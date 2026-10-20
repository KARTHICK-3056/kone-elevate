# Threat model

The P4 deliverable this satisfies: *"a documented threat model, and a
personal-data review covering technician names in an append-only log."*
Both live here, because the honest answer to "is a technician's name a
privacy concern" only makes sense next to "who can read it and how" - the
two questions share the same trust-boundary diagram.

> **Status.** This is a first pass, written against the system as it stands
> after P4. It has not been reviewed by a security professional external to
> this build, and should be treated as a structured starting point for that
> review, not a substitute for it.

---

## 1. System overview and trust boundaries

```
                    ┌─────────────────────────────────────────┐
  Technician's      │              Internet / LAN              │
  phone (QR scan)   │                                          │
        │            │                                          │
        ▼            │                                          │
 ┌─────────────┐     │      ┌──────────────┐      ┌──────────┐  │
 │  Frontend    │◄────┼─────►│   Backend    │◄────►│ Postgres │  │
 │  (nginx,     │     │      │  (FastAPI)   │      │          │  │
 │   static)    │     │      └──────┬───────┘      └──────────┘  │
 └─────────────┘     │             │                            │
                      │             ▼                            │
                      │      ┌──────────────┐                    │
                      │      │ SMTP relay    │ (signup codes)     │
                      │      │ (optional)    │                    │
                      │      └──────────────┘                    │
                      └─────────────────────────────────────────┘
```

Trust boundaries that matter:

1. **Public internet → frontend/backend.** Anything reachable without a
   token: `/health`, `/metrics`, the entire `/passports/*` QR-scan surface,
   `/auth/login`, `/auth/signup*`. Everything else requires a bearer token
   (`app/main.py`'s `authenticated` dependency list).
2. **Authenticated caller → tenant boundary.** A signed-in user is scoped to
   their `country` (hard) and `frontline_unit` (soft default) - see
   `app/core/tenancy.py`. This boundary is enforced in application code, not
   at the database or network layer.
3. **Backend → Postgres.** One shared credential (`DATABASE_URL`), no
   per-tenant database role. A SQL-injection bug anywhere would bypass every
   tenant boundary at once - see §3, "Application-layer tenant isolation
   only."
4. **Backend → SMTP.** Only reached for signup verification codes; disabled
   (falls back to a local outbox) when unconfigured. See
   `app/services/email_service.py`.

## 2. Assets, ranked by what a compromise actually costs

| Asset | Why it matters | Where it lives |
|---|---|---|
| Audit chain (`audit_logs`) | The entire compliance/tamper-evidence pitch rests on this being both correct and attributable | Postgres, hash-chained, see `app/services/audit_service.py` |
| Bearer-token signing key (`SECRET_KEY`) | Anyone who has it can mint a token for any user, any role | `app/core/config.py` / `app/core/secrets.py` |
| Password hashes (`users.password_hash`) | PBKDF2-HMAC-SHA256, 240,000 rounds in production - expensive to crack per-guess, not immune to it | `users` table |
| Component/service-event data | Business data (fleet composition, service history); moderately sensitive, not personal in itself | `components`, `service_events` |
| Technician names, actor emails | Personal data inside an append-only log - see §4 | `service_events.technician`, `audit_logs.actor` |
| Database credential (`DATABASE_URL`) | Full read/write over every tenant at once | Environment / `.env` (gitignored) |

## 3. Threats and mitigations

### 3.1 Identity and access

| Threat | Mitigation | Residual risk |
|---|---|---|
| Credential stuffing against `/auth/login` | PBKDF2 (240k rounds) + IP rate limiting (`app/core/rate_limit.py`, 10/min default) | Single-process, in-memory limiter - see §6, "Rate limiting is per-process" |
| Signup used to mint many low-privilege accounts | IP rate limiting on `/auth/signup` (5/min default); self-registered accounts always land on the lowest-privilege role with no path to self-elevate | An attacker distributed across many IPs is not slowed by this |
| OTP brute-forcing on `/auth/signup/verify` | Per-challenge attempt cap (`OTP_MAX_ATTEMPTS=5`) and expiry (`OTP_TTL_MINUTES=10`), not IP rate limiting - deliberately: guessing one account's 6-digit code is already capped at 5 tries regardless of how many IPs an attacker has | None material within the existing cap |
| Stolen/forged actor attribution in the audit chain | `current_actor` reads only the verified bearer-token subject; there is no header or body field that can name an actor (closed the `X-Actor` and `MatchDecision.actor` spoofing paths - see P4 §deliverables) | A compromised account still writes attributable-to-that-account entries |
| Privilege escalation via self-registration | `SignupRequest` has no `role` field; `POST /auth/users` (the only path to a role above `technician`) requires `require_roles(Role.SUPERVISOR)` | A compromised supervisor account can mint arbitrary roles - see "single point of privilege" below |

**Single point of privilege, accepted as a known gap.** Every role above
`technician` is granted by a supervisor, and there is no dual-control or
approval step on `POST /auth/users`. A compromised supervisor account can
provision a `sustainability_controller` or another `supervisor` account
outright. Mitigating this properly (dual approval, anomaly detection on
account creation) is real production-identity work out of scope for this
pass; it is recorded here rather than left implicit.

### 3.2 Multi-tenancy

| Threat | Mitigation | Residual risk |
|---|---|---|
| Cross-country data read | Every component lookup enforces `country` equality against the caller's own; a mismatch returns a plain 404 (not 403 - see `app/core/tenancy.py`'s module docstring for why leaking existence would itself be a disclosure) | Enforced in application code, not the database - see below |
| Cross-frontline-unit read (same country) | Soft default only, by design. Documented as an intentional, not accidental, boundary | A technician's default list view is scoped, but `?all_units=true` is one query parameter away for anyone in the same country |
| SQL injection bypassing tenant scoping entirely | Every query in this codebase uses SQLAlchemy's parameterised query builder; there is no raw string-interpolated SQL in a request path (the raw SQL that does exist - `scripts/load_test.py`, migrations - runs outside any request context) | A future endpoint that drops to raw SQL without parameterisation would bypass every tenant check at once. Not currently the case; worth a lint rule if this grows |

