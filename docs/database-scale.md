# Database scale - what was measured, what was fixed, what was deliberately left

The P4 audit finding this closes: *"Aggregates computed in Python, not SQL...
At a 1.8M-unit maintenance base - the number the pitch leads with - this does
not degrade, it stops."* This file is the evidence for what actually changed,
measured against a real (not simulated) Postgres instance, and an honest
account of what a 1.8M-row test would need that this pass did not have.

> **Status.** Every number below was measured in this build's own sandbox
> environment against `postgres:16-alpine` via `docker-compose.yml`, using
> `backend/scripts/load_test.py`. It is a real Postgres instance, not a
> simulation - but the fleet size tested (200,000 components / ~600,000
> service events) is roughly 9x smaller than the 1.8 million the pitch
> quotes. See §5 for what that gap does and does not mean.

---

## 1. What was actually slow, and why

Before this pass, `app/api/dashboard.py` answered almost every question -
"what's the current disposition breakdown", "what's the average health
score", "what needs inspection" - by loading every matching `Component` (plus
its predictions) into Python and looping over the ORM objects. That is
`O(fleet size)` Python work on every request to a page a technician opens
routinely, and it does not degrade gracefully: it is exactly the pattern the
audit's own words ("this does not degrade, it stops") describe.

## 2. What changed

1. **Every aggregate moved into SQL** - `GROUP BY` / `COUNT` / `AVG` /
   `percentile_cont` instead of a Python loop over ORM objects. See the
   module docstring in `app/api/dashboard.py`.
2. **A cached "current recommendation" column.** The first SQL rewrite still
   computed "what is this component's latest recommendation" with a
   `MAX(id) GROUP BY component_id` join against the full, forever-growing
   `predictions` table on every dashboard request. Measured at 200k
   components / ~600k predictions, that alone cost `GET /dashboard/summary`
   a 1.75s p95. `Component.latest_recommendation` /
   `latest_confidence` (migration `0011_cached_recommendation`) cache the
   answer, refreshed on every assessment
   (`app.services.prediction_service.assess_component`) the same way
   `health_score` already was. `predictions` itself is untouched and stays
   append-only - this is a read-side cache, not a change to what gets
   persisted or to the audit trail around it.
3. **SQL-side bucketing.** Health-score and confidence distributions used to
   pull every non-null value into Python and bucket it there
   (`app.api.dashboard._bucket_counts` / `_band_counts` /
   `_avg_and_median` now do it in one `GROUP BY` over a `CASE` expression,
   plus `percentile_cont` for an exact median on Postgres).
4. **`service_events` is partitioned by year on Postgres**
   (migration `0010_partition_service_events`), so a query bounded to a date
   range - `dashboard.monthly_activity`'s `WHERE event_date >= cutoff`, for
   instance - can prune to the relevant partition(s) instead of scanning
   every service event the fleet has ever logged. SQLite (tests, local dev)
   is a documented no-op; see the migration's own docstring for why
   `audit_logs` was deliberately **not** partitioned in this pass.
5. *(Removed.)* Recovery Exchange matching did SQL candidate generation;
   the exchange has since been removed from the platform.

## 3. Measured, before and after

`scripts/load_test.py seed --count 200000` bulk-inserts 200,000 components
(plus one prediction and 3 service events each) via plain SQL in ~15 seconds
- the ORM per-row path `scripts/seed_database.py` uses is the right tool for
a curated demo fleet and the wrong one for this. `scripts/load_test.py bench`
then times each endpoint 20 times against a running API pointed at that
database, logged in as a tenant-scoped supervisor with `?all_units=true`
(the broadest single-country view a non-global role can request).

| Endpoint | Before (full Python loop) | After cached-column + SQL bucketing |
|---|---:|---:|
| `GET /dashboard/summary` | p95 **1,747 ms** | p95 **152–213 ms** |
| `GET /dashboard/analytics` | p95 **5,431 ms** | p95 **~1,330–1,395 ms** |
| `GET /dashboard/safety-queue` | (not separately measured before) | p95 **5 ms** |
| `GET /components?page_size=50` | (not separately measured before) | p95 **10–14 ms** |
| `GET /recovery/summary` *(endpoint since removed)* | (not separately measured before) | p95 **6–9 ms** |

Every single-purpose endpoint (`safety-queue`, the component list, recovery
summary) is comfortably inside the plan's own p95 < 300ms target.
`/dashboard/analytics` is not: it deliberately answers ~10 independent
aggregate questions in one round trip so the analytics page loads in one
request, and at this fleet size that is still roughly a dozen separate
queries even after every individual query was made efficient. It is ~4x
faster than before this pass (5.4s → 1.3–1.4s) but is the one endpoint left
above the target - see §4.

## 4. What is still open on `/dashboard/analytics`

The honest next step, not attempted in this pass because it changes the
endpoint's caching contract rather than just its query shape: a materialised
summary row per tenant (country × frontline unit), refreshed transactionally
whenever a component or prediction changes, so `/dashboard/analytics` reads
one row instead of recomputing ~10 aggregates from `components` on every
request. That is the literal "summary tables refreshed on write" P4 asked
for; this pass delivered the SQL-aggregation half of that sentence and the
cached-column version of it for `components`, and is recording the
materialised-summary-table half as the next increment rather than rushing it
into this same change.

## 5. What 200k proves and what it does not

- **Proves:** the query shape is now `O(distinct groups)` or `O(indexed row
  range)`, not `O(fleet size)` - the property that actually determines
  whether performance holds at 10x or 30x this fleet, because none of the
  rewritten queries scan the full `components` or `predictions` table
  unconditionally any more.
- **Does not prove:** that 1.8 million components behaves identically. Disk
  layout, autovacuum behaviour, connection pool sizing, and query planner
  choices can all shift at an order of magnitude beyond what was tested here,
  and none of that was validated in this sandbox. A provisioned staging
  environment at or near the real target size, with real (not synthetic)
  index bloat and autovacuum history, is what would close that gap - that is
  infrastructure this environment does not have, not a claim this document
  is making on its behalf.

## 6. Reproducing this

```bash
docker compose up -d postgres
cd backend
alembic upgrade head
python scripts/seed_users.py
python scripts/load_test.py seed --count 200000
python scripts/load_test.py bench --base-url http://localhost:8000
```
