# Database schema

PostgreSQL in Docker Compose; SQLite for zero-setup local development. The
same SQLAlchemy models drive both - see `backend/app/models/`.

## Entity relationships

```
                    ┌──────────────────┐
                    │    components    │
                    │  (the passport)  │
                    └────────┬─────────┘
                             │ 1
              ┌──────────────┼──────────────┐
              │ N            │ N            │ N
    ┌─────────▼──────┐ ┌─────▼───────┐ ┌────▼──────────┐
    │ service_events │ │ predictions │ │ material_flow │
    └────────────────┘ └─────────────┘ └───────────────┘

    ┌────────────┐
    │ audit_logs │   append-only SHA-256 chain, referenced by
    └────────────┘   (entity_type, entity_id) - deliberately NOT a
                     foreign key, so history survives deletion
```

`audit_logs` has no foreign keys on purpose. Deleting a component must not
delete its audit history, otherwise the chain could be pruned by deleting the
records it protects.

---

## `components`

The core entity. One row per replaceable elevator component.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | surrogate key |
| `component_id` | varchar(48) | unique, indexed. Business id, e.g. `KE-MOT-000012` |
| `serial_number` | varchar(64) | unique, indexed |
| `component_type` | varchar(48) | indexed. Motor, Steel Rope, Brake, Governor, Door Operator, Sheave (Guide Rail and Control Board were removed - migrations `0020_remove_guide_rail`, `0021_remove_control_board`) |
| `material` | varchar(32) | indexed. Steel, Cast Iron, Aluminum, Copper, Composite (Electronic was only used by Control Board; ledger rows keep it) |
| `manufacturer` | varchar(96) | product line |
| `origin` | varchar(96) | indexed. Manufacturing plant |
| `installation_date` | date | indexed. Age is derived from this, never stored |
| `operating_hours` | float | cumulative run hours |
| `load_cycles` | integer | cumulative cycles |
| `average_load` | float | kg |
| `vibration` | float | mm/s RMS |
| `temperature` | float | degrees C |
| `service_count` | integer | preventive-maintenance visits |
| `repair_count` | integer | corrective interventions |
| `failure_history` | integer | in-service failures |
| `inspection_score` | float | 0-100, last assessed condition |
| `last_service_date` | date | drives `days_since_last_service` |
| `health_score` | float | indexed. Cached latest score, for fast list queries |
| `current_status` | varchar(32) | indexed. Lifecycle state (see below) |
| `location` | varchar(96) | indexed. `City, Country` |
| `qr_token` | varchar(48) | unique, indexed. Opaque passport token |
| `notes` | varchar(512) | free text |
| `created_at` / `updated_at` | timestamp | maintained by the ORM |

**Composite indexes:** `(component_type, current_status)`, `(current_status, health_score)`.

**Derived, not stored:** `component_age` (years from `installation_date`) and
`days_since_last_service`. Storing them would guarantee they go stale.

---

## `service_events`

Dated lifecycle history. One row per visit.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `component_id` | integer FK → components, `ON DELETE CASCADE` | indexed |
| `event_type` | varchar(32) | indexed. INSTALLATION, INSPECTION, MAINTENANCE, REPAIR, MODERNIZATION, REMOVAL |
| `event_date` | date | indexed |
| `technician` | varchar(96) | |
| `description` | text | |
| `operating_hours`, `vibration`, `temperature`, `inspection_score` | float | readings taken at the visit |
| `created_at` | timestamp | |

**Composite index:** `(component_id, event_date)`.

Recording an event can absorb its readings into the component record
(`update_component: true`), increment the service or repair counters, and
advance the lifecycle status for `REMOVAL` and safety-critical `INSPECTION`.

---

## `predictions`

Immutable AI assessments. Never updated in place - each assessment appends a
row, so the passport carries the full decision history.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `component_id` | integer FK → components, cascade | indexed |
| `health_score` | float | 0-100 at assessment time |
| `recommendation` | varchar(24) | indexed. CONTINUE_USING / COMPONENT_RECOVERY / MATERIAL_RECOVERY / DISPOSE / DEFER_TO_INSPECTION (renamed from the legacy codes by migration 0018) |
| `confidence` | float | 0-1, the winning class probability |
| `model_version` | varchar(48) | e.g. `RF-v1.0-synthetic` |
| `key_factors` | JSON | ranked explanation factors |
| `input_snapshot` | JSON | the exact feature vector scored, for auditability |
| `probabilities` | JSON | full class distribution |
| `safety_flag` | boolean | true for safety-critical types |
| `safety_message` | varchar(128) | `MANDATORY HUMAN INSPECTION` when flagged |
| `predicted_at` | timestamp | indexed |

