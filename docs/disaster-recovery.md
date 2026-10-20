# Disaster recovery: backup, retention, and a real restore drill

The P4 deliverable this satisfies: *"PITR configured, retention policy
documented, restore drill rehearsed and timestamped."* All three are here,
and the restore drill was run for real against this build's own
`docker-compose.yml` Postgres - not asserted, replayed below with the actual
log output.

---

## 1. What "configured" means here

`docker-compose.yml`'s `postgres` service now starts with:

```
-c wal_level=replica
-c archive_mode=on
-c archive_command='test ! -f /var/lib/postgresql/wal_archive/%f && cp %p /var/lib/postgresql/wal_archive/%f'
-c max_wal_senders=3
```

backed by a new named volume, `postgres_wal_archive`, separate from the main
`postgres_data` volume. This is continuous WAL archiving, not just periodic
`pg_dump` snapshots: combined with one base backup (`pg_basebackup`), it lets
a restore land on *any* point in time after that backup, not only the moment
the backup itself was taken.

**A found-the-hard-way gotcha, now handled automatically.** A freshly
created `postgres_wal_archive` volume is `root`-owned by Docker by default.
Postgres's `archive_command` then fails silently - it logs a warning and
retries forever rather than crashing - so a deployment can look like it has
working PITR while nothing has actually been archived. `scripts/backup_postgres.sh`
now runs `chown postgres:postgres` on that path before every backup, which is
idempotent and harmless once the ownership is already correct. This is
recorded here because it is exactly the kind of gap that is invisible until
the day someone needs the archive and it turns out to be empty.

## 2. Retention policy (illustrative, not yet operationally enforced)

| Backup type | Frequency | Retention |
|---|---|---|
| Physical base backup (`pg_basebackup`) | Daily | 35 days |
| Base backup | Weekly | 1 year |
| WAL archive | Continuous | At least as long as the oldest retained base backup |

These figures are a reasonable starting point, not a validated compliance
requirement - nothing in this repository currently enforces them (no
scheduled job prunes old backups or WAL segments). Wiring
`scripts/backup_postgres.sh` into cron/a scheduled CI job, and adding a
matching pruning script for the WAL archive volume, is the next step before
this is a real operational practice rather than a documented intention.

## 3. The restore drill

Run against the live `docker-compose.yml` Postgres instance (`postgres:16-alpine`,
container `kone-elevate-postgres`), already carrying a synthetic fleet of
200,060 components / 600,627 service events / 326 audit-chain records from
`scripts/load_test.py` at the time of this drill.

**Procedure:** take a base backup; insert a canary row (`DR-CANARY-BEFORE`);
record the exact time; wait 2 seconds; insert a second canary row
(`DR-CANARY-AFTER`); force the WAL to archive (`pg_switch_wal()`); restore
the base backup plus archived WAL into a **separate, throwaway Postgres
instance** (never the live one) targeting the recorded time; confirm the
first canary survived, the second did not, and the audit chain still
verifies as intact.

### Timestamped result

```
Base backup taken:        2026-09-17 04:39:xx UTC  (pg_basebackup, 424,933 kB)
DR-CANARY-BEFORE inserted: 2026-09-17 04:39:48.981593 UTC
Recovery target time:      2026-09-17 04:39:56.374951 UTC
DR-CANARY-AFTER inserted:  2026-09-17 04:39:58.423904 UTC
```

Restore log (`recovery_target_action = 'promote'`), verbatim:

```
LOG:  starting point-in-time recovery to 2026-09-17 04:39:56.374951+00
LOG:  starting backup recovery with redo LSN 0/4D000028, checkpoint LSN 0/4D000060, on timeline ID 1
LOG:  restored log file "000000010000000000000004D" from archive
LOG:  redo starts at 0/4D000028
LOG:  restored log file "00000001000000000000004E" from archive
LOG:  consistent recovery state reached at 0/4E00C2C0
LOG:  recovery stopping before commit of transaction 786, time 2026-09-17 04:39:58.426364+00
LOG:  redo done at 0/4E00C2C0
LOG:  selected new timeline ID: 2
LOG:  archive recovery complete
LOG:  database system is ready to accept connections
```

`transaction 786` is the `DR-CANARY-AFTER` insert - Postgres reports stopping
recovery *before* committing it, exactly at the requested boundary.

### Verification, against the restored instance

```
SELECT component_id, created_at FROM components WHERE component_id LIKE 'DR-CANARY%';

   component_id   |         created_at
-------------------+----------------------------
 DR-CANARY-BEFORE  | 2026-09-17 04:39:48.981593
```

`DR-CANARY-AFTER` is absent, as required. Row counts on the restored instance:
200,061 components (200,060 + the one canary that should have survived),
600,627 service events (unaffected - no service events were written during
the drill window), 326 audit-chain records.

**Audit chain integrity survives the restore.** `scripts/verify_chain.py`
run against the restored instance:

```
AUDIT CHAIN VERIFICATION
  records checked : 326
  valid           : True
```

This is the result that actually matters for this product: a full
backup/restore/point-in-time-recovery cycle does not corrupt or invalidate
the tamper-evident hash chain the entire compliance story depends on.

### The packaged scripts were separately run and produce a live, connectable database

`scripts/backup_postgres.sh` and `scripts/restore_pitr.sh` (the reusable,
parameterised versions of the manual steps above) were run end-to-end
against a fresh backup and a different target time; the restored instance
came up on the requested port, accepted connections, and its recovery log
showed the same `recovery stopping before commit of transaction ...` /
`database system is ready to accept connections` sequence. The specific
canary rows used in that second run landed close enough to the recovery
boundary (both issued in the same `psql -c` invocation, which Postgres runs
as one implicit transaction, giving both statements the same `now()`) that
the *before/after* assertion on that particular data was ambiguous - a flaw
in how that follow-up test was instrumented, not in the restore mechanism,
which is why the unambiguous first run (separate `psql` invocations, an
explicit `pg_sleep`) is the one recorded as the timestamped result above.

## 4. Reproducing this

```bash
docker compose up -d postgres
cd backend
./scripts/backup_postgres.sh ./backups

# ... time passes, more data is written ...

./scripts/restore_pitr.sh ./backups/basebackup-<timestamp> "<recovery target time>" 5555
docker exec -u postgres kone-elevate-postgres psql -p 5555 -U kone_admin -d kone_elevate
DATABASE_URL="postgresql+psycopg2://kone_admin:change_me@kone-elevate-postgres:5555/kone_elevate" \
    python scripts/verify_chain.py

# Clean up when done:
docker exec -u postgres kone-elevate-postgres pg_ctl -D <restore-path-printed-above> stop -m fast
docker exec kone-elevate-postgres rm -rf <restore-path-printed-above>
```

## 5. What is not covered by this drill

- **Restoring after total loss of the `kone-elevate-postgres` container and
  both volumes** (`postgres_data` and `postgres_wal_archive`) was not
  tested - this drill restores from a backup copied out via `docker cp`,
  which implies the backup already left the host. A real deployment must
  ship both the periodic base backup *and* the continuously-archived WAL
  segments to storage outside the machine running Postgres (object storage,
  a separate backup host) for that to be true; this repository does not do
  that shipping for you.
- **Restoring the frontend or the trained model artefacts** is out of scope
  for this document - those are stateless (rebuildable from the Docker image
  and `scripts/train_model.py` / `scripts/train_forecast.py`) rather than
  data requiring backup.
- **A restore under real time pressure**, i.e. an actual incident drill with
  a stopwatch and a runbook someone unfamiliar with this system follows cold.
  What exists here is a proof that the mechanism works, not a rehearsed
  operational runbook.
