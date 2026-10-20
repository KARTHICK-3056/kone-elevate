# Architecture

KONE ELEVATE is a three-tier prototype: a React single-page application, a
FastAPI service, and PostgreSQL (or SQLite for zero-setup local development).
A scikit-learn pipeline and a SHA-256 audit chain sit alongside the service
layer.

> **Prototype disclosure.** The system is trained on synthetic degradation
> data and is not affiliated with KONE Corporation. No output constitutes a
> certification, approval or authorisation to operate an elevator.

---

## 1. System overview

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
                          REST / JSON
                               │
                    ┌──────────▼───────────┐
                    │      FastAPI         │
                    │ Components API       │
                    │ Prediction API       │
                    │ Passport API         │
                    │ Simulation API       │
                    │ Dashboard API        │
                    │ Audit API            │
                    └──────────┬───────────┘
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
             ▼                 ▼                 ▼
       PostgreSQL          ML Model          Audit Chain
       (SQLAlchemy)      Random Forest         SHA-256
             │                 │                 │
             ▼                 ▼                 ▼
       Component Data     Prediction       Tamper Evidence
```

---

## 2. The core user journey

```
Physical elevator component
        ↓  QR label
Digital Component Passport            /passport/:componentId
        ↓
Lifecycle + service data              components, service_events
        ↓
AI Circular Intelligence              POST /predict
        ↓
Health score (transparent)            health_service
        ↓
Confidence + explainability           model probabilities + factor ranking
        ↓
SAFETY GATE                           steel rope / brake / governor
        ↓
DECISION FLOW (app/ml/decision_flow.py)
  Continue Using – No Changes Required → Component Recovery → Material Recovery → Dispose
        ↓
Economic + environmental impact       impact_service
        ↓
SHA-256 audit trail                   audit_logs
```

---

## 3. Backend layering

The backend is layered so each concern has exactly one home.

| Layer | Package | Responsibility |
|---|---|---|
| API | `app/api/` | HTTP routing, request/response models, status codes. No business logic. |
| Schemas | `app/schemas/` | Pydantic validation and serialisation contracts. |
| Services | `app/services/` | Business logic: health scoring, prediction orchestration, impact, QR, audit. |
| ML | `app/ml/` | Feature contract, dataset generation, training, inference, explainability, model registry. |
| Models | `app/models/` | SQLAlchemy ORM entities. |
| Core | `app/core/` | Configuration, database engine, logging, hashing/security primitives. |
| Utils | `app/utils/` | Enums, validation bounds, small helpers. |

**Dependency direction** is strictly downward: `api → services → ml/models → core/utils`.
Nothing in `services/` imports from `api/`, which keeps every service reusable
by the seed script, the CLI tools and the test suite.

### Request flow for an assessment

```
POST /api/v1/components/{id}/predict
  │
  ├─ api/components.py            resolve component (id | serial | qr_token)
  ├─ services/prediction_service  build features from the ORM row
  │     ├─ ml/features            normalise to the 13-feature contract
  │     ├─ ml/predict             score with the cached pipeline
  │     │     ├─ services/health_service   transparent 0-100 score
  │     │     ├─ ml/explain               rank the factors
  │     │     └─ safety gate              attach inspection requirement
  │     ├─ models/prediction      append an immutable row
  │     ├─ component.health_score cache for fast list queries
  │     └─ services/audit_service append a PREDICT chain entry
  └─ single transaction commit
```

The prediction row, the component update and the audit entry commit together.
A failure anywhere rolls all three back, so the audit chain can never record an
action that did not happen.

---

## 4. Frontend structure

```
src/
├── api/client.js        one axios instance; all error normalisation lives here
├── hooks/               data-fetching hooks (components, prediction, dashboard)
├── components/          reusable presentation components
├── pages/               one component per route
├── utils/               formatters and shared vocabulary
└── styles/index.css     Tailwind layers and the component class library
```

Two decisions matter:

1. **One API client.** Base URL, timeout, the audit actor header and error
   translation are defined once. A component never sees an axios error, only a
   normalised `ApiError` with a human-readable message.
2. **A standalone passport route.** `/passport/:componentId` renders without
   the navigation shell, because it is usually reached by scanning a QR code on
   a phone in a machine room.

---

## 5. Runtime behaviour

### Model caching

The joblib bundle is loaded once per process by `ml/model_registry.py` and held
in memory. Deserialising a 400-tree forest on every request would add tens of
milliseconds and significant GC pressure for no benefit.

The registry degrades gracefully: if the model file is missing, the API still
starts, predictions fall back to the transparent health-score heuristic, and
`model_available: false` is reported so the UI can show an honest banner.

### Database portability

`DATABASE_URL` selects the engine. SQLite is the default for a zero-setup
clone; Docker Compose sets a PostgreSQL URL. All enum-like columns are stored
as indexed `String` rather than native database enums, so the same models work
on both engines and adding a vocabulary value needs no migration.

### Indexing

Indexes back the queries the UI actually issues:

- single-column: `component_id`, `serial_number`, `component_type`, `material`,
  `current_status`, `health_score`, `qr_token`, `recommendation`
- composite: `(component_type, current_status)`, `(current_status, health_score)`,
  `(component_id, event_date)`, `(component_id, predicted_at)`

### Error handling

Four exception handlers in `app/main.py` convert every failure class into a
structured JSON body with no stack trace: validation (422), integrity conflict
(409), database unavailable (503) and unhandled (500). The frontend maps these
onto user-facing messages, including a specific recovery checklist when the
backend is unreachable.

---

## 6. Security posture (honest)

**Implemented:** environment-driven configuration with no hard-coded secrets,
explicit CORS allow-list, Pydantic validation on every inbound payload,
SQLAlchemy ORM throughout (no string-concatenated SQL), PBKDF2-HMAC password
hashing and HMAC-signed tokens available in `core/security.py`, and a non-root
container user.

**Not implemented:** there is no enforced authentication on the API. Every
endpoint is open, and the audit actor is taken from an optional `X-Actor`
header rather than a verified identity. This is a deliberate, documented
prototype limitation - see the Limitations section of the README. Production
deployment would require real authentication, per-role authorisation, rate
limiting and TLS termination before any of this is exposed.

---

## 7. Future IoT integration

`POST /api/v1/sensors/{component_id}` exists as a documented architecture hook
and **deliberately returns 501 Not Implemented**. No sensor hardware is
connected to this prototype, and no part of the demo should imply otherwise.
The endpoint documents the payload shape a future telemetry pipeline would
send (vibration, load, temperature, cumulative hours, timestamp).

A production ingestion path would add a queue between the sensors and the API,
write to a time-series store, and roll readings up into the component record on
a schedule rather than writing each reading synchronously.