**Composite indexes:** `(component_id, predicted_at)`, `(recommendation, predicted_at)`.

Storing `input_snapshot` alongside the output means a past recommendation can
always be reproduced and explained, even after the component record has moved
on.

---

## `audit_logs`

Append-only, tamper-evident chain. See `docs/architecture.md` and the Audit
Chain section of the README.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | chain order |
| `entity_type` | varchar(48) | indexed. component, prediction, ... (older records may also name the removed recovery_item, service_demand and recovery_match entities) |
| `entity_id` | varchar(64) | indexed. Business id or numeric id as text |
| `action` | varchar(32) | indexed. CREATE, UPDATE, DELETE, PREDICT, SERVICE_EVENT, STATUS_CHANGE, MATERIAL_FLOW, ... (older records may carry the removed Recovery Exchange actions, e.g. RECOVERY_LISTED, MATCH_ACCEPTED - the chain is never rewritten) |
| `data_snapshot` | JSON | immutable copy of the record at that moment |
| `previous_hash` | varchar(64) | SHA-256 of the preceding record (genesis = 64 zeros) |
| `current_hash` | varchar(64) | unique, indexed |
| `timestamp` | timestamp | indexed |
| `actor` | varchar(96) | who performed the action |

**Composite index:** `(entity_type, entity_id)`.

Hash input: `previous_hash + "|" + canonical_json({entity_type, entity_id, action, data_snapshot, timestamp, actor})`.
`id` is excluded so the hash never depends on a database sequence value.

---

## Controlled vocabularies

**Lifecycle status** (a human decision, tracked on the component):

```
ACTIVE → UNDER_INSPECTION → REMOVED → RECOVERED → PART_RECOVERY
                                   → MATERIAL_RECOVERED
                                   → DISPOSED
```

`PART_RECOVERY` means the component's usable sub-components are being
recovered for technically suitable lower-demand applications. There is no edge
back to `ACTIVE`: a complete component is never refitted, resold or
transferred, and a manual status edit that tries it is rejected with 409.

The Recovery Exchange (and its `AVAILABLE` / `ALLOCATED` / `PARTS_FITTED`
states and `PARTS_FITTED` service event) was removed. Migration
`0019_remove_recovery_exchange` drops `recovery_items`, `service_demands` and
`recovery_matches` and moves any component in an exchange state to
`PART_RECOVERY`.

**AI recommendation** (an advisory model output, stored per prediction):

```
CONTINUE_USING | COMPONENT_RECOVERY | MATERIAL_RECOVERY | DISPOSE | DEFER_TO_INSPECTION
```

Displayed as "Continue Using – No Changes Required", "Component Recovery",
"Material Recovery", "Dispose". Migration `0018_recommendation_categories`
renames the legacy stored values (REUSE / REFURBISH / RECYCLE, the old
lifecycle states, recovery conditions, workshop outcomes, the REINSTALLATION
event type and the planner role) everywhere except `audit_logs`, which is
hash-chained and keeps what was recorded; legacy codes read from it are mapped
by `enums.canonical_recommendation`.

These are deliberately separate. The model proposes a category; a human
moves the component through its lifecycle. A component can sit at `ACTIVE`
while its latest recommendation is `COMPONENT_RECOVERY` - that is a work queue,
not a contradiction.

`components.material_grade` holds a grade only when one was recorded from the
nameplate or bill of materials. When it is empty, views show the
industry-standard grade for the material, labelled "(industry standard -
assumed, not recorded)"; the assumption is never written to this column.

---

## Migrations

Alembic is configured in `backend/alembic/`, with `env.py` reading
`DATABASE_URL` from the application settings so migrations never carry a
committed credential.

```bash
cd backend

python -m alembic upgrade head                       # apply all migrations
python -m alembic revision --autogenerate -m "note"  # create a new one
python -m alembic downgrade -1                       # roll one back
python -m alembic current                            # show current revision
python -m alembic history --verbose                  # full history
```

The initial revision is `0001_initial` and creates all seven tables with their
indexes. `render_as_batch` is enabled for SQLite so `ALTER TABLE` migrations
work there too.

For a throwaway local database, `create_all()` runs automatically on API
startup, so a fresh clone works without running Alembic at all. Alembic is the
supported path for anything that must survive a schema change.