**Application-layer tenant isolation only.** There is one Postgres role and
one connection pool for every tenant; nothing at the database layer (row-level
security policies, separate schemas, separate roles) backs up the
application-level `WHERE country = ...` filters. This is a normal, accepted
architecture for a single-database multi-tenant SaaS product, but it means a
bug in `app/core/tenancy.py` or a forgotten `scope_by_country()` call on a new
endpoint is a full cross-tenant data leak, not a partial one. Postgres
row-level security policies mirroring the same country/global-role logic
would be the defence-in-depth version of this; not implemented in this pass.

### 3.3 Data in transit and at rest

| Threat | Mitigation | Residual risk |
|---|---|---|
| Eavesdropping on API traffic | None inside this repository - TLS termination is an infrastructure concern (ingress/load balancer), not application code | Every deployment must terminate TLS somewhere before this API is reachable; nothing here enforces that |
| Database credential exposure via a leaked `.env` | `.env` is gitignored (verified); `SECRET_KEY`/SMTP password can be sourced from HashiCorp Vault instead (`app/core/secrets.py`) | Vault path is unit-tested against a mocked response only - no live Vault instance was available to confirm the real round trip (see that module's docstring) |
| Default secrets reaching production | `app/main.py::_guard_against_default_secret` refuses to boot with the shipped `SECRET_KEY` when `DEBUG=false` | `POSTGRES_PASSWORD`'s docker-compose default (`change_me`) has no equivalent boot-time guard |

### 3.4 Observability surface

| Threat | Mitigation | Residual risk |
|---|---|---|
| `/metrics` exposes prediction-class distribution / abstention rate to anyone | Deliberately unauthenticated, matching standard Prometheus practice (see `app/api/metrics.py`) | In a deployment where this API is directly internet-reachable rather than behind a private scrape network, this is a real information disclosure (fleet health signal, abstention rate) to an unauthenticated caller. **Action for a real deployment: restrict `/metrics` at the ingress/network layer**, not application auth |
| Request/DB tracing spans leak sensitive data | `app/core/telemetry.py` truncates `db.statement` to 512 chars and does not log bound parameter values; span export defaults to nowhere (`OTEL_CONSOLE_EXPORT=False`, no OTLP endpoint configured) unless explicitly turned on | A configured OTLP collector receives full SQL statement text (parameters excluded) - treat the collector itself as needing the same access control as application logs |
| Structured JSON logs leak PII into a log aggregator | Log records are built from record attributes and explicit `extra=` fields, not full request/response bodies | A future `logger.info("payload: %s", request_body)` call would leak whatever that payload contains, technician names included - no automated redaction exists |

### 3.5 Dependency supply chain

Backend: `pip-audit -r requirements.lock` currently reports **zero known
vulnerabilities** (see `docs/database-scale.md`'s CI section and
`.github/workflows/ci.yml`). SBOM generated in CI as CycloneDX JSON for both
tiers.

Frontend: `npm audit --audit-level=high` currently reports **7
vulnerabilities (5 moderate, 1 high, 1 critical)**, all in
`vite`/`esbuild`/`vitest` (dev-time build tooling, not shipped to the
browser) and `react-router-dom` (a real runtime dependency - an open-redirect
class issue). Fixing them needs `react-router-dom` 6→7 (a breaking API
migration touching every route definition in `App.jsx`) and `vite`/`vitest`
major bumps - deliberately **not** forced through in this pass without the
frontend regression testing that migration deserves; recorded here as an
open, prioritised item rather than silently left. `npm audit` stays
informational (`|| true`) in CI until that migration lands; flip it to
blocking the moment it does.

## 4. Personal-data review

Two fields carry personal data inside an **append-only** system, which is
exactly the case GDPR's storage-limitation and erasure principles were
written for and an audit chain is structurally bad at satisfying:

| Field | What it is | Erasure story today |
|---|---|---|
| `service_events.technician` | Free-text name of whoever performed a service event | **None.** The row is part of an append-only lifecycle history; there is no delete/redact path |
| `audit_logs.actor` | The verified email of whoever performed a chain-recorded action | **Structurally cannot be erased** without breaking the hash chain - every subsequent row's hash depends on this row's content |
| `users.email`, `users.display_name` | Account identity | `DELETE`-able in principle (no cascade tested), but doing so does not touch `audit_logs.actor` snapshots already taken |

**This is a real, unresolved tension, not an oversight to paper over.** An
append-only, tamper-evident audit chain and a "right to erasure" pull in
opposite directions by construction: the chain's entire value proposition is
that a snapshot cannot be changed after the fact, and a name embedded in a
hashed snapshot cannot be redacted without invalidating every hash after it.

What a real deployment needs before this is defensible under GDPR (or
India's DPDP Act, given the seeded demo fleet's own country):

1. **Pseudonymise at write time, not read time.** Store a stable internal
   employee id in `technician` / derive `actor` from it, with the id→name
   mapping held in a *separate, erasable* system (the actual HR/identity
   system, not this database). This is the standard pattern for "identity in
   an immutable log" and was not implemented in this pass - `technician` and
   `actor` still store the display name / email directly today.
2. **A documented lawful basis** (legitimate interest for maintenance
   records is the likely fit) and retention period, published somewhere a
   data-subject request can be answered against. Not drafted in this pass.
3. **A DPIA** (Data Protection Impact Assessment) before any real personal
   data - not the synthetic demo fleet - enters this system. Listed as a
   P6 deliverable already (`plan.md`'s governance pack); repeated here
   because it is the actual answer to the erasure tension above, not a
   checkbox alongside it.

## 5. The AI Act question

Already analysed in `plan.md` §6 ("The AI Act question you will be asked")
in more depth than belongs duplicated here. Summary: this product almost
certainly falls outside Annex I high-risk classification because it advises
on *already-removed* components rather than the operation of a lift in
service, and the safety gate (mandatory human inspection for ropes, brakes,
governors) is the specific design choice that keeps it there - the
classification argument rests entirely on that gate remaining absolute. See
`plan.md` for the full reasoning and the regulatory citations.

## 6. Known gaps, stated plainly

- **Rate limiting is per-process, in-memory.** Correct for the one-worker
  deployment this ships (`uvicorn app.main:app` with no `--workers` flag in
  `docker-compose.yml`). Adding worker processes multiplies the effective
  limit by worker count, because each process counts independently - a
  shared store (Redis) is the fix, not implemented here. See
  `app/core/rate_limit.py`'s module docstring.
- **No dual control on account provisioning** (§3.1).
- **No database-layer tenant isolation** (§3.2) - application code is the
  only enforcement point.
- **`POSTGRES_PASSWORD`'s default has no boot-time guard**, unlike
  `SECRET_KEY` (§3.3).
- **Personal data has no erasure path** (§4) - the most important open item
  in this document, and the one a real pilot cannot proceed without closing.
- **Vault integration is unit-tested against a mock, not a live server**
  (§3.3) - see `app/core/secrets.py`.
- **Frontend dependency vulnerabilities are open, not fixed** (§3.5).
