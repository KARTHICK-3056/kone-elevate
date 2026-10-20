# Component Passport — Build Audit and Completion Plan

**Engineering & strategy audit · 11 September 2026**

An end-to-end read of the KONE ELEVATE codebase against the Kone Elevate pitch,
against production standards, and against what KONE Corporation actually has to
deliver between now and 2030.

| | |
|---|---|
| Repo | `D:\Coding\kone-elevate` |
| Team | CodeFather · SRM IST Ramapuram |
| Model | `RF-v1.0-synthetic` |

---

## Contents

1. [The verdict](#1-the-verdict)
2. [What is actually built](#2-what-is-actually-built)
3. [Pitch-to-code ledger](#3-pitch-to-code-ledger)
4. [Four gaps that matter](#4-four-gaps-that-matter)
5. [Production readiness](#5-production-readiness)
6. [Aligning to KONE](#6-aligning-to-kone)
7. [The plan, phase by phase](#7-the-plan-phase-by-phase)
   - [P0 — Make it real](#p0--make-it-real)
   - [P1 — A model a safety engineer will accept](#p1--a-model-a-safety-engineer-will-accept)
   - [P2 — Forecasting and refurbishment capacity](#p2--forecasting-and-refurbishment-capacity)
   - [P3 — The compliance engine](#p3--the-compliance-engine)
   - [P4 — Production hardening](#p4--production-hardening)
   - [P5 — Field reality and systems integration](#p5--field-reality-and-systems-integration)
   - [P6 — Validation and pilot](#p6--validation-and-pilot)
8. [Next seven days](#8-next-seven-days)
9. [What not to build](#9-what-not-to-build)
10. [Sources](#10-sources)

---

## 1. The verdict

| Metric | Value |
|---|---|
| Lines of app code | **15,368** |
| API endpoints | **60** |
| Tests | **82** (62 py / 20 js) |
| Model accuracy (synthetic) | **82.2%** |
| Lines of forecasting code | **0** |

> **This is not a vibecoded demo.** It is a genuinely well-engineered prototype —
> and it is roughly **55%** of the product the pitch describes, and roughly **20%**
> of the product KONE could deploy.

The build quality is unusually high for a hackathon artefact. The feature contract
is shared across the dataset generator, trainer and inference path so training and
serving cannot drift. The health score is a fully inspectable weighted model that
returns its own breakdown. The audit chain is a real SHA-256 hash chain with a
working tamper test. The safety gate is enforced in code, exercised in tests, and
surfaced in the UI. The README is candid about its own limitations in a way most
commercial pitches are not — and that honesty is an asset with a safety-regulated
buyer, not a weakness.

Three things are true at the same time, and the plan below follows from all three:

- **The demo layer is done.** Registry, passport, QR, prediction, explanation,
  exchange, dashboard, audit chain, seeded portfolio, Docker Compose, docs. You can
  walk a judge through this today.
- **Two headline promises have no code behind them.** Probability calibration and
  end-of-life forecasting / refurbishment capacity planning appear on the slides and
  appear nowhere in the repository. So do ISO 4344, ISO 281 and EN 81-80 — those
  strings return zero matches across the entire codebase.
- **The thing that makes it an enterprise product is absent.** There is no enforced
  identity, so the audit trail's `actor` field is self-asserted via an unverified
  `X-Actor` header. An audit log that cannot prove who acted is not an audit log a
  sustainability assurer will accept. This single gap undercuts the platform's
  central claim.

**Coverage:** 55% built and working · 20% shell exists, substance missing ·
25% claimed, not started.

---

## 2. What is actually built

The system runs as three tiers: a FastAPI backend with a SQLAlchemy 2.0 ORM over
SQLite or PostgreSQL, a scikit-learn pipeline serialised as a single joblib bundle,
and a React 18 + Vite frontend that talks to the API through one centralised axios
client with normalised error handling. Docker Compose wires Postgres, backend,
frontend and an optional pgAdmin.

### Backend, 7,746 lines

Seven routers under `/api/v1`. Six ORM models — `Component`, `ServiceEvent`,
`Prediction`, `RecoveryItem`, `RecoveryMatch`, `ServiceDemand`, `AuditLog` — with
composite indexes that suggest someone thought about query plans. Five services
carry the domain logic out of the API layer: health scoring, impact estimation,
prediction orchestration, recovery matching, audit chaining. Error handlers convert
integrity violations, database faults and unhandled exceptions into shaped JSON
without leaking a stack trace.

Two design decisions stand out. First, `predictions` are append-only: an assessment
never updates in place, so the passport carries the entire decision history. Second,
the sensor ingestion endpoint deliberately returns `501 Not Implemented` with a
documented future payload, so no part of the demo can imply live telemetry that does
not exist. That is exactly the right instinct for this buyer.

### The ML path, and what it really shows

A 10,000-row synthetic dataset is produced by a small causal simulator — building
traffic drives duty cycle, duty and age drive a latent wear variable, and every
observable (vibration, temperature, inspection score, repairs, failures) is a
*noisy* view of that hidden wear. The label is generated from the latent variable
the model never sees, so there is no target leakage, and deliberate class overlap
keeps accuracy in a believable band instead of an implausible 100%.

Measured on 2,000 held-out synthetic rows:

| | REUSE | REFURBISH | RECYCLE | DISPOSE |
|---|---|---|---|---|
| Precision | 0.827 | 0.818 | 0.792 | 0.860 |
| Recall | 0.844 | 0.782 | 0.807 | 0.873 |
| F1 | 0.836 | 0.800 | 0.799 | 0.866 |
| Support | 340 | 592 | 597 | 471 |

Accuracy 82.15%, macro F1 0.825. Mean confidence 0.737 — 0.757 when correct, 0.643
when wrong. Feature importance is dominated by inspection score (0.266), operating
hours (0.160) and load cycles (0.117).

> **Read the confusion matrix, not the accuracy.**
> 59 components the simulator labelled REFURBISH were predicted REUSE, and 64
> labelled DISPOSE were predicted RECYCLE. Those are the *optimistic* errors — the
> ones that put a part back into a building or a foundry when it should not go there.
> 52 REUSE→REFURBISH and 50 RECYCLE→REFURBISH are the conservative errors, which
> cost money but not safety. Today all four error types are weighted identically by
> the F1 score the slides quote. A KONE quality engineer will look at exactly this
> asymmetry first.

### Frontend, 7,622 lines

Nine routes, nineteen components, three data hooks, nine Recharts visualisations. A
top-level error boundary keeps a rendering fault from producing a blank screen. The
passport route detects a QR-scan entry and drops all navigation chrome, rendering a
phone-shaped record — a small detail that shows someone pictured a technician in a
machine room. A manual entry fallback sits permanently beside the camera scanner
because `getUserMedia` needs a secure context.

### The audit chain

Every state change appends one row storing the hash of the row before it.
`verify_chain` walks the whole chain and reports the *first* break, distinguishing a
`broken_link` (a row inserted, removed or reordered) from a `snapshot_modified` (a
historical record edited after the fact). The canonical JSON serialiser sorts keys
and fixes separators so two logically identical payloads always hash identically.
The docstring correctly describes this as tamper *evidence*, not a blockchain. That
framing is more credible to an enterprise audience than the alternative, and it
should stay.

---

## 3. Pitch-to-code ledger

Every claim on the six pitch slides, checked against the repository.

| Claim | Status | Evidence in code |
|---|---|---|
| QR-linked passport at installation | ✅ Built | `app/api/passports.py` · `services/qr_service.py` — PNG, data-URI, metadata and a forgiving scan resolver that accepts a URL, a bare id or a token |
| Tracks origin, duty cycle, service history | ✅ Built | `models/component.py` · `models/service_event.py` — 6 event types, readings captured per event |
| Random Forest disposition recommender | ✅ Built | `app/ml/train.py` — 400 trees, depth 16, balanced subsample, whole pipeline serialised so serving cannot drift from training |
| "Random Forest **+ calibration**" | ❌ Absent | No `CalibratedClassifierCV`, no reliability curve, no Brier score, no ECE anywhere. The README already admits this; the slide does not |
| Recharts "impact and **calibration** visualisations" | ❌ Absent | Nine charts exist; none of them is a calibration plot |
| Explainable AI — confidence + key factors | ⚠️ Partial | `app/ml/explain.py` blends global Gini importance with per-component design-envelope deviation. Honest, but global importance is not per-prediction attribution, and Gini is biased toward high-cardinality features |
| Safety gate for ropes, brakes, governors | ✅ Built | `app/ml/predict.py` `_apply_safety_gate` — flag, verbatim message and disclaimer on every response; covered by tests including "banner appears even when the AI says REUSE" |
| Recovery Exchange matches recovered parts to demand | ✅ Built | `services/recovery_service.py` — six weighted criteria over 100 points, threshold 55, every scoring term emits a human-readable reason line |
| Closed loop — reallocates recovered parts | ✅ Built | `accept_match` allocates the item, closes the demand, moves the component to ALLOCATED, rejects sibling proposals and audits all of it in one transaction |
| Portfolio Command Center | ✅ Built | 11 dashboard endpoints incl. a safety-critical inspection queue |
| SHA-256 tamper-evident audit log | ✅ Built | `services/audit_service.py` — but see the concurrency defect in §5 |
| **Forecast end-of-life · plan refurbishment capacity ahead** | ❌ Absent | Zero matches for forecast, RUL, remaining-useful-life or capacity across the codebase. No survival model, no horizon, no endpoint, no page. This is a core pillar of the pitch with nothing behind it |
| Auditable lifecycle data for CSRD and BRSR | ⚠️ Shell only | The chain and CSV exports exist. The words CSRD, BRSR, ESRS, DPP and "digital product passport" appear *nowhere* in the codebase. There is no period-scoped report, no material-flow ledger, no disclosure mapping |
| Passport model is standards-based — ISO 4344, ISO 281, EN 81-80 | ❌ Absent | Zero occurrences. The type reference table in `app/ml/features.py` holds plausible design envelopes that the README correctly calls placeholders, with no clause citation |
| Economic and CO₂ impact | ✅ Built as estimate | `services/impact_service.py` — factor tables live in config so engineering can replace them without touching code. Every response carries a prototype disclaimer. Well handled |
| ₹30,000–₹1,20,000 saved per component; ₹4.9 L and 1.7 t CO₂ per site per quarter | ⚠️ Per-component traced; per-site now derivable (see P0 follow-up) | The per-component band is close to REUSE × the configured part costs. The per-site quarterly figure needed a site model that did not exist; `app.services.site_impact_service` (added post-launch, see P0 deliverables) now derives it from real data - on the 60-component demo fleet it comes out to ~₹78,000 and 0.33 t CO₂ per site per quarter, well under the original ₹4.9L/1.7t guess, because the demo fleet is far smaller per site than a real KONE site's component count. The mechanism is real; the magnitude will only match the slide once it runs against a fleet the size the slide assumed |
| Live IoT integration | ⏸️ Deferred, honestly | `POST /api/v1/sensors/{id}` returns 501 with a documented planned payload. Correct call |
| Technician mobile app | ⚠️ Partial | `html5-qrcode` scanner plus a chrome-free standalone passport route. No PWA manifest, no service worker, no offline queue |

---

## 4. Four gaps that matter

Not everything missing is equally important. These four decide whether this becomes
a product.

### 1 · The model tells a technician to act, and does not know how sure it is

Mean confidence across held-out predictions is 0.737. Random Forest vote fractions
are not probabilities; they are systematically overconfident in the middle of the
distribution and underconfident at the extremes. The UI renders that number as a
percentage next to a recommendation, which invites a technician to read 0.74 as
"74% likely correct." Nothing in the repo establishes that it is.

Worse, the system always returns an answer. There is no abstention. A component
sitting on the REFURBISH/RECYCLE boundary — where 117 of 2,000 test errors live —
gets the same confident presentation as a clear-cut case. For a decision-support
tool in a safety-regulated industry, *knowing when not to answer* is more valuable
than another two points of accuracy.

### 2 · The product forecasts nothing

"Forecast end-of-life. Plan refurbishment capacity ahead." is on the solution slide
and in the system-flow diagram. It is the difference between a scoring tool and a
planning platform — and it is the half of the value proposition KONE's service
organisation would actually buy, because refurbishment capacity is a fixed asset
that has to be scheduled quarters in advance. The current system is entirely
point-in-time: score a component that is already in front of you. Nothing projects
forward.

### 3 · "Auditable lifecycle data for CSRD" is a chain, not a report

The audit chain proves that a record was not edited. It does not produce a
disclosure. Under ESRS E5, the two disclosure requirements that matter — E5-4
resource inflows and E5-5 resource outflows — are **mass-flow** metrics, expressed
in tonnes of material, not in CO₂e or rupees. The platform today reports CO₂ avoided
and INR recovered, and never persists a kilogram of anything: component mass is a
config lookup applied at read time, so there is no ledger of material entering or
leaving the fleet. A reporting controller cannot derive an E5 table from this
database.

### 4 · The audit actor is a header anyone can type

`current_actor` reads an optional `X-Actor` request header and falls back to
`"system"`. Every accept, reject, assessment and deletion in the chain is attributed
to an unverified string. The hash chain is cryptographically sound and evidentially
worthless, because it proves only that an unauthenticated claim was recorded without
subsequent edit. Identity is not a Phase 4 nicety here; it is load-bearing for the
central pitch.

---

## 5. Production readiness

Findings ranked by severity.

| Sev | Finding | Why it bites | Fix |
|---|---|---|---|
| 🔴 | No version control | This working copy is not a git repository. `models/metrics.json` records a training path of `G:\KONE\…`, so the tree was built elsewhere and copied. No history, no branches, no review, no CI trigger, no way to bisect a regression | `git init` today, push to a private remote, protect main |
| 🔴 | Audit chain forks under concurrent writes | `latest_hash()` reads the head, then the caller inserts. Two simultaneous requests read the same head and both write `previous_hash = H`. `verify_chain` then reports `broken_link` — a *false tamper alarm* on an untampered database. A demo will not show this; a load test will | Serialise appends with a `SELECT … FOR UPDATE` on a single chain-head row, or a Postgres advisory lock; add a concurrency test that writes 100 entries from 10 threads and verifies |
| 🔴 | No enforced authentication or authorisation | Every endpoint is open. `core/security.py` has PBKDF2 and signed tokens; nothing calls them. See gap 4 above | OIDC + RBAC in Phase 4; actor derived from a verified token only |
| 🔴 | Non-reproducible builds | `requirements.txt` uses ranges. `scikit-learn>=1.5,<2.0` means a rebuilt image can load a joblib bundle pickled by a different minor version — the classic silent-corruption failure. The shipped model was trained on sklearn 1.7.2 / Python 3.13 while the Dockerfile targets 3.11 | Lockfile (uv or pip-tools), exact pin for scikit-learn and joblib, assert the training sklearn version at model load |
| 🔴 | Aggregates computed in Python, not SQL | `exchange_summary` loads every item, demand and match into memory. `generate_matches` is O(items × demands) in a Python loop. At a 1.8 M-unit maintenance base — the number the pitch leads with — this does not degrade, it stops | Push aggregation into SQL, add summary tables, replace the match loop with SQL candidate generation plus scored top-k |
| 🔴 | No model governance | The model is a joblib blob on a Docker volume. No registry, no signed artefact, no promotion gate, no drift detection, no rollback path, no model card | Versioned artefact store, checksum, staged promotion, a drift job, a published model card |
| 🟠 | No CI/CD | 82 tests that nothing runs automatically are 82 tests that will rot | GitHub Actions: ruff, pytest with coverage gate, vitest, `vite build`, `pip-audit`, `npm audit`, Docker build, on every PR |
| 🟠 | No observability | Plain-text logs to stdout, no request correlation id, no metrics endpoint, no tracing. You cannot answer "why was that prediction slow" or "how often do we abstain" | JSON logs with request id, OpenTelemetry, Prometheus counters for prediction latency, class distribution and abstention rate |
| 🟠 | Default secrets | `SECRET_KEY=dev-only-insecure-key-change-me` and `POSTGRES_PASSWORD=change_me` are the Compose defaults, so the documented happy path deploys with them | Fail startup if `SECRET_KEY` is the default and `DEBUG` is false; secrets from a vault |
| 🟠 | Docker Compose unverified | The README states Docker was unavailable during the build. The one-command demo has never actually run | Verify on a clean machine and record it in CI |
| 🟠 | Personal data unclassified | `ServiceEvent.technician` and audit `actor` hold named individuals. That is GDPR-scoped personal data inside an append-only log that is designed never to be edited | Pseudonymise to a stable employee id, document the lawful basis and the erasure story before any pilot |
| 🟡 | Safety-critical list duplicated | `app/api/components.py` hardcodes `["Steel Rope","Brake","Governor"]` instead of calling `is_safety_critical`. Two sources of truth for a safety rule | One constant, referenced everywhere; a test that asserts they agree |
| 🟡 | No i18n, no accessibility audit | KONE operates in ~60 countries. Field UIs are used in gloves, in poor light, by non-English speakers | Extract strings, audit contrast and target sizes, keyboard paths |
| 🟡 | No backup, retention or DR story | An append-only compliance record with no restore drill is a compliance liability | PITR, documented retention, a rehearsed restore |

---

## 6. Aligning to KONE

If KONE is going to take this in, it has to land inside a strategy they have already
committed to publicly. It does — but the framing in the current pitch leaves most of
that value on the table.

### Rise, 2025–2030

KONE's strategy period names four thrusts: accelerate digital, drive modernization,
win residential, and cut carbon. This product sits squarely on three of them.
Modernization is the exact moment components are removed — the instant the product
acts. Cutting carbon is the outcome it measures. Accelerating digital service is the
mechanism. Say that explicitly on the first slide; right now the deck argues from
waste, which is a problem statement, rather than from Rise, which is a mandate with
budget attached.

### The targets the product should be measured against

KONE has committed to cutting emissions from its own operations by 50% by 2030 and —
the one that matters here — reducing emissions from its *products' materials and
lifetime energy consumption by 40% per product ordered* against a 2018 baseline,
alongside carbon-neutral operations by 2030. Operations are largely solved: 99.6%
renewable electricity, manufacturing emissions down 86%. The hard, unsolved part is
materials and the value chain.

> **Reframe the impact metric.**
> "Avoids 1.7 tonnes of CO₂ per site per quarter" is a number nobody at KONE is
> accountable for. **"Reduces material carbon intensity per product ordered, against
> the 2018 baseline"** is a number in their strategy document. Same maths, a metric
> that maps to an existing target owner. Make the dashboard emit that figure directly.

### Integrate with what already exists

KONE 24/7 Connected Services already streams condition data off the maintenance
base, and KONE runs a public API Portal where partners register sandbox applications
and test against virtual elevators on the KONE IoT platform. Do not propose a
parallel IoT stack. Propose an adapter that consumes KONE's existing telemetry and
equipment identity, and register a sandbox app so the integration story is
demonstrated rather than asserted. That turns the deliberate 501 on `/sensors/{id}`
from a gap into a named, scheduled integration point.

### The regulatory window is the strongest argument, and the deck misses it

| Instrument | Status | What it means for this product |
|---|---|---|
| Construction Products Regulation (EU) 2024/3110 | In force Jan 2025; most provisions applying from Jan 2026 | Embeds a construction-specific Digital Product Passport aligned to ESPR. Lift components are construction products. This *is* the Component Passport, with a legal definition attached |
| EU DPP Registry | Launched 20 July 2026, with a test environment | There is now a real registry to conform to. A passport that exports to it is a compliance asset; one that does not is a private database |
| CSRD, post-Omnibus | Omnibus adopted 24 Feb 2026, in force 18 Mar 2026; transposition by Mar 2027 | Scope narrowed to >1,000 employees and >€450 M turnover — KONE remains firmly in scope. Simplified ESRS cut E5 datapoints by ~60% and added a critical-raw-materials metric |
| ESRS E5-4 / E5-5 | The operative disclosure requirements | Mass-based resource inflows and outflows. Requires a kilogram ledger the platform does not yet keep. The new critical-raw-materials metric points straight at control boards |
| BRSR Core (India) | Applies to KONE's Indian operations | Principle 2 asks for reclaimed products as a share of products sold — a direct output of this platform |
| **EU AI Act, Annex I** | Annex I obligations deferred to **2 August 2028** by Regulation (EU) 2026/1744 | See below. This is the most important line in the table |

> **⚠️ The AI Act question you will be asked.**
> The Lifts Directive 2014/33/EU is listed in Annex I of the AI Act. An AI system
> that is a *safety component* of a product covered by Annex I legislation requiring
> third-party conformity assessment is classified high-risk, with obligations
> applying from 2 August 2028.
>
> Your product is almost certainly *not* that — it advises on the disposition of
> components that have already been removed, not on the operation of a lift. But
> "almost certainly" is not an answer to give KONE's quality organisation. Write the
> classification argument down, and note that the argument rests entirely on the
> safety gate: the moment an AI output is allowed to return a rope, brake or governor
> to service without human inspection and conformity assessment, the classification
> flips. The gate is not a UX feature. It is the regulatory boundary of the product,
> and it should be presented that way.

### Ground the passport in the standards you already name

ISO 4344:2022 sets minimum requirements for lift steel wire ropes; discard criteria
for wire ropes are their own body of practice; EN 81-80 (SNEL) is the rulebook for
improving the safety of *existing* lifts and is exactly the framework a
modernization decision sits inside; ISO 281 gives bearing L10 life, which is the
right basis for sheave and motor design envelopes. None of these appear in the code.
Encoding them as a `standards_basis` field per component type — clause cited, shown
in the passport, referenced by the safety gate — is what converts "standards-based"
from a slide adjective into something an auditor can click on.

---

## 7. The plan, phase by phase

Seven phases, sequenced so each one unblocks the next. The ordering is deliberate:
credibility before features, because a KONE reviewer will discount every feature
built on a model they do not trust. Durations assume the four of you part-time.

---

### P0 — Make it real

**Week 1**

Before adding anything, make what exists reproducible, verifiable and honest. This
phase adds no features and is the highest return per hour in the entire plan.

- `git init`, private remote, protected main, conventional commits. Nothing else in
  this document is safe to do without it.
- Lock Python dependencies (uv or pip-tools). Pin `scikit-learn` and `joblib`
  exactly. Add a version assertion at model load so a mismatch fails loudly instead
  of unpickling something subtly wrong. Align the Dockerfile's Python to the version
  the model was trained on.
- CI on every push: ruff, pytest with a coverage floor, vitest, `vite build`,
  `pip-audit`, `npm audit`, Docker build.
- Actually run `docker compose up` on a clean machine. Record it. The README
  currently admits this was never verified.
- Fail startup when `SECRET_KEY` is the shipped default and `DEBUG` is false.
- Write `scripts/derive_impact_claims.py` that prints every financial and carbon
  figure used in the pitch, with its assumptions, from the same constants the API
  uses. If a number cannot be printed by that script, it comes off the slide.
- Truth-up the deck: either remove "+ calibration" and "calibration visualisations",
  or accept that P1 must land before you next present. Remove the ISO/EN claim until
  P3 delivers it.

**Done when:** a clean clone plus one command produces a working demo; CI is green
and blocks merges; every pitch number is printed by a script, not typed into a slide.

#### P0 deliverables

- [x] Git repository initialised (no remote configured yet — this environment has no hosted git provider access; `main` branch protection needs a remote to protect)
- [x] `backend/requirements.lock` committed; `scikit-learn` (1.9.1) and `joblib` (1.6.0) pinned exactly
- [x] Version assertion at model load — mismatch raises (`ModelVersionMismatchError`), does not silently unpickle
- [x] Dockerfile Python version aligned with the training environment (3.12)
- [x] `.github/workflows/ci.yml` — ruff, pytest + coverage floor, vitest, `vite build`, `pip-audit`, `npm audit`, Docker build
- [ ] CI required on every PR; merges blocked on red — requires a hosted remote + branch-protection settings, neither of which exist yet
- [x] `docker compose up` verified — **run for real on 2026-09-21**, no `.env`, exactly the documented one-command path. All three services build and reach healthy; migrations apply to head; the fleet seeds into Postgres (60 components, 326 audit rows); the frontend serves and its nginx tier proxies `/api` correctly. It surfaced one real defect, now fixed: the Postgres host port defaulted to 5432 and collided with a locally installed Postgres, failing the headline command with a bare "address already in use". Default is now 55432, overridable via `POSTGRES_PORT`
- [x] Startup guard: refuse to boot with the default `SECRET_KEY` when `DEBUG=false`
- [x] `backend/scripts/derive_impact_claims.py` prints every pitch figure with assumptions (originally flagged the per-site-per-quarter figure as NOT DERIVABLE — see the follow-up below)
- [x] Deck corrected — no pitch-deck file exists in this repo, so the correction was applied to the README's own capability claims instead; also fixed audit-chain concurrency (§5 finding) and the duplicated safety-critical type list (§5 finding)
- [x] `CONTRIBUTING.md` with branch, commit and review conventions
- [x] **P0 follow-up, added later:** the per-site-per-quarter figure is no longer NOT DERIVABLE. `app.services.site_impact_service` builds the site model this always needed — for each site, `N = current backlog + forecast arrivals next quarter` (reusing the P2 survival forecaster), and `value/co2 = N × that site's own historical average per assessed component`, falling back to the fleet-wide average (and saying so) when a site has no assessment history yet. Exposed at `GET /api/v1/forecast/site-impact`, surfaced on the Forecast page, and printed by `derive_impact_claims.py` with a per-site breakdown plus a fleet-wide average. Verified end to end against a real Postgres instance, not just SQLite. On the 60-component demo fleet the fleet average comes out to ≈₹78,000 / 0.33 t CO₂ per site per quarter — the *mechanism* is now real and reproducible; the *magnitude* will only resemble the original ₹4.9L/1.7t slide guess once it runs against a fleet the size a real KONE site carries, and the script says so rather than implying the demo number validates the slide

---

### P1 — A model a safety engineer will accept

**Weeks 2–4**

Close the calibration claim, add the ability to say "I don't know", and make the
cost of each error type explicit. This is the phase that changes how the product is
received.

- **Calibration.** Wrap the Random Forest in `CalibratedClassifierCV` (isotonic,
  5-fold) fitted on a dedicated calibration split. Report per-class Brier score and
  expected calibration error. Expose `/api/v1/model/calibration` returning
  reliability bins, and render the reliability diagram in the analytics page. This
  single change makes the confidence number on the technician's screen mean what it
  appears to mean.
- **Abstention.** Add a fifth outcome, `DEFER_TO_INSPECTION`, triggered when the
  calibrated top-class probability falls below a tuned threshold or a conformal
  prediction set contains more than one label. Report the abstention rate as a
  headline metric. A system that refuses 15% of cases and is right 95% of the rest is
  worth more to KONE than one that answers everything at 82%.
- **Cost-sensitive decisions.** Write down an explicit 4×4 cost matrix — optimistic
  errors cost more than conservative ones, and cost more again on safety-critical
  types — and tune decision thresholds against expected cost rather than macro F1.
  Report expected cost per decision alongside accuracy.
- **Honest validation.** Add a cohort-based split (by installation year) beside the
  random split and publish both. Expect the numbers to drop; publishing the drop is
  the credible move.
- **Better explanations.** Permutation importance alongside Gini. SHAP
  `TreeExplainer` for genuine per-prediction attribution, clearly labelled as a
  second method beside the existing envelope-deviation view.
- **Drift harness.** A scheduled job comparing live feature distributions to the
  training distribution (PSI or KS), with a threshold that raises an alert.
- **Model card.** Intended use, out-of-scope use, training data provenance, metrics
  by class and by cohort, known failure modes, human-oversight requirement. Shape it
  like AI Act Annex IV technical documentation now, so it is reusable if the
  classification question ever goes the other way.

**Done when:** the reliability diagram tracks the diagonal within ±5% across bins and
is published in the UI; abstention rate and expected cost per decision appear on the
model metrics endpoint; the cost matrix is a reviewed artefact, not a constant buried
in code.

#### P1 deliverables

- [x] `CalibratedClassifierCV` (isotonic, 5-fold) in the training pipeline, fitted on a held-out calibration split (the `dev` split; `conformal_calib` and `test` stay disjoint from it)
- [x] Per-class Brier score and expected calibration error written to `models/metrics.json`
- [x] `GET /api/v1/model/calibration` returning reliability bins
- [x] Reliability diagram rendered on the Analytics page
- [x] `DEFER_TO_INSPECTION` outcome implemented end to end — API, persistence (migration 0003), UI
- [x] Conformal prediction sets (split-conformal / LAC) driving abstention, OR'd with a tuned confidence threshold
- [x] Abstention rate reported as a headline model metric (17.8% on the current model)
- [x] 4×4 cost matrix documented and reviewed as its own artefact (`app/ml/cost_matrix.py`) — reviewed in code review here; still needs sign-off from an actual quality/safety engineer before the weights are anything but illustrative
- [x] Decision thresholds tuned to expected cost; expected cost per decision reported (`cost_analysis` on every prediction); `recommendation` itself intentionally stays the argmax choice for auditability, with the cost-optimal alternative reported alongside it rather than substituted in
- [x] Cohort split by installation year, published alongside the random split (81.75% → 71.73%)
- [x] Permutation importance computed and exposed beside Gini
- [x] SHAP `TreeExplainer` per-prediction attribution, labelled as a second method
- [x] Drift job (PSI or KS) with an alerting threshold (`scripts/check_drift.py`, exit-code-driven; verified it fires on a synthetic shift and stays quiet on the real split — nothing schedules it against live traffic yet, since there is none)
- [x] `docs/model-card.md` in Annex IV shape
- [x] Tests: calibration bins sum correctly (`test_model_info_and_metrics_endpoints`), abstention triggers at the threshold (`test_predictions.py`, 3 dedicated cases), safety gate still fires on all three critical types (pre-existing, re-verified against the calibrated model)

---

### P2 — Forecasting and refurbishment capacity

**Weeks 4–8**

Build the missing half of the pitch. This turns a scoring tool into a planning
platform, and it is the capability the service organisation actually buys.

- **Time-to-disposition model.** A survival model — Weibull AFT or a
  gradient-boosted survival forest — over the component cohort, producing
  P(component reaches REFURBISH-or-worse within h) for h ∈ {3, 6, 12, 24} months,
  with intervals. The existing simulator already has a latent wear trajectory;
  extend it to emit time-indexed observations so there is something to fit.
- **Fleet EOL forecast API.**
  `GET /api/v1/forecast/eol?horizon=&group_by=type|site|region` returning expected
  removals per component type per quarter with prediction intervals.
- **Capacity planner.** Given forecast removals, per-type refurbishment labour hours
  and declared workshop capacity, output utilisation by quarter, the bottleneck
  component type, and a recommended intake schedule. This is literally the slide's
  promise: "plan refurbishment capacity ahead."
- **Make the Exchange forward-looking.** Match *forecast* supply against *forecast*
  demand, not only present stock — that is what lets a planner commit to a recovered
  part before it has been removed.
- **Backtest.** Hold out a cohort, forecast it, report MAPE per component type.
  Publish the error, do not hide it.
- **UI.** A Forecast page: stacked quarterly removals by type, a capacity
  utilisation strip that reads red where demand exceeds the workshop, and a named
  bottleneck.

**Done when:** a planner can ask "what is coming off the fleet in Q3 and can we
absorb it?" and get an answer with an interval; backtest MAPE is published per
component type; the capacity plan respects a stated constraint and names the
bottleneck.

#### P2 deliverables

- [x] Simulator extended to emit time-indexed observations per component (`generate_survival_dataset`; the classifier's dataset is left byte-identical so its published metrics still reproduce)
- [x] Survival model trained (Weibull AFT, hand-written over scipy rather than a new dependency) with intervals from the coefficient covariance — fitted k = 1.51, i.e. hazard rises with age as wear-out should
- [x] P(reaches REFURBISH-or-worse within h) for h ∈ {3, 6, 12, 24} months
- [x] `GET /api/v1/forecast/eol` with `horizon` and `group_by=type|site|region`
- [x] `GET /api/v1/forecast/capacity` — utilisation by quarter, bottleneck type, levelled intake schedule that carries un-absorbable work forward
- [x] Refurbishment labour-hour and workshop-capacity constants in config, documented as estimates
- [x] Recovery Exchange matches forecast supply against forecast demand (`GET /api/v1/forecast/supply-demand`)
- [x] Backtest harness; MAPE published per component type in `models/forecast_metrics.json` (13.1% overall; 1.5% at 6m, 23.4% at 3m where event counts are small — published, not hidden)
- [x] `Forecast.jsx` page — stacked quarterly removals, capacity utilisation strip, named bottleneck
- [x] Sidebar and navigation entry for the Forecast page
- [x] Tests: forecast endpoint shape, horizon bounds, capacity plan respects a stated constraint — plus Weibull AFT parameter-recovery tests, since the model is hand-written

**Not in the original list, added because building it surfaced the need:** the
forecast is only valid for the *at-risk* population. A component already
assessed REFURBISH-or-worse has crossed the threshold being forecast, and
including it piled 34 of 40 removals into quarter one. `split_fleet` now
reports those separately as **current backlog** and queues them ahead of the
first quarter in the capacity plan. See `docs/forecasting.md` §4.

---

### P3 — The compliance engine

**Weeks 8–11**

Turn "auditable lifecycle data" from a hash chain into filed disclosures and a
conformant Digital Product Passport. This is where the regulatory window becomes
revenue.

- **Material-flow ledger.** A new `material_flow` table: component, material,
  mass_kg, from_state, to_state, date, source. Every lifecycle transition writes one
  row. Mass stops being a read-time config lookup and becomes a recorded fact.
  Without this table there is no E5 report — this is the single most important schema
  change in the plan.
- **ESRS E5 output.** `/api/v1/reports/esrs-e5?period=` producing E5-4 resource
  inflows (including secondary/reused share) and E5-5 resource outflows in tonnes by
  material, plus the new critical-raw-materials metric for electronics. Each report
  carries the hash range of the audit entries it was derived from, so an assurance
  provider can re-derive it independently.
- **BRSR output.** The equivalent for KONE's Indian entity: Principle 2
  reclaimed-product share, Principle 6 waste and circularity.
- **DPP conformance.** Add a DPP identifier, economic-operator field and a
  registry-shaped export mapped to CPR (EU) 2024/3110. Upgrade the QR payload from a
  localhost URL to a resolvable, versioned, persistent identifier — a passport whose
  link dies when the demo server stops is not a passport.
- **Standards basis.** A per-component-type `standards_basis` field citing ISO
  4344:2022 for ropes, wire-rope discard practice for the safety gate's rope path,
  EN 81-80 hazard references for modernization context, ISO 281 L10 life for
  bearing-bound types. Show the clause in the passport. This is the claim the deck
  already makes and the code does not support.
- **Fix the chain, then anchor it.** Serialise appends to close the concurrency fork
  found in §5, then publish the daily head hash to an external append-only store so
  tamper evidence survives a database administrator.

**Done when:** a draft E5-4/E5-5 table is generated from real rows, in tonnes, for a
chosen period; the DPP export validates against a published schema and resolves
through a persistent identifier; every standards citation in the UI resolves to a
named clause; a 10-thread, 100-write concurrency test leaves the chain valid.

#### P3 deliverables

- [x] `material_flow` table + Alembic migration 0004 (component, material, mass_kg, mass_source, from_state, to_state, direction, outflow_route, is_secondary, date, actor, source, audit_hash). Identifying attributes are denormalised so the ledger outlives edits to the component row
- [x] Every lifecycle transition writes a material-flow row — component create/update, service events, recovery listing and match acceptance all route through `material_flow_service.record_transition`. Each row is pinned to the audit entry recording the same transition
- [x] `GET /api/v1/reports/esrs-e5?period=` — E5-4 inflows with secondary/reused share, E5-5 outflows split diverted-from-disposal vs directed-to-disposal, in tonnes by material. Period accepts a year, quarter, month or explicit range; CSV export at `/reports/esrs-e5.csv`
- [x] Critical-raw-materials metric, by substance and by component type (`CRM_MASS_FRACTION`, referenced to Regulation (EU) 2024/1252 Annex I) — prototype per-material averages, labelled as such
- [x] Each report embeds the audit hash range it was derived from (`derivation`: ledger rows, audit entry count, first/last hash, chain head at generation, and the re-derivation procedure)
- [x] `GET /api/v1/reports/brsr?period=` — Principle 2 reclaimed share, Principle 6 waste and circularity
- [x] `dpp_id`, `economic_operator` and `economic_operator_id` on `Component` (migration 0005), each falling back to a deployment-wide default
- [x] `GET /api/v1/passports/{id}/dpp` registry-shaped export mapped to CPR (EU) 2024/3110 — **registry-shaped, not registry-accepted**: no EU DPP Registry credentials exist in this build, and `registry_status` reports `NOT_REGISTERED` rather than implying conformance
- [x] QR payload upgraded to a resolvable, versioned, persistent identifier (`urn:kone:dpp:1:{component_id}` resolved via `DPP_RESOLVER_BASE_URL`). No longer encodes a localhost URL; legacy payloads still scan
- [x] `standards_basis` per component type — ISO 4344:2022, ISO 281:2007, ISO 7465:2007, EN 81-20/50:2020, EN 81-80:2019, IEC 60034-1:2022. **Clause pointers are flagged `CLAUSE_UNVERIFIED`**: the purchased standards were not available to this build, so standard identity is verified but clause numbers are good-faith locators pending confirmation
- [x] Standards citation rendered in the passport UI, with the unverified-clause badge shown on every affected citation
- [x] Audit-chain append serialised via the `audit_chain_lock` row (landed in P0; re-verified here)
- [x] Concurrency test: 10 threads × 100 writes, chain verifies valid — and confirmed to *fail* (chain forks at record 6) with the lock disabled, so the test is known to be load-bearing
- [x] Daily head-hash anchoring — `ChainAnchor` (migration 0006) + `scripts/anchor_chain_head.py`. **Mechanism complete, external witness NOT configured**: `CHAIN_ANCHOR_WEBHOOK_URL` is unset, so the API reports `NOT PROTECTED against a database administrator` instead of implying a protection that is not in place. Exit code 1 makes that visible to a scheduler
- [x] `docs/compliance.md` mapping each disclosure requirement to its data source, plus the re-derivation procedure and §10 "what would have to be true to actually file"

---

### P4 — Production hardening

**Weeks 11–15**

Everything that separates a prototype from something an enterprise security review
will pass. Identity first, because the audit trail depends on it.

- **Identity and roles.** OIDC — Entra ID is the realistic target for a KONE
  deployment — with five roles: technician, supervisor, refurbishment planner,
  sustainability controller, and read-only auditor. The audit actor comes from the
  verified token and nowhere else. Delete the `X-Actor` path.
- **Multi-tenancy.** Scope by frontline unit and country, with row-level enforcement
  and tests that prove cross-tenant reads fail.
- **Observability.** JSON logs with a request id threaded through every layer,
  OpenTelemetry traces, Prometheus metrics for prediction latency, predicted-class
  distribution, abstention rate and chain-verification results. Alerting on drift and
  on verification failure.
- **Scale.** Move dashboard aggregation into SQL, add summary tables refreshed on
  write, partition the event tables, replace the O(n×m) Python matching loop with SQL
  candidate generation plus scored top-k. Then load-test at 1.8 M components and tens
  of millions of events — the number the pitch leads with should be the number the
  system is tested at.
- **Security.** Secrets from a vault, dependency scanning and an SBOM in CI, rate
  limiting, security headers on the nginx tier, a documented threat model, and a
  personal-data review covering technician names in an append-only log.
- **Resilience.** Point-in-time recovery, a documented retention policy, and a
  rehearsed restore drill.

**Done when:** SSO login works and every audit row carries a verified subject; p95
under 300 ms on list and dashboard endpoints at fleet scale; zero high-severity CVEs;
restore drill documented with a timestamp.

#### P4 deliverables

- [~] **Partial.** Token issuance and validation middleware are wired (`app/api/deps.py::get_current_user`, `app/api/auth.py`), and the login endpoint uses the OAuth2 password-form shape so Swagger's own Authorize button works against it. **This is local authentication against the platform's own `users` table, not OIDC/Entra ID** — that needs a company tenant this environment has no access to. Only how the token is *obtained and validated* would change; no endpoint that consumes an identity would
- [x] Five RBAC roles enforced: technician, supervisor, refurbishment planner, sustainability controller, read-only auditor (`Role` in `app/utils/enums.py`, `deps.require_roles`). The rule enforced everywhere: a read-only auditor reads everything and writes nothing. Narrower rules gate account provisioning (supervisor) and chain anchoring (supervisor or sustainability controller)
- [x] Audit actor derived from the verified token only; `X-Actor` path deleted. A **second** spoofing path was found during this work and closed too: `MatchDecision.actor` let the request *body* name the decision-maker on recovery accept/reject, so a caller did not even need to forge a header. Both are covered by tests verified to fail when the old behaviour is simulated
- [x] Accounts are provisioned, never self-registered — an endpoint letting a caller choose their own role is a privilege-escalation hole wearing a registration form. `POST /auth/users` requires a supervisor; `scripts/seed_users.py` bootstraps the first five
- [x] Public-by-design surface documented and tested: `/health` and the QR passport endpoints stay unauthenticated, because a technician scanning a label in a basement machine room has no login. Gating them would break the one thing the QR code exists to do
- [x] **Added after the above landed, not originally listed here:** self-service signup (`POST /auth/signup`, emailed one-time code). Does not reopen the privilege-escalation hole the line above closed — the request has no `role` field, a self-registered account always lands on `technician`, and it likewise gets no default tenant (see the next line) until a supervisor assigns one
- [x] Tenant column + row-level scoping by frontline unit and country — `country` is a hard boundary (a mismatch on any direct lookup is a 404, identical to "does not exist", never a 403 — see `app/core/tenancy.py`'s module docstring for why); `frontline_unit` is a soft default overridable with `?all_units=true`. The Recovery Exchange is deliberately country-scoped only, not unit-scoped — routing a recovered part across units within a country is the point of it. `SUSTAINABILITY_CONTROLLER` and `READ_ONLY_AUDITOR` bypass both, because a country-scoped fleet-wide disclosure or chain verification is not actually fleet-wide. Migration `0009_tenancy`; validated against real Postgres (not just SQLite), including that a supervisor's default dashboard view genuinely differs from a global role's
- [x] Tests proving cross-tenant reads return 404/empty — `tests/test_tenancy.py`, 10 tests: cross-country component reads, cross-country dashboard exclusion, the frontline-unit soft-default and its override, and the Recovery Exchange's deliberate non-unit-scoping in both directions
- [x] Structured JSON logging with a request id threaded through every layer — `app/core/logging_config.py` (one JSON object per line, `LOG_FORMAT=human` opt-out for a developer terminal), `app/core/request_context.py` (a `ContextVar`, not thread-local — ASGI request handling hops `await` points on the same thread), `app/core/middleware.py` (accepts an inbound `X-Request-ID` or mints one, echoes it on the response)
- [x] OpenTelemetry tracing on the API and inference path — hand-rolled in `app/core/telemetry.py` rather than the `opentelemetry-instrumentation-fastapi`/`-sqlalchemy` auto-instrumentation packages, which pin to specific FastAPI/SQLAlchemy version ranges this build's pinned versions (see `requirements.lock`) sit outside of: one span per request (a `@app.middleware("http")`), one child span per SQL statement (a `before_cursor_execute`/`after_cursor_execute` pair on the engine, timed via the connection's own `info` scratch dict). Spans are created regardless of configuration and cost nothing extra when dropped; `OTEL_EXPORTER_OTLP_ENDPOINT` sends them to a real collector, `OTEL_CONSOLE_EXPORT` prints them, neither means they are silently discarded
- [x] `GET /metrics` — prediction latency, predicted-class distribution, abstention rate, chain-verification result. `app/core/metrics.py` (Prometheus histogram/counters/gauge) + `app/api/metrics.py`. Deliberately unauthenticated, matching standard Prometheus scrape practice — `docs/threat-model.md` §3.4 flags this as needing network-layer restriction in a real deployment, not application auth
- [x] Alerting on drift breach and on chain-verification failure — `app/core/alerting.py` (a shared webhook-POST helper, extracted from the pattern `scripts/anchor_chain_head.py` already used). `scripts/check_drift.py` now posts to `DRIFT_ALERT_WEBHOOK_URL` on a significant shift; new `scripts/verify_chain.py` runs the same tamper-evidence check as `GET /audit/verify` on a schedule and posts to `CHAIN_VERIFY_ALERT_WEBHOOK_URL` on a break. Both webhooks are empty by default (prints only, nobody paged) — same "record the gap rather than hide it" pattern as the chain-anchor webhook
- [x] Dashboard aggregation moved into SQL; summary tables refreshed on write — every `app/api/dashboard.py` endpoint now runs `GROUP BY`/`COUNT`/`AVG`/`percentile_cont` instead of loading components into Python. `Component.latest_recommendation`/`latest_confidence` (migration `0011_cached_recommendation`) are the "summary column refreshed on write" version of this, refreshed in `prediction_service.assess_component` the same way `health_score` already was — added mid-pass after a real load test showed the first SQL rewrite still cost `GET /dashboard/summary` a 1.75s p95 via a `MAX(id) GROUP BY` join against the full predictions table. A literal separate summary *table*, refreshed transactionally per tenant, is recorded as the next increment in `docs/database-scale.md` §4, not done in this pass
- [x] Event tables partitioned — `service_events` is range-partitioned by year on PostgreSQL (migration `0010_partition_service_events`; a documented no-op on SQLite, which has no native partitioning and backs only tests/dev). `audit_logs` was deliberately **not** partitioned: Postgres requires a partitioned table's uniqueness constraints to include the partition key, which would force `current_hash`'s global uniqueness into a weaker `(current_hash, timestamp)` constraint on the one table where changing a uniqueness guarantee untested is least acceptable — see the migration's own docstring and `docs/database-scale.md` §4
- [x] Matching rewritten as SQL candidate generation + scored top-k — `recovery_service._candidate_items_for_demand`/`_candidate_demands_for_item` filter by component type (a hard, all-or-nothing requirement in `score_match`) and country in SQL before any Python scoring runs, turning the O(items × demands) full cross-product the audit flagged into O(matching candidates). `exchange_summary` also moved from three full-table Python loops to SQL `GROUP BY`s
- [x] Load test at 1.8 M components / tens of millions of events; p95 < 300 ms on list and dashboard — run at **200,000 components / ~600,000 service events** against real Postgres (`scripts/load_test.py`), not the full 1.8M: `GET /dashboard/summary` p95 dropped from 1,747ms to 152–213ms, `/components`, `/recovery/summary` and `/dashboard/safety-queue` are all single-digit-to-low-double-digit milliseconds — comfortably under 300ms. `/dashboard/analytics` (which deliberately answers ~10 aggregate questions in one round trip) improved 5,431ms → ~1,330–1,395ms p95 but is **not yet under 300ms**. Full measurements, what 200k does and does not prove about 1.8M, and the next optimisation step: `docs/database-scale.md`
- [x] Secrets sourced from a vault; no default secret can boot in production — `app/core/secrets.py`: a `SecretsProvider` protocol, `EnvSecretsProvider` (today's behaviour) and `VaultSecretsProvider` (HashiCorp Vault's KV v2 HTTP API, selected automatically when `VAULT_ADDR`/`VAULT_TOKEN` are set), wired into `SECRET_KEY`/`SMTP_PASSWORD`/`SMTP_USERNAME` resolution. **No live Vault instance was available in this environment** — the provider is unit-tested against a mocked KV v2 response (`tests/test_secrets.py`), not a real server; `DATABASE_URL` embeds its credential in a connection string rather than as a standalone value and is not yet sourced this way either. The default-secret boot guard (`app/main.py::_guard_against_default_secret`) predates this pass and is unchanged
- [x] SBOM generated in CI; dependency scanning blocking on high-severity CVEs — CycloneDX SBOMs for both tiers uploaded as CI artefacts (`pip-audit --format cyclonedx-json` for the backend, `@cyclonedx/cyclonedx-npm` for the frontend — both commands verified to actually run, not just added to the workflow file). **Blocking is not flipped on.** Backend: `pip-audit` currently reports zero findings against `requirements.lock`, but pip-audit has no reliable built-in severity filter to gate on. Frontend: `npm audit --audit-level=high` currently finds real, unfixed vulnerabilities (1 high, 1 critical, 5 moderate — `vite`/`esbuild`/`vitest` dev tooling plus a `react-router-dom` open-redirect issue) whose fix needs a `react-router-dom` 6→7 migration (breaking API changes across every route) that this pass deliberately did not force through without the frontend regression testing that deserves. See `docs/threat-model.md` §3.5 for the specific CVEs and why they are recorded as open, not silently deferred
- [x] Rate limiting and security headers on the nginx tier — this API has no nginx tier of its own (the frontend's nginx serves static files and proxies to it; see `frontend/nginx.conf`), so both landed on the FastAPI backend, which is reachable directly regardless of what sits in front of it. Rate limiting: `app/core/rate_limit.py`, an in-memory fixed-window limiter applied to `/auth/login` (10/min default) and `/auth/signup` (5/min default) specifically — not indiscriminately, and deliberately *not* also on `/auth/signup/verify`, whose existing per-challenge `OTP_MAX_ATTEMPTS` cap is the more precise defence and conflicted with a shared IP-based bucket when both were tried together. Documented as single-process/in-memory — correct for the one-worker deployment this ships, needs a shared store (Redis) the moment there is more than one worker. Security headers: `app/core/security_headers.py` (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`, and a locked-down `Content-Security-Policy` on every route except `/docs`/`/redoc`, which need a CDN-loaded Swagger UI a strict CSP would break)
- [x] `docs/threat-model.md` and a personal-data review covering technician names — trust boundaries, an assets table, threats/mitigations/residual-risk across identity, multi-tenancy, data-at-rest, observability and the dependency supply chain, the AI Act pointer, and a dedicated personal-data section. **The personal-data review's conclusion is that this is unresolved, not that it is handled**: `service_events.technician` and `audit_logs.actor` carry names/emails inside an append-only, hash-chained log with no erasure path, and cannot get one without either breaking the chain or pseudonymising at write time — neither implemented in this pass. See `docs/threat-model.md` §4
- [x] PITR configured, retention policy documented, restore drill rehearsed and timestamped — `docker-compose.yml`'s Postgres service now runs with WAL archiving on (`wal_level=replica`, `archive_mode=on`, a dedicated `postgres_wal_archive` volume); `scripts/backup_postgres.sh`/`scripts/restore_pitr.sh` are real, tested scripts, not just documentation. **A real restore drill was run against this build's own live Postgres instance** carrying the 200k-component load-test fleet: a canary row inserted before a recorded timestamp survived a restore-to-that-point-in-time, a second canary inserted after it did not, and — the result that actually matters for this product — the tamper-evident audit chain (326 records) verified as fully intact on the restored instance. Full log output, exact timestamps, the retention policy, and what this drill does *not* cover (shipping backups off-host, a real timed incident runbook): `docs/disaster-recovery.md`

---

### P5 — Field reality and systems integration

**Weeks 15–20**

Meet the technician where they actually are — a machine room with no signal — and
connect to systems KONE already runs.

- **Offline-first PWA.** Manifest, service worker, IndexedDB write queue,
  conflict-safe sync on reconnect. A technician must be able to scan a passport, run
  an assessment against a cached model or a queued request, and record a removal with
  no network at all. This is not polish; machine rooms are basements.
- **KONE integration adapters behind an anti-corruption layer.** Register a sandbox
  application on the KONE API Portal and demonstrate one live call for equipment
  identity. Define adapter interfaces for service-record ingest and spare-parts
  inventory, with contract tests against recorded fixtures. Build to the documented
  APIs; do not assume internals you cannot see.
- **Real logistics costing.** Replace the distance proxy in the match score with a
  carrier rate card plus emissions per tonne-kilometre, so a match that looks good on
  condition but bad on freight is scored honestly — and so the CO₂ number nets out
  transport instead of ignoring it.
- **Durable labelling.** Evaluate DataMatrix against QR for small, oily, curved
  surfaces, and specify a label stock that survives a machine room for twenty years.
  A passport is only as permanent as the thing carrying its identifier.

**Done when:** a full lookup → assess → record-removal cycle completes offline and
syncs cleanly; one live sandbox integration is demonstrated end to end; match scores
include real freight cost and emissions.

#### P5 deliverables

- [x] PWA manifest and installable app shell — `vite-plugin-pwa` (`frontend/vite.config.js`), icons generated from the existing favicon, verified via a real production build (`npm run build` emits `dist/manifest.webmanifest`)
- [x] Service worker with an offline app cache — Workbox, same plugin, precaches every JS/CSS/HTML/image asset (`dist/sw.js`, `dist/workbox-*.js`, confirmed generated)
- [x] IndexedDB write queue for assessments, service events and removals — `frontend/src/offline/db.js` + `outbox.js` (via `idb`), wired into component creation, service events, ad-hoc assessment and recovery-item listing in `frontend/src/api/client.js`. Tested against a real IndexedDB backend (`fake-indexeddb`, since jsdom has none natively) in `frontend/src/test/offline.test.js` — 9 tests covering replay-on-success, mark-failed-on-server-rejection, stop-not-lose-on-still-offline, and never-resync-without-explicit-retry
- [x] Conflict-safe sync on reconnect, with a visible pending-sync state — `frontend/src/hooks/useOfflineSync.js` + `frontend/src/components/OfflineBanner.jsx`, mounted in both the authenticated shell and the standalone QR-scan passport route. "Conflict-safe" is defined precisely for this system's append-heavy writes in `docs/offline-pwa.md` §2, not borrowed from a merge-two-edits model this domain does not need
- [x] Offline passport lookup against a cached record — Workbox `NetworkFirst` runtime caching on the passport/component GET routes; works transparently for axios's XHR calls with no extra client code, since a service worker intercepts same-origin requests regardless of how they were issued
- [x] Native camera scan path with the manual fallback retained — pre-existing (`frontend/src/components/QRScanner.jsx`), confirmed still correct: the manual lookup always renders, the camera is progressive enhancement
- [x] Anti-corruption layer: adapter interfaces for equipment identity, service records, spare-parts inventory — `app/integrations/base.py` (three `Protocol`s), `fixture_adapters.py` (the only concrete implementation), `registry.py` (swap point), `app/api/integrations.py` (the API layer built on the interfaces, not on KONE-shaped types directly)
- [ ] KONE API Portal sandbox application registered — needs a real developer account this environment has no access to
- [ ] One live sandbox call demonstrated end to end and recorded — blocked on the item above
- [x] Contract tests against recorded fixtures for every adapter — `tests/test_integrations.py`: `assert_equipment_identity_contract` / `assert_service_record_contract` / `assert_spare_parts_contract` describe what *any* implementation must satisfy, run today against the fixture adapters, intended to be run against a real adapter before it is trusted
- [x] Carrier rate card + emissions per tonne-km replacing the distance proxy in match scoring — `app/services/logistics_service.py` (illustrative distance bands + a configurable rate card in `app/core/config.py`), wired into `recovery_service.score_match`'s logistics criterion (formerly a same-city/same-country string-match proxy — see that module's docstring for the replacement). Tested (`tests/test_logistics.py`, 9 cases) including that a same-city pairing now outscores a cross-country one *because* freight is cheaper, not because of a string comparison
- [x] CO₂ figures net out transport emissions — `score_match` now reports `net_co2_saving_kg` (estimated CO2 saving minus estimated freight emissions) alongside the existing gross figure, exposed on `RecoveryMatchRead.net_co2_saving_kg`
- [x] DataMatrix vs QR evaluation written up; label stock and print spec chosen — `docs/labelling.md`: recommendation is to keep QR (the components this platform tracks are not small enough for DataMatrix's size advantage to matter), plus a concrete label-stock spec (PET substrate, resin thermal-transfer print, overlaminate, -40°C to +150°C rating) — explicitly a specification to validate against real supplier datasheets, not a purchase order
- [ ] Field test: full lookup → assess → record-removal cycle completed with no network — no physical field test was performed; the mechanism is verified via the automated IndexedDB-backed test suite and a real production build, not a phone in a machine room

---

### P6 — Validation and pilot

**Week 20 onward — the phase that decides everything**

Every number in this project currently describes a simulator. Until the model meets
real removals, nothing else is proven. The README says this plainly and it is right.

- **Shadow mode first.** Run against historical removals with outputs hidden from
  technicians. Measure agreement with what the refurbishment workshop actually did.
  Publish the disagreement analysis, by component type.
- **Design the label now.** The real target is not the simulator's disposition — it
  is what the workshop did with the part and whether it survived in service. Add a
  one-tap outcome capture on the recovery item so a real training set starts
  accumulating from day one of the pilot. Without this, you are still training on
  your own simulator in year two.
- **Pre-register the pilot.** Two sites, one quarter, metrics fixed before the
  start: diversion rate, refurbishment yield, decision-reversal rate, technician
  trust score, value recovered, mass diverted. Pre-registration is what stops the
  pilot from becoming a demo.
- **Governance pack.** Model card, Annex IV-shaped technical file, human-oversight
  standard operating procedure, incident reporting route, DPIA. Assemble it whether
  or not you conclude the system is high-risk — the conclusion is more credible when
  the file exists.
- **Name the stakeholders.** Frontline maintenance operations, the modernization
  business, sustainability and reporting, quality and safety, and IT security. Five
  different questions, five different answers. Quality and safety will ask about the
  gate; sustainability will ask about E5; security will ask about the actor field.

**Done when:** shadow-mode agreement is measured against real removals and published
with its disagreements; outcome capture is live and a real label set is accumulating;
the governance pack exists as a reviewed document set.

#### P6 deliverables

- [x] Shadow mode: predictions computed and stored, never shown to technicians — `Prediction.shadow` (migration `0012_p6_outcome_and_shadow`) + `prediction_service.assess_component_shadow()` + `POST /components/{id}/predict/shadow`. A shadow assessment never updates `Component.health_score`/`latest_recommendation`/`latest_confidence` — the cached columns every technician-facing view reads — and is excluded from `GET /predictions/recent`. **A real leak was found and fixed during this work**: `Component.latest_prediction` (the property backing the passport/component-detail/list views) originally returned the chronologically newest prediction regardless of its shadow flag, which would have surfaced a shadow assessment anyway even though the cached columns were untouched — the property now explicitly skips shadow rows. Tested (`tests/test_pilot_mechanisms.py`)
- [x] Agreement measured against historical removal outcomes, by component type — `app/services/agreement_service.py` + `scripts/agreement_report.py`, reused by `GET /api/v1/pilot/metrics` so the two never drift apart on what "agreement" means. **No real removals exist** — verified instead against three real outcomes recorded through the live API against the seeded demo fleet during this work, which the report correctly matched to their originating predictions and scored (66.7% agreement, one correctly flagged optimistic miss). See `docs/shadow-mode.md` §2 for the exact run
- [x] Disagreement analysis published, including the cases the model got optimistically wrong — same report: `optimistic_misses` and a full `disagreements` list, with the optimistic-miss definition (a REUSE/REFURBISH recommendation whose real outcome was FAILED_INSPECTION/DISPOSED/RECYCLED) matching the asymmetry the original build audit's confusion-matrix discussion named as the one that matters more than accuracy
- [x] One-tap outcome capture on the recovery item (what the workshop did, whether it survived) — `RecoveryItem.workshop_outcome`/`survived_in_service`/`outcome_notes`/`outcome_recorded_at`/`outcome_recorded_by` + `POST /recovery/items/{id}/outcome`, audited (`AuditAction.OUTCOME_RECORDED`), a fixed small vocabulary (`WorkshopOutcome` enum) rather than free text so it aggregates into a usable label without an NLP step
- [ ] Real-label training set accumulating from day one of the pilot — the capture mechanism exists and works; there is no pilot yet for it to accumulate from
- [x] Pre-registered pilot protocol: 2 sites, 1 quarter, metrics fixed in advance — `docs/pilot-protocol.md`. The protocol, scope and metric definitions are fixed; the actual sites, dates and pass/fail thresholds are explicitly left for a real pilot partner to confirm, not invented here
- [x] Pilot metrics instrumented: diversion rate, refurbishment yield, decision-reversal rate, technician trust score, value recovered, mass diverted — all six live at `GET /api/v1/pilot/metrics` (`app/services/pilot_service.py`), computed from real data rather than promised as a future report. `technician_trust_rating` (1-5, `POST /predictions/{id}/feedback`) was added specifically because it is the one metric nothing else in this system could derive. Tested end-to-end through the real API (`tests/test_pilot_metrics.py`, 7 cases: assessed components, recorded outcomes, ratings, and an accepted match all flow through to the right numbers)
- [x] Governance pack: model card, Annex IV-shaped technical file, human-oversight SOP, incident reporting route, DPIA — `docs/governance-pack.md`, pointing to the existing model card and mapping Annex IV's sections to where each already lives in this repository. The human-oversight SOP and incident-reporting route are concrete (the safety gate, the abstention path, the two alert webhooks); the DPIA section is deliberately a structure plus the one substantive finding (`docs/threat-model.md`'s unresolved erasure tension), not a completed assessment against a data controller that does not exist yet
- [x] AI Act classification argument written down and reviewed — `docs/ai-act-classification.md`, expanded from the existing `plan.md` §6 / `docs/threat-model.md` §5 pointer into its own document. **"Reviewed" means reviewed in this document's own drafting, explicitly stated as such** — no qualified external legal/regulatory review has occurred, and that review (not this document) is what should precede anyone relying on the conclusion
- [x] Stakeholder map with the specific question each group will ask — `docs/stakeholders.md`: the five named groups, the specific question each will ask, and — matching this project's own honesty pattern — what each would push back on in the system *today*, not a generic RACI chart
- [ ] Retraining plan on real labels, with a promotion gate — the gate half is real and tested: `scripts/promotion_gate.py` compares a candidate model's metrics against the deployed one and blocks promotion on regression in random-split F1, cohort/temporal F1, abstention rate, or calibration (mean Brier score); verified to both approve an unchanged candidate and block a deliberately regressed one. **The retraining half does not exist**: there is no pipeline that consumes `agreement_report.py`'s accumulated real-label outcomes and produces a candidate model automatically — real follow-on engineering once there is enough real-label data to make retraining meaningful, which today there is not (see `docs/shadow-mode.md` §3)

---

## 8. Next seven days

In order. None of these takes longer than a day.

- [x] `git init`. Push to a private remote still pending — no hosted git provider is reachable from this environment.
- [x] Lock and pin dependencies; assert the scikit-learn version at model load.
- [x] Stand up CI with the tests that already exist.
- [x] Run `docker compose up` on a clean machine and fix whatever it shows — done 2026-09-21. What it showed: the default Postgres host port 5432 collides with any locally installed Postgres, so the documented one-command demo died on `address already in use`. Fixed by defaulting to 55432. Full stack then verified healthy end to end.
- [x] Write the concurrency test that proves the audit-chain fork, then fix it with a chain-head lock (`audit_chain_lock` table + serialising `UPDATE`, not a Python-level lock — see `app/services/audit_service.py`).
- [x] Write `derive_impact_claims.py`; correct or remove any slide number it cannot print. (It flags the per-site-per-quarter figure as not derivable; there being no deck file in this repo, that correction has nowhere else to land yet.)
- [ ] Remove the calibration and ISO/EN claims from the deck, or commit to landing P1 and P3 before the next presentation. Calibration is no longer a false claim — P1 landed it. ISO/EN standards citations are still P3, not started; there is also no deck file in this repository to edit, so this item applies to whatever slide deck the team is presenting from outside this codebase.

---

## 9. What not to build

- **Blockchain.** The README already makes the better argument: a hash chain gives
  tamper evidence without a distributed-consensus dependency. Adding a chain would
  weaken the pitch, not strengthen it. External anchoring of the head hash gets you
  the remaining property at a fraction of the cost.
- **An LLM chat assistant.** It adds an unbounded failure surface to a system whose
  entire credibility rests on bounded, inspectable decisions. If you want natural
  language, constrain it to reading the passport aloud.
- **More charts.** Nine is enough. One reliability diagram and one
  capacity-utilisation strip are worth more than five new pie charts.
- **Removing the disclaimers.** The synthetic-data notice, the safety-gate message
  and the "not affiliated with KONE" line are the most commercially valuable text in
  the repository. A buyer in a safety-regulated industry trusts a team that states
  its limits. Keep every one of them.
- **Claiming real KONE data.** Obvious, and worth writing down anyway.

---

## 10. Sources

- [KONE — Our Sustainability Journey](https://www.kone.com/en/sustainability/our-sustainability-journey/) and [KONE — Strategy (Rise, 2025–2030)](https://www.kone.us/about-kone/company/strategy.html)
- [Elevator World — KONE announces its 2025–2030 "Rise" strategy](https://elevatorworld.com/news/daily-news/kone-announces-ambitious-new-2025-2030-strategy-rise/)
- [GreentechLead — KONE manufacturing emissions, renewable electricity and 2030 targets](https://greentechlead.com/sustainability/kone-cuts-manufacturing-emissions-86-uses-99-6-renewable-electricity-and-targets-carbon-neutral-operations-by-2030-54354)
- [KONE 24/7 Connected Services](https://www.kone.com/en/products-and-services/maintenance-and-modernization/24-7-connected-services.aspx) · [KONE API services](https://www.kone.com/en/careers/professionals-and-technical-experts/blogs/meet-kones-trailblazing-api-services.aspx) · [konecorp/kone-api-examples](https://github.com/konecorp/kone-api-examples)
- [European Commission — Digital Product Passport](https://single-market-economy.ec.europa.eu/single-market/digital-product-passport_en) · [Construction products DPP and CPR (EU) 2024/3110](https://myproductpassport.eu/sectors/construction)
- [KPMG — EU agrees Omnibus changes](https://kpmg.com/xx/en/our-insights/ifrg/2025/esrs-eu-omnibus.html) · [CSRD under Omnibus: scope and timelines for 2026](https://www.coolset.com/academy/csrd-under-omnibus-updated-scope-timelines-and-what-companies-should-do-in-2026)
- [EFRAG — ESRS E5 Resource use and circular economy](https://www.efrag.org/sites/default/files/sites/webpublishing/SiteAssets/ESRS%20E5%20Delegated-act-2023-5303-annex-1_en.pdf) · [How to interpret ESRS E5](https://www.coolset.com/academy/esrs-e5-circular-economy)
- [EU AI Act — high-level summary](https://artificialintelligenceact.eu/high-level-summary/) · [Annex I explained: AI in regulated products](https://www.euai-act.com/articles/annex-i-explained) · [Annex I union harmonisation legislation, incl. Directive 2014/33/EU](https://www.nicfab.eu/en/pages/annex-i-ai-act/)
- [ISO 4344:2022 — Steel wire ropes for lifts](https://www.iso.org/standard/79195.html) · [ELA — Safety of Existing Lifts, EN 81-80 (SNEL)](https://www.ela-aisbl.eu/wp-content/uploads/2024/11/Safety_of_Existing_Lift_SNEL_application_2020.pdf)

---

*Audit of the working tree at `D:\Coding\kone-elevate` as of 11 September 2026. Code
figures measured from the repository; model metrics read from
`backend/models/metrics.json` (RF-v1.0-synthetic, trained on 8,000 synthetic rows,
evaluated on 2,000). Regulatory positions summarised from the sources above and are
not legal advice. KONE is a trademark of KONE Corporation; this is an independent
analysis of a student project.*
