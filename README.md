# KONE ELEVATE

### Component Passport - AI-Powered Circular Economy Platform for Elevator Component Lifecycle Management

**Team CodeFather** - SRM Institute of Science and Technology, Ramapuram

[![Backend](https://img.shields.io/badge/backend-FastAPI-009688)]()
[![Frontend](https://img.shields.io/badge/frontend-React%2018%20%2B%20Vite-61dafb)]()
[![ML](https://img.shields.io/badge/ML-scikit--learn%20Random%20Forest-f7931e)]()
[![Data](https://img.shields.io/badge/data-SYNTHETIC-orange)]()
[![Tests](https://img.shields.io/badge/tests-391%20passing-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

---

> ### Prototype disclosure - read this first
>
> **Prototype uses synthetic degradation data. Production deployment requires
> validation against real historical component service, inspection, sensor and
> removal records.**
>
> - No real KONE data was used. The model is trained on a synthetic degradation
>   simulator committed in this repository and reproducible from seed 42.
> - Every AI output is an **AI-assisted disposition recommendation**. It is
>   advisory only and is never a certification, approval or authorisation to
>   operate an elevator.
> - Safety-critical components (steel ropes, brakes, governors) always carry a
>   **MANDATORY HUMAN INSPECTION** requirement, whatever the model predicts.
> - Economic and CO2 figures are **prototype estimates** from configurable
>   constants, not validated KONE cost or emission data.
> - "KONE" is a trademark of KONE Corporation. This is an independent student
>   project, not affiliated with, endorsed by, or connected to KONE Corporation.

---

## Table of contents

1. [The problem](#1-the-problem)
2. [The solution](#2-the-solution)
3. [Architecture](#3-architecture)
4. [Features](#4-features)
5. [Tech stack](#5-tech-stack)
6. [ML approach](#6-ml-approach)
7. [Dataset generation](#7-dataset-generation)
8. [Database](#8-database)
9. [API](#9-api)
10. [QR passport](#10-qr-passport)
11. [Simulation](#11-simulation)
12. [Audit chain](#12-audit-chain)
13. [Installation](#13-installation)
14. [Docker setup](#14-docker-setup)
15. [Local setup](#15-local-setup)
16. [Model training](#16-model-training)
17. [Seed data](#17-seed-data)
18. [Demo flow](#18-demo-flow)
19. [Testing](#19-testing)
20. [Project structure](#20-project-structure)
21. [Limitations](#21-limitations)
22. [Future scope](#22-future-scope)

---

## 1. The problem

Thousands of elevator components are removed during modernisation and
maintenance: sheaves, door operators, steel ropes, motors, brakes,
governors.

Many are scrapped not because they are worn out, but because **nobody can prove
they are not**. A technician holding an unlabelled sheave has no service
history, no operating hours, no inspection record. The safe default is the skip.

That single evidence gap causes six costs:

1. Components with remaining useful life are disposed of
2. New parts are purchased that were not needed
3. Usable sub-components are never identified for recovery
4. Component-recovery capacity cannot be planned, because demand is invisible
5. Lifecycle records are lost the moment a component leaves the shaft
6. Sustainability reporting has no auditable component-level basis

## 2. The solution

Give every component a **digital passport**, addressable by the QR code on its
label.

```
Physical component  ──QR──►  Digital passport  ──►  AI assessment
                                                          │
                                    ┌─────────────────────┤
                                    ▼                     ▼
                            Health score 0-100     SAFETY GATE
                            Confidence             (rope/brake/governor)
                            Ranked explanation           │
                                    │                    ▼
                                    ▼          MANDATORY HUMAN INSPECTION
   Continue Using – No Changes Required / Component Recovery /
                  Material Recovery / Dispose
                                    │
                                    ▼
                    Economic + environmental impact
                                    │
                                    ▼
                          SHA-256 audit trail
```

The passport records identity, material, origin, installation date, operating
history, duty cycle, load cycles, vibration, temperature, service history,
inspections, repairs, every previous AI decision, and the current lifecycle
status - all anchored in a tamper-evident hash chain.

## 3. Architecture

```
                    ┌──────────────────────┐
                    │      React UI        │
                    │ Dashboard            │
                    │ Component Passport   │
                    │ QR Lookup            │
                    │ Analytics            │
                    │ Simulation           │
                    │ Audit Log            │
                    └──────────┬───────────┘
                               │
                              REST
                               │
                    ┌──────────▼───────────┐
                    │      FastAPI         │
                    │ Components API       │
                    │ Prediction API       │
                    │ Passport API         │
                    │ Recovery API         │
                    │ Dashboard API        │
                    │ Audit API            │
                    └──────────┬───────────┘
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
       PostgreSQL          ML Model          Audit Chain
                         Random Forest        SHA-256
             │                 │                 │
             ▼                 ▼                 ▼
       Component Data     Prediction       Tamper Evidence
```

Full detail in [`docs/architecture.md`](docs/architecture.md).

## 4. Features

**Component passport**
- QR-addressable digital passport per component, resolvable by component id,
  serial number or QR token
- Backend QR generation (PNG endpoint + inline data URI), printable passport
- Browser QR scanner with a **guaranteed manual fallback** when the camera is
  unavailable or permission is denied
- Full lifecycle: identity, operating history, service events, decision history,
  audit trail

**AI circular intelligence**
- Four recommendation categories, decided by one flow (`app/ml/decision_flow.py`):
  **Continue Using – No Changes Required** (stays in its current device and
  application, unchanged) → else **Component Recovery** (usable sub-components
  recovered after inspection and testing, for technically suitable lower-demand
  applications; the complete component is never refurbished or supplied again)
  → else **Material Recovery** → else **Dispose**. Each gate is decided on the
  calibrated classifier, the inspection result, the type's separable
  sub-components and the material - never on age alone. No complete component
  is ever resold or transferred.
- Calibrated Random Forest classifier over those four categories, wrapped in
  `CalibratedClassifierCV` (isotonic, 5-fold) so confidence tracks observed
  accuracy - reliability diagram on the Analytics page
- Material grade shown wherever material is shown: the recorded grade, or the
  industry-standard grade for the material, clearly labelled as assumed
- **Abstention.** A fifth outcome, `DEFER_TO_INSPECTION`, triggered by a
  split-conformal prediction set or low calibrated confidence, so an
  ambiguous case is flagged rather than answered with false certainty
- Transparent 0-100 health score with a full weighted per-factor breakdown
- Model confidence plus the complete class-probability distribution
- Three independent, side-by-side explanation methods: blended
  importance/design-envelope factors, Gini + permutation global importance,
  and per-prediction SHAP `TreeExplainer` attribution
- Cost-sensitive decision analysis (`app/ml/cost_matrix.py`) reporting
  expected cost alongside accuracy, since an optimistic error and a
  conservative one are not the same mistake
- Cohort (installation-year) validation published beside the random split, and
  a PSI/KS feature-drift check (`scripts/check_drift.py`)
- **Safety gate**: a hard rule outside the model for ropes, brakes and governors
- Graceful degradation to a health-score heuristic when no model is trained

**Forecasting and capacity planning**
- Weibull AFT survival model over the component cohort, fitted with proper
  right-censoring (41% of the training set is censored)
- `P(no longer suitable to continue using within h)` for h ∈ {3, 6, 12, 24} months, with
  confidence intervals from the model's coefficient covariance
- Fleet end-of-life forecast: expected removals per quarter, grouped by
  component type, site or region
- Component-recovery capacity planner: utilisation per quarter against declared
  workshop hours, the bottleneck component type, and a levelled intake
  schedule that carries un-absorbable work forward instead of dropping it
- Current backlog reported **separately** from the forecast - a component
  already assessed as no longer suitable to continue using has crossed the threshold being
  forecast, so it is this quarter's workload, not a prediction
- Published backtest: predicted vs actual event counts per horizon, MAPE per
  component type

**Portfolio command centre**
- 12 headline KPIs, 10 chart types (Recharts)
- Fleet analytics with type, status, location and date-range filters
- Safety-critical inspection queue
- Prototype economic and carbon impact with the assumption tables visible

**Audit and reporting**
- Append-only SHA-256 hash chain over every state change
- One-click integrity verification that names the first tampered record
- CSV export of components, predictions and the audit chain

## 5. Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 5, Tailwind CSS 3, React Router 6, Recharts 2, Axios, html5-qrcode, lucide-react |
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Uvicorn |
| Database | PostgreSQL 16 (Docker) / SQLite (local default), Alembic migrations |
| ML | scikit-learn (RandomForestClassifier), pandas, NumPy, SciPy, joblib |
| QR | `qrcode` + Pillow |
| Security | SHA-256 audit chain, PBKDF2-HMAC hashing, canonical JSON |
| DevOps | Docker, Docker Compose, nginx, Makefile |
| Testing | pytest + FastAPI TestClient (64 tests), Vitest + Testing Library (20 tests) |

## 6. ML approach

**Random Forest** (400 trees, `max_depth=16`, `class_weight="balanced_subsample"`)
inside a scikit-learn `Pipeline` whose `ColumnTransformer` one-hot encodes the
two categorical features. The **whole pipeline** is serialised with joblib, so
inference always applies exactly the preprocessing training used.

**13 features**, defined once in `app/ml/features.py` and shared by the
generator, the trainer and the inference path:

`component_type`, `material`, `component_age`, `operating_hours`, `load_cycles`,
`average_load`, `vibration`, `temperature`, `service_count`, `repair_count`,
`failure_history`, `inspection_score`, `days_since_last_service`

**No target leakage.** `health_score` is deliberately **not** a model feature -
it is a deterministic function of the same inputs, computed separately for
explanation. The trainer asserts this and fails loudly if a future edit
reintroduces it.

### Measured performance (`RF-v1.0-synthetic`, held-out 2,000 records)

| Metric | Value |
|---|---|
| Accuracy | **87.10%** |
| Precision (macro) | 86.75% |
| Recall (macro) | 85.80% |
| F1 (macro) | **86.24%** |
| 5-fold CV F1 (macro) | 85.35% (+/- 1.23) |

Confusion matrix (rows = actual; CU = Continue Using – No Changes Required,
CR = Component Recovery, MR = Material Recovery, D = Dispose):

|  | CU | CR | MR | D |
|---|---|---|---|---|
| **CU** | **237** | 63 | 12 | 0 |
| **CR** | 48 | **407** | 52 | 1 |
| **MR** | 15 | 64 | **1050** | 0 |
| **D** | 0 | 3 | 0 | **48** |

Most errors are between neighbouring categories. Material Recovery and Dispose
are separated mainly by the material itself (Dispose is reserved for material
with no recovery route), which is why `material` is now the most important
feature.

87% is the honest number on a *random* split, and it is deliberate - higher
would mean leakage (see [section 7](#7-dataset-generation)). It is also not
the number to quote as a production expectation: a **cohort split by
(synthetic) installation year** - train on the older 70%, test on the newer
30% - drops accuracy to **80.54%**. Both numbers are published side by side in
`models/metrics.json` and [`docs/model-card.md`](docs/model-card.md).

**Calibration and abstention.** The model is wrapped in
`CalibratedClassifierCV` (isotonic, 5-fold): Expected Calibration Error is
**0.0134**, and the reliability diagram is rendered live on the Analytics page.
A split-conformal rule adds a fifth outcome, `DEFER_TO_INSPECTION`
(`app/ml/abstention.py`), on 5.9% of the test set - and accuracy on the 94.1%
the model does answer rises to **89.3%**.

**Explainability**: three independent methods, side by side rather than one
standing in for the others - Random Forest Gini importance, permutation
importance, and genuine per-prediction **SHAP `TreeExplainer`** attribution
(`GET /api/v1/model/feature-importance`, and `shap_factors` on every
prediction).

**Cost-sensitive decisions**: `app/ml/cost_matrix.py` scores optimistic errors
(recommending something less conservative than the truth) higher than
conservative ones, and highest on safety-critical types. Every prediction
reports both the argmax choice and the cost-optimal alternative
(`cost_analysis`).

Full detail: [`docs/machine-learning.md`](docs/machine-learning.md) and
[`docs/model-card.md`](docs/model-card.md).

## 7. Dataset generation

`app/ml/generate_dataset.py` is a small causal simulator, not a random-number
dump:

```
building traffic (duty)   ─┐
maintenance quality       ─┤
environmental stress      ─┼──►  latent WEAR  ──►  noisy observations
component age             ─┤     (never seen         vibration
load stress               ─┘      by the model)      temperature
                                       │             inspection score
                                       ▼             repairs / failures
                          decision flow (4 gates) ──►  LABEL
```

**Why the model does not score 100%** - two deliberate mechanisms:

1. The model sees only *noisy observations* of latent wear, and part of the
   wear (environmental stress, maintenance quality) is never observable at all.
2. 5.5% of labels move one class up or down, modelling real inspector
   disagreement between sites and years.

```bash
python scripts/generate_data.py                            # 10,000 records, seed 42
python scripts/generate_data.py --records 25000 --seed 7
python scripts/generate_data.py --noise 1.4                # harder task
python scripts/generate_data.py --types Motor "Steel Rope"
```

Outputs `data/synthetic/dataset.csv` plus a stratified `train.csv`/`test.csv`.

Labels follow the same four-gate decision flow as the live recommendation
(`decision_flow.label_from_wear`): a wire rope (no separable
sub-components) never gets Component Recovery, and a recoverable material
never gets Dispose - label noise is confined to the categories feasible for
each row. Class distribution at the default settings: Continue Using 15.6%,
Component Recovery 25.4%, Material Recovery 56.4%, Dispose 2.6%.

## 8. Database

Core tables: `components`, `service_events`, `predictions`, `material_flow`,
`audit_logs` (plus users, simulation scenarios and telemetry). The Recovery
Exchange tables (`recovery_items`, `service_demands`, `recovery_matches`) were
dropped by migration `0019_remove_recovery_exchange`.

PostgreSQL in Docker; SQLite for a zero-setup clone. Enum-like columns are
indexed `String` so the same models run on both engines.

`audit_logs` deliberately has **no foreign keys** - deleting a component must
not delete the history that protects it.

Full schema, indexes and vocabularies: [`docs/database.md`](docs/database.md).

## 9. API

50+ REST endpoints under `/api/v1`. Swagger at `/docs`, ReDoc at `/redoc`.

```
GET    /api/v1/health
GET    /api/v1/meta/enums

GET    /api/v1/components                      list, filter, sort, paginate
POST   /api/v1/components                      register
GET    /api/v1/components/{component_id}
PUT    /api/v1/components/{component_id}
DELETE /api/v1/components/{component_id}
GET    /api/v1/components/export                CSV

GET    /api/v1/components/{component_id}/service-events
POST   /api/v1/components/{component_id}/service-events

POST   /api/v1/predict                          ad-hoc assessment
POST   /api/v1/components/{component_id}/predict
GET    /api/v1/components/{component_id}/predictions
GET    /api/v1/model/info | /metrics | /feature-importance

GET    /api/v1/passports/{component_id}
GET    /api/v1/passports/{component_id}/qr      PNG
GET    /api/v1/passports/lookup/resolve
GET    /api/v1/passports/{component_id}/report

GET    /api/v1/simulation/reference
POST   /api/v1/simulation/advance

GET    /api/v1/dashboard/summary | /disposition | /health-distribution
GET    /api/v1/dashboard/component-types | /impact | /analytics | /safety-queue

GET    /api/v1/audit                            paginated chain
GET    /api/v1/audit/verify                     integrity check
GET    /api/v1/audit/{entity_type}/{entity_id}
```

Full reference with request/response examples: [`docs/api.md`](docs/api.md).

### Prediction example

```bash
curl -X POST http://localhost:8000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"component_type":"Motor","material":"Steel","component_age":5.2,
       "operating_hours":18000,"load_cycles":140000,"average_load":650,
       "vibration":3.8,"temperature":52,"service_count":5,"repair_count":1,
       "failure_history":0,"inspection_score":82,"days_since_last_service":90}'
```

```json
{
  "recommendation": "COMPONENT_RECOVERY",
  "recommendation_label": "Component Recovery",
  "recommendation_text": "Recover usable sub-components from this motor after inspection and testing. ...",
  "decision_flow": { "steps": [ { "gate": "Suitable for its current application?", "passed": false, "evidence": "..." } ] },
  "confidence": 0.92,
  "health_score": 78,
  "safety_flag": false,
  "key_factors": [
    { "factor": "Vibration", "impact": "moderate",
      "description": "Vibration of 3.80 mm/s is elevated but not severe (limit 7.0 mm/s)." }
  ],
  "model_version": "RF-v1.0-synthetic"
}
```

## 10. QR passport

Every component gets a QR code encoding `{QR_BASE_URL}/passport/{component_id}`.

- `GET /api/v1/passports/{id}/qr` streams a PNG (configurable module size,
  optional download header)
- The passport payload also embeds an inline `qr_data_uri`, so the code renders
  and prints without a second request
- `/passport/:componentId` renders **without the navigation shell** - it is
  designed for a phone in a machine room that has just scanned a label
- The scanner (`html5-qrcode`, lazy-loaded) is an enhancement; a **manual
  lookup is always rendered** so a denied camera never blocks a technician
- `GET /passports/lookup/resolve` accepts a full URL, a bare id, a serial
  number or a QR token

## 11. Simulation

Runs the reference lift's drivetrain (motor, steel rope, sheave, brake) month
by month at the average load you set, and shows every model's view of it.
**KONE API first**: each of the 13 model parameters is taken from the KONE API
wherever KONE publishes it, and only what KONE does not publish is simulated.

| Parameter | Source |
|---|---|
| Operating hours, load cycles | KONE API per journey (movement `durationSeconds`, one cycle per journey) at ISO 25745-2 trips/day - KONE publishes no journey count over time |
| Average load | KONE API (`loadPercentage` x rated load) - becomes "your input" once you change it |
| Service count, repairs, failures, days since service, inspection score | Start from the reference lift's KONE service orders at month 0, then carried forward by the simulation |
| **Vibration, temperature, component age** | **Simulated** - not in any KONE API |
| Component type, material | Reference assumptions |

Where the KONE record is too thin to give a rate it says so and the
simulation's own figure is used: the recorded example orders hold one
preventive visit (so the 6-month service interval is an assumption) and cover
6.5 months (too short for a callout rate). There are no KONE credentials in
this build, so "KONE API" values are recorded example responses; with live
credentials the same code reads the real lift. See
[`docs/simulation.md`](docs/simulation.md).

## 12. Audit chain

Every state change appends one row that hashes its own content together with
the hash of the record before it:

```
Record 1 ──► Hash 1
              │
Record 2 + Hash 1 ──► Hash 2
                       │
Record 3 + Hash 2 ──► Hash 3
```

```
current_hash = SHA256(previous_hash + "|" + canonical_json({
    entity_type, entity_id, action, data_snapshot, timestamp, actor
}))
```

Canonical JSON (sorted keys, fixed separators) guarantees a reproducible hash.
The row `id` is excluded so the hash never depends on a database sequence.

```bash
curl http://localhost:8000/api/v1/audit/verify
```

```json
{ "valid": true, "records_checked": 227,
  "message": "AUDIT CHAIN VALID - every record hash recomputed successfully." }
```

On tampering:

```json
{ "valid": false, "records_checked": 12, "invalid_record": 12,
  "reason": "snapshot_modified" }
```

This is **tamper evidence, not a blockchain**. There is no distributed
consensus, and an attacker with full write access could rebuild the chain. It
raises the cost of silent tampering and gives auditors a reproducible check.
`tests/test_audit.py` proves it: write records, verify, tamper with an old
snapshot, verify again, assert `valid: false`.

## 13. Installation

### One click on Windows

Double-click **`setup-and-run.cmd`** in the project folder. It:

1. installs Python and Node.js with winget if they are missing,
2. creates `backend\.venv` and installs all dependencies,
3. creates `backend\.env` from `.env.example` if there is none,
4. uses the committed, pre-trained models (it retrains only if they cannot
   be loaded with the installed library versions),
5. seeds the demo portfolio and the five demo accounts,
6. starts the backend and frontend (in two minimized windows) and opens
   <http://localhost:5173> in your browser.

The first run takes a few minutes; after that, every step already done is
skipped and the app is up in seconds. Dependencies are reinstalled only when
`backend/requirements.lock` or `package-lock.json` changes. Press Enter in the launcher
window - or double-click **`stop.cmd`** - to stop both servers. Sign in with
any demo account listed on the sign-in screen, password `elevate-demo-2026`.

### Manual

**Prerequisites**: Python 3.12+ (3.13 recommended), Node.js 22.12+, and
Docker (optional).

```bash
git clone <repository-url>
cd kone-elevate
cp .env.example .env       # adjust if needed; SQLite works with no changes
```

## 14. Docker setup

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | <http://localhost:5173> |
| Backend | <http://localhost:8000> |
| Swagger | <http://localhost:8000/docs> |
| PostgreSQL | `localhost:55432` (not 5432 - avoids colliding with a local Postgres; override with `POSTGRES_PORT`) |
| pgAdmin (optional) | <http://localhost:5050> - `docker compose --profile tools up` |

The backend image ships the committed, pre-trained models (retraining only if
they are incompatible with the pinned libraries), then runs migrations and seeds the demo portfolio on first start, so the stack comes
up demo-ready.

```bash
docker compose down          # stop
docker compose down -v       # stop and delete the database volume
docker compose logs -f       # follow logs
```

> Docker was unavailable in the environment where this project was built, so the
> Compose stack is written but **not executed-verified**. The local path below
> is fully verified end to end.

## 15. Local setup

### Backend

```bash
cd backend

python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.lock          # exact pinned versions (see requirements.txt for ranges)

python scripts/check_models.py            # committed models load? (no training needed)
python scripts/seed_database.py --reset   # 60 demo components

python -m uvicorn app.main:app --reload --port 8000
```

Backend: <http://localhost:8000> - Swagger: <http://localhost:8000/docs>

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: <http://localhost:5173>

The Vite dev server proxies `/api` to `http://localhost:8000`, so no
configuration is needed. To point at a different backend, set
`VITE_API_URL=http://host:port/api/v1`.

### Database options

**SQLite (default, zero setup).** `DATABASE_URL=sqlite:///./kone_elevate.db`.
Tables are created automatically on API startup.

**PostgreSQL.**

```bash
createdb kone_elevate
export DATABASE_URL="postgresql+psycopg2://kone_admin:change_me@localhost:55432/kone_elevate"
cd backend && python -m alembic upgrade head
```

### With the Makefile

```bash
make setup     # install backend + frontend dependencies
make demo      # committed models -> seed
make dev       # run both servers
make test      # run both test suites
make help      # list every target
```

### On Windows

Windows has no `make`; `make.cmd` (a wrapper around [`tools/windows/tasks.ps1`](tools/windows/tasks.ps1))
provides the same targets from PowerShell or cmd, with no execution-policy
changes needed. Every Python target runs inside `backend\.venv`, whichever
`python.exe` is first on PATH.

```powershell
.\make doctor           # check Python, Node.js, ports and project state
.\make install-prereqs  # (optional) install missing Python 3.13 / Node.js LTS via winget
.\make all              # first run: setup + demo + test
.\make start            # = setup-and-run.cmd (flags: --no-browser, --no-wait)
.\make stop             # = stop.cmd
.\make dev              # backend in a new window, frontend in this one
.\make help             # list every target
```

`.\make all` is `setup` (creates `backend\.venv`, installs Python deps,
`npm ci`, creates `backend\.env` from `.env.example` if you have none),
then `demo` (committed models -> seed -> demo accounts), then `test`.

Requirements: Windows 10 1809+ or Windows 11, **Python 3.12+** (3.13
recommended; x64 Python on ARM64 machines) and **Node.js 22.12+** (current
LTS). Nothing else - no `make`, WSL, Docker or admin rights. To pick a
specific interpreter for the venv: `$env:KE_PYTHON = "py -3.12"` before
`.\make setup`.

Troubleshooting:
- A `backend\.venv` or `frontend\node_modules` copied from another machine or
  OS does not work (wrong interpreter paths, wrong native binaries):
  `.\make setup` detects a broken venv and rebuilds it, and `npm ci` always
  reinstalls node_modules from the lockfile.
- "Port 8000/5173 is already in use": another server is still running;
  the message names the process to stop.
- The Windows Store "python.exe" stub (opens the Store instead of running) is
  detected and skipped.

## 16. Model training

**You do not need to train anything to run the app.** The trained models
(`backend/models/`) and the synthetic datasets (`backend/data/synthetic/`)
are committed, and every setup path - `setup-and-run.cmd`, `make demo`,
Docker, CI - uses them as-is. `python scripts/check_models.py` confirms they
load; a joblib bundle is only trusted under the exact scikit-learn/joblib
versions that pickled it, which is why installs use `requirements.lock`.

Retrain only to change the model, or after bumping scikit-learn/joblib in
`requirements.lock` - then commit the new files in `backend/models/`:

```bash
make retrain            # Windows: .\make retrain
# or, step by step:
cd backend
python scripts/train_model.py
python scripts/train_forecast.py
```

The script generates the dataset if missing, validates it (including the
leakage guard), splits it three ways (`dev` / `conformal_calib` / `test`),
fits the calibrated pipeline, evaluates, cross-validates, computes calibration
and conformal-abstention statistics, runs the cohort validation and
cost-sensitive analysis, and writes three artefacts.

```
====================================================================
KONE ELEVATE - Random Forest training report
====================================================================
DATA SOURCE      : SYNTHETIC (not trained on real KONE data)
Dataset          : 10,000 records
Dev / Conformal / Test : 6,400 / 1,600 / 2,000
Classes          : CONTINUE_USING, COMPONENT_RECOVERY, MATERIAL_RECOVERY, DISPOSE
--------------------------------------------------------------------
Accuracy         : 87.10%
Precision (macro): 86.75%
Recall (macro)   : 85.80%
F1 (macro)       : 86.24%
CV F1 (5-fold)   : 85.35% (+/- 1.23)
Mean confidence  : 0.877 (correct 0.8958, incorrect 0.7464)
Calibration (ECE): 0.0134 (isotonic, 5-fold)
Conformal q_hat  : 0.5975 (target coverage 90%)
Abstention rate  : 5.9% | answered accuracy 89.3% (vs 87.1% without abstention)
--------------------------------------------------------------------
Feature importance (Gini, averaged across calibration folds):
    material                   0.2328  ############################
    inspection_score           0.1445  #################
    component_type             0.1273  ###############
    operating_hours            0.1132  #############
    load_cycles                0.0960  ###########
    ...
--------------------------------------------------------------------
Cohort (installation-year) validation:
    cutoff year 2018 | accuracy=80.54% f1_macro=77.44% (random-split accuracy was 87.10%)
--------------------------------------------------------------------
Cost-sensitive decision analysis (relative units, see app.ml.cost_matrix):
    mean expected cost, argmax choice       : 0.5611
    mean expected cost, cost-optimal choice  : 0.4586
    decisions where they differ              : 4.50%
--------------------------------------------------------------------
Model saved      : backend/models/random_forest.joblib
Metrics saved    : backend/models/metrics.json
Importance saved : backend/models/feature_importance.json
====================================================================
```

Options: `--regenerate`, `--records N`, `--seed N`, `--estimators N`,
`--test-size 0.25`, `--no-cv`.

Check for feature drift against the training distribution:

```bash
python scripts/check_drift.py            # PSI + KS vs. data/synthetic/train.csv
```

Train the end-of-life forecaster (separate model, separate dataset):

```bash
python scripts/train_forecast.py         # Weibull AFT + published backtest
```

See [`docs/forecasting.md`](docs/forecasting.md) for the method, the
at-risk-population caveat and the backtest table.

Reload a freshly trained model without restarting the API:
`curl -X POST http://localhost:8000/api/v1/model/reload`

## 17. Seed data

```bash
python scripts/seed_database.py --reset
```

Creates 60 components covering all 7 types, ~680 service events, an AI
assessment for every component, and a 259-record audit chain that verifies
clean.

Options: `--components N`, `--seed N`, `--reset`, `--quiet`.

### The five demo scenarios

| Scenario | Component ID | Outcome |
|---|---|---|
| 1. Healthy motor | `KE-MOT-000001` | Continue Using – No Changes Required, 98% confidence, health 96.8 |
| 2. Moderately degraded motor | `KE-MOT-000002` | Component Recovery, 90% confidence, health 70.8 |
| 3. Heavily degraded sheave | `KE-SHE-000001` | Material Recovery, 92% confidence, health 52.0 |
| 4. **Safety-critical steel rope** | `KE-STE-000001` | Continue Using – No Changes Required 93% **+ MANDATORY HUMAN INSPECTION** |
| 5. **Safety-critical brake, worn lining** | `KE-BRA-000001` | Component Recovery 86%, health 80.8 **+ MANDATORY HUMAN INSPECTION** |

Dispose is reserved for material with no recovery route (composites), so none
of the five scenarios reaches it. Every scenario has the full passport deep
dive - material profile, usage-adjusted life projection and pre-emptive
forecast (Motor, Steel Rope, Sheave, Brake and Governor).

## 18. Demo flow

1. **Dashboard** - 60 components, health distribution, recommendation split,
   Rs. 15.0L recovery value, 7.26 t CO2e avoided
2. **Components** - search, filter, sort; safety chips on ropes/brakes/governors
3. **Component Passport** - QR code, full record, service history, audit trail
4. **Run AI Assessment**
5. **Result** - health 70.8/100, Component Recovery, with the decision flow gate by gate
6. **Explanation** - ranked factors with real readings and model importance
7. **Steel rope** (`/passport/KE-STE-000001`) - AI says Continue Using at 98%, the page
   still shows **MANDATORY HUMAN INSPECTION**
8. **Simulation** - KONE API values first, only vibration and temperature simulated
9. **Audit Log** - 259 records with linked hashes
10. **Verify Audit Integrity** - **AUDIT CHAIN VALID**

Full script with talking points and likely questions:
[`docs/demo.md`](docs/demo.md).

## 19. Testing

```bash
cd backend  && python -m pytest -q          # 64 tests
cd frontend && npm run test                 # 20 tests
```

**Backend (64 tests)** - `tests/`

| File | Covers |
|---|---|
| `test_health.py` | health, readiness, enums, OpenAPI/Swagger, the 501 sensor hook |
| `test_components.py` | CRUD, validation bounds, service events, QR, passport, resolve, safety flags, export, delete-with-audit |
| `test_predictions.py` | prediction, probability distribution, invalid payloads, **safety gate on all three critical types**, persistence + audit, health-score monotonicity, forbidden-claim guard |
| `test_audit.py` | genesis link, chain linking, canonical JSON, **tamper detection**, deletion detection, entity scoping, API surface |
| `test_recovery.py` | listing, matching, scoring explanation, condition blocking, accept/reject, idempotent regeneration, dashboard and analytics |

The tamper test is the required scenario: write records → verify → modify an old
snapshot → verify again → assert `valid: false` with the correct record id.

**Frontend (20 tests)** - formatters, health bands, safety-critical constants,
and component rendering including a test asserting the safety banner appears
even when the AI says Continue Using, and one asserting the UI never renders
"approved for operation", "AI approved" or "certified".

## 20. Project structure

```
kone-elevate/
├── setup-and-run.cmd, stop.cmd     Windows one-click launcher / stopper
├── make.cmd, Makefile              task runners (Windows / Linux-macOS)
├── docker-compose.yml, .env.example
├── README.md, CONTRIBUTING.md, LICENSE, plan.md, PROGRESS.md
│
├── tools/windows/tasks.ps1         implementation behind make.cmd and the .cmd launchers
│
├── backend/
│   ├── Dockerfile, pytest.ini, alembic.ini, ruff.toml
│   ├── requirements.txt            direct dependencies (ranges)
│   ├── requirements.lock           exact pins every install uses
│   ├── app/
│   │   ├── main.py                 FastAPI app, middleware, routers
│   │   ├── core/                   config, database, security, tenancy, telemetry
│   │   ├── models/                 SQLAlchemy entities
│   │   ├── schemas/                Pydantic contracts
│   │   ├── api/                    REST routers
│   │   ├── services/               domain logic (prediction, recovery, audit, ...)
│   │   ├── ml/                     dataset simulator, training, prediction,
│   │   │                           explanation, model + forecast registries
│   │   ├── integrations/           KONE API client and adapters
│   │   └── utils/
│   ├── alembic/versions/           schema migrations
│   ├── data/synthetic/             committed datasets: dataset, train, test, survival
│   ├── models/                     committed trained models + metrics (no retraining needed)
│   ├── scripts/                    check_models, train_*, seed_*, verify_chain, ...
│   └── tests/                      pytest suite
│
├── frontend/
│   ├── Dockerfile, nginx.conf, vite.config.js, tailwind.config.js
│   └── src/
│       ├── api/                    axios client, error normalisation
│       ├── components/             reusable components
│       ├── pages/                  routed pages
│       ├── context/, hooks/        auth context, data hooks
│       ├── offline/                IndexedDB outbox for the offline PWA
│       ├── utils/, styles/
│       └── test/                   Vitest suites
│
└── docs/                           architecture, API, ML, model card, compliance, ...
```

## 21. Limitations

Stated plainly, because a prototype that oversells itself is worse than one
that does not.

**Data and model**

1. **Synthetic training data.** No real KONE service, inspection, sensor or
   removal records were available. The accuracy figures describe simulated
   degradation; real performance is unknown.
2. **The model partly learns our simulator.** Where a real degradation
   relationship differs from the one modelled, the model has learned the wrong
   thing.
3. **Design envelopes are illustrative.** Design life, design hours and
   vibration limits in `TYPE_REFERENCE` are plausible placeholders, not KONE
   specifications.
4. **Cohort (installation-year) validation confirms a random split flatters.**
   `models/metrics.json`'s `cohort_validation` trains on the older 70% of
   installation years and tests on the newer 30%; accuracy drops materially
   versus the random split. That drop is published, not hidden - see
   `docs/machine-learning.md` §6. A drift-monitoring job now exists
   (`scripts/check_drift.py`, PSI + KS per feature) but nothing schedules it
   against live traffic yet, because there is no live traffic.
5. **Forecasting is a separate model with separate limits.** The Weibull AFT
   (`docs/forecasting.md`) projects *when* a component stops being suitable to
   continue using, but it is fitted on the same simulator, its backtest MAPE is
   ~13% overall and materially worse at the 3-month horizon where event counts
   are small, and it is only valid for the at-risk population - components
   already past the threshold are reported as backlog, not forecast. The
   disposition classifier itself remains point-in-time.
6. **Calibration and abstention are implemented, not merely diagnosed.** The
   model is wrapped in `CalibratedClassifierCV` (isotonic, 5-fold); the
   reliability diagram is on the Analytics page and the reported ECE is
   typically in the 0.03-0.05 range. A split-conformal abstention rule adds a
   fifth outcome, `DEFER_TO_INSPECTION`, when the model is genuinely
   ambiguous - it is not a cure for the underlying accuracy ceiling, only an
   honest way of not presenting a guess as a fact.
7. **Gini importance is biased** toward high-cardinality features. Permutation
   importance and SHAP `TreeExplainer` attribution are now also computed and
   shown alongside it (`GET /api/v1/model/feature-importance`, and per-
   assessment SHAP factors on the Prediction page) precisely so Gini is never
   the only signal relied on.

**Health score and impact**

8. **The health score is a demo methodology.** The weights are reasoned but not
   engineering-validated. It is not an official KONE formula.
9. **Every economic and CO2 figure is a prototype estimate** from configurable
   constants. Transport is not modelled, component-recovery cost is bundled into a
   single ratio, and embodied carbon is one number per material rather than a
   full LCA.

**Platform**

10. **No enforced authentication.** Every endpoint is open and the audit actor
    comes from an unverified `X-Actor` header. `core/security.py` provides
    PBKDF2 hashing and signed tokens, but nothing enforces them. This is a
    documented prototype limitation, not a security design.
11. **Tamper evidence is not tamper proof.** An attacker with full database
    write access could rebuild the entire chain. There is no distributed
    consensus and no external anchoring.
12. **No IoT integration.** `POST /api/v1/sensors/{id}` returns 501 on purpose.
13. **No multi-tenancy, no i18n, no offline mode**, and the QR scanner needs a
    secure context (which is why the manual fallback is always present).
14. **Docker Compose is unverified.** It is written and reviewed, but Docker was
    unavailable in the build environment. The local path is verified end to end.

## 22. Future scope

**Near term**
- Real authentication (OAuth2/OIDC) with per-role authorisation
- A real cost matrix reviewed by a quality/safety engineer, replacing the
  illustrative relative-unit weights in `app/ml/cost_matrix.py`
- Photo attachments on service events

**Medium term**
- IoT telemetry ingestion behind a queue and a time-series store, activating the
  documented `/sensors/{id}` hook
- Real component-recovery routing/standard-time data to replace the illustrative
  labour-hour and workshop-capacity constants the capacity planner assumes
- Scheduling `scripts/check_drift.py` against real assessment traffic with
  alerting, instead of running it by hand
- Transport-aware impact modelling in the matching engine
- Mobile app with offline capture for machine rooms without signal

**Longer term**
- Validation against real historical service, removal and recovery-outcome
  records - the single change that would make everything else meaningful
- Externally anchored audit trail (periodic hash publication)
- Supplier-specific LCA data replacing the illustrative carbon constants
- Regulatory review against per-market elevator safety standards

---

## License

MIT - see [LICENSE](LICENSE).

"KONE" is a trademark of KONE Corporation. This is an independent student
prototype created for a hackathon, not affiliated with, endorsed by, or
connected to KONE Corporation, and it contains no KONE proprietary data.

**Team CodeFather** - SRM Institute of Science and Technology, Ramapuram
