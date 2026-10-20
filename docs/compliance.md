# Compliance - disclosure requirements mapped to their data source

Where every number in an ESRS E5, BRSR or Digital Product Passport output
comes from, how to re-derive it, and - just as important - which parts are not
yet fit to file.

This file is the audit trail for the audit trail. An assurance provider should
be able to read it, run the queries it names, and arrive at the same figures
the API returns.

> **Status: DRAFT, from synthetic data.** No figure here has been produced
> from a real elevator, a real removal or a weighed component. The mechanism is
> complete and testable; the inputs are simulated. See §7.

---

## 1. Why a ledger had to exist first

The audit chain (`docs/architecture.md`) proves a record was not edited after
the fact. It does not produce a disclosure.

ESRS E5-4 and E5-5 are **mass-flow** disclosures: tonnes of material entering
and leaving, split by material and treatment route. Before P3 this platform
reported CO₂ avoided and INR recovered and **never persisted a kilogram** -
component mass was a configuration lookup applied at read time. A reporting
controller could not derive an E5 table from the database, because the
database did not contain the quantity E5 asks about.

`material_flow` fixes that. Every lifecycle transition now writes one immutable
row stating how much of which material moved, from which state to which, on
what date, and where the mass figure came from.

---

## 2. The reporting boundary

The boundary is the **installed fleet under management**.

| Transition | Direction | Disclosure effect |
|---|---|---|
| *(none)* → `ACTIVE` | `INFLOW` | E5-4 resource inflow |
| `ACTIVE` → `REMOVED` | `INTERNAL` | none - the part is in the workshop, not gone |
| `*` → `PART_RECOVERY` (Component Recovery) | `OUTFLOW` | E5-5, *preparation for reuse* (the regulation's term; diverted) |
| `*` → `MATERIAL_RECOVERED` (Material Recovery) | `OUTFLOW` | E5-5, *recycling* (the regulation's term; diverted) |
| `*` → `DISPOSED` | `OUTFLOW` | E5-5, landfill (directed to disposal) |
| `*` → `UNDER_INSPECTION` / `RECOVERED` | `INTERNAL` | none |

The four platform categories map onto the regulation's routes: Component
Recovery → "preparation for reuse", Material Recovery → "recycling", Dispose →
disposal. The report keeps the ESRS / BRSR / MCI wording because that is what
the regulation asks for; everywhere else the platform uses its own four
categories.

A removed component can never be set back to `ACTIVE`: a complete component
is never refitted, resold or transferred, so the platform never books a
secondary inflow of a recovered component
(`test_component_recovery_is_one_outflow_and_never_a_secondary_inflow`).
Ledger rows written before the Recovery Exchange was removed may still name
its states (`AVAILABLE`, `ALLOCATED`, `PARTS_FITTED`); they are history and
are not rewritten.

Two rules that are easy to get wrong, and are tested:

1. **A move between two outflow states is not a second outflow.**
   `AVAILABLE → PART_RECOVERY` is internal. The mass left the boundary once,
   when it became `AVAILABLE`; counting the onward move would inflate E5-5
   with material that never came back in.
   (`test_moving_between_two_outflow_states_is_not_counted_twice`)

2. **A component under Component Recovery leaves the boundary once.** Its
   usable sub-components are recovered for lower-demand applications - an
   E5-5 outflow diverted from disposal, under the regulation's "preparation
   for reuse" route. The complete component cannot be set back to `ACTIVE`,
   so it is never counted again as an inflow.
   (`test_component_recovery_is_one_outflow_and_never_a_secondary_inflow`)

Classification lives in one place: `app/services/material_flow_service.py`,
`_DESTINATION` and `classify()`.

---

## 3. Disclosure → data source

### ESRS E5-4 Resource inflows
`GET /api/v1/reports/esrs-e5?period=`

| Datapoint | Source | Notes |
|---|---|---|
| Total resource inflows (t) | `SUM(material_flow.mass_kg) / 1000` where `direction='INFLOW'` | |
| Secondary / reused share (%) (ESRS term) | Same, filtered `is_secondary = true` | `is_secondary` is set when an inflow has a non-null `from_state`. A recovered complete component can never re-enter service, so no path books one for it; rows written earlier keep their historical value |
| Inflows by material (t) | Grouped by `material_flow.material` | Denormalised on the ledger row, so the figure is stable if the component is later edited |
| Critical raw materials (t) | `mass_kg × settings.CRM_MASS_FRACTION[material][substance]` | **Estimate.** See §5 |

### ESRS E5-5 Resource outflows
| Datapoint | Source | Notes |
|---|---|---|
| Total outflows (t) | `direction='OUTFLOW'` | |
| Diverted from disposal (t) | `outflow_route IN (PREPARATION_FOR_REUSE, RECYCLING, OTHER_RECOVERY)` | `DIVERTED_FROM_DISPOSAL` in `app/utils/enums.py` |
| Directed to disposal (t) | `outflow_route IN (INCINERATION, LANDFILL, OTHER_DISPOSAL)` | `DIRECTED_TO_DISPOSAL` |
| By treatment route (t) | Grouped by `outflow_route` | |

### BRSR
`GET /api/v1/reports/brsr?period=`

| Datapoint | Source |
|---|---|
| Principle 2 - reclaimed input share | Secondary inflow mass ÷ total inflow mass |
| Principle 6 - total waste generated | Total outflow mass |
| Principle 6 - recovered (reuse + recycling + other recovery) | Outflow mass on diverted routes |
| Principle 6 - directed to disposal | Outflow mass on disposal routes |

### Digital Product Passport
`GET /api/v1/passports/{id}/dpp` - mapped to CPR (EU) 2024/3110.

| DPP element | Source |
|---|---|
| Persistent identifier | `components.dpp_id`, else derived `urn:kone:dpp:{schema}:{component_id}` |
| Data carrier (QR payload) | `DPP_RESOLVER_BASE_URL` + identifier |
| Economic operator | `components.economic_operator(_id)`, else `DPP_ECONOMIC_OPERATOR*` settings |
| Material composition | `material_flow_service.resolve_mass()` + `CRM_MASS_FRACTION` |
| Standards basis | `app/utils/standards.py` |
| Lifecycle record | `material_flow` rows for that component |
| Tamper evidence | `audit_logs` head hash for that component |

---

## 4. Re-deriving a report independently

Every report carries a `derivation` block:

```json
"derivation": {
  "ledger_rows": 17,
  "audit_entries": 17,
  "first_audit_hash": "...",
  "last_audit_hash": "...",
  "chain_head_hash_at_generation": "..."
}
```

To verify a published figure:

1. Select `material_flow` rows in the period
   (`GET /api/v1/reports/material-flow?period=2026`).
2. Sum `mass_kg` by `material` and divide by 1000. This must reproduce the
   `by_material` tonnages exactly.
3. Take each row's `audit_hash` and confirm it exists in `audit_logs`.
4. Run `GET /api/v1/audit/verify` and confirm the chain recomputes.

Step 3 is the load-bearing one: it ties an aggregate number to a specific,
individually hashed event. A report that only says "12 tonnes" is a claim; one
that says "12 tonnes, from these 17 hashed events" is evidence.

**This guarantee depends on the chain not forking under concurrent writes.**
Appends are serialised through `audit_chain_lock`
(`app/services/audit_service.py::_acquire_chain_lock`), and
`test_chain_survives_ten_threads_writing_one_hundred_entries_each` writes 1,000
entries from 10 threads and asserts the chain still verifies. That test was
confirmed to fail (chain forks at record 6) with the lock disabled.

---

## 5. What is estimated, and how much

Honest reporting means naming the estimates.

| Input | Status | Consequence |
|---|---|---|
| Component mass | `IMPACT_COMPONENT_MASS_KG`, per *type* not per unit | **Every tonne in every report is an estimate** unless `components.mass_kg` is populated |
| CRM mass fractions | `CRM_MASS_FRACTION`, per-material averages | CRM figures are order-of-magnitude only |
| Disposal route | Defaults to `LANDFILL` for `DISPOSED` | Conservative: overstates rather than flatters the disposal split |
| Standards clauses | Assembled from public scopes | Flagged `CLAUSE_UNVERIFIED` - see §6 |

Each ledger row records `mass_source` (`COMPONENT_RECORD` when weighed,
`CONFIG_ESTIMATE` when it fell back), and every report publishes
`estimated_mass_share_percent`. On the current synthetic dataset that figure is
**100%** - which is the correct and intended answer, not a bug.

**To make a report fileable:** populate `components.mass_kg` from weighbridge
or engineering data. The ledger then records measured mass and the estimated
share falls on its own, with no code change.

---

## 6. Standards basis

`app/utils/standards.py` cites, per component type:

| Component type | Standards |
|---|---|
| Steel Rope | ISO 4344:2022 (minimum requirements; discard criteria) |
| Brake | EN 81-20:2020 (braking system) |
| Governor | EN 81-20:2020, EN 81-50:2020 (overspeed governor type test) |
| Motor | ISO 281:2007 (bearing L10 life), IEC 60034-1:2022 |
| Sheave | ISO 281:2007, EN 81-20:2020 (traction sheaves, groove wear) |
| Door Operator | EN 81-20:2020 (doors, closing force) |
| *(all)* | EN 81-80:2019 (SNEL - improving safety of existing lifts) |

> **Clause numbers are not verified.** Standards are copyrighted documents sold
> by ISO, CEN and IEC and were not available to this build. Standard identity
> (number, year, scope) is correct; the *clause pointers* were assembled from
> public scopes and contents listings and carry `verification:
> "CLAUSE_UNVERIFIED"`. The UI renders that flag.
>
> Before any external use, someone holding the purchased standards must check
> each pointer and change the flag to `CLAUSE_VERIFIED`. Presenting an
> unverified clause to a technician as authoritative would be exactly the kind
> of confident wrongness the rest of this project is built to avoid.

---

## 7. Tamper evidence beyond the database

The hash chain detects a record edited **in place**. It does not detect an
administrator who deletes a record and re-hashes everything after it: the
rebuilt chain verifies perfectly, because the database is the only witness.

`scripts/anchor_chain_head.py` publishes the daily head hash so a second
witness exists. Run it daily; exit code 1 means no external witness is
configured.

```bash
python scripts/anchor_chain_head.py          # anchor today's head
python scripts/anchor_chain_head.py --check  # report status only
```

> **Current status: NOT PROTECTED against a database administrator.**
> `CHAIN_ANCHOR_WEBHOOK_URL` is unset, so anchors live in the same database and
> on the same host as the chain they commit to. `GET /api/v1/reports/anchors`
> reports `externally_witnessed_anchors: 0` and says so in plain words rather
> than implying a protection that is not in place.
>
> To close it, point `CHAIN_ANCHOR_WEBHOOK_URL` at an append-only store outside
> this system's administrative control.

---

## 8. Digital Product Passport conformance

| Requirement (CPR (EU) 2024/3110 / ESPR) | Status |
|---|---|
| Unique persistent product identifier | ✅ `urn:kone:dpp:1:{component_id}` |
| Resolvable data carrier | ⚠️ Resolves to `DPP_RESOLVER_BASE_URL`, a documented **placeholder host**. No resolver is deployed |
| Economic operator identified | ❌ Not assigned. `economic_operator.assigned` is `false` and the export says a passport may not be placed on the market without one |
| Registered with the EU DPP Registry | ❌ `registry_status: NOT_REGISTERED`. No registry credentials in this build |
| Schema version declared | ✅ `schema_version` |
| Material composition incl. CRM | ⚠️ Present, but estimated (§5) |
| Standards basis | ⚠️ Present, clauses unverified (§6) |
| Lifecycle record | ✅ From `material_flow`, each event hash-pinned |

The QR payload no longer encodes a `localhost` URL. A label is printed once and
glued to a component that outlives several generations of web application; a
passport whose link dies when the demo server stops is not a passport. Labels
printed under the old scheme still resolve
(`test_legacy_qr_formats_still_resolve`).

---

## 9. Reproducing everything in this file

```bash
cd backend

# Seed a fleet, which now writes material-flow rows for every transition
python scripts/seed_database.py --reset

# The ledger and its coverage
curl "localhost:8000/api/v1/reports/ledger-summary"

# The disclosures
curl "localhost:8000/api/v1/reports/esrs-e5?period=2026"
curl "localhost:8000/api/v1/reports/brsr?period=2026"
curl "localhost:8000/api/v1/reports/esrs-e5.csv?period=2026"

# One component's passport export
curl "localhost:8000/api/v1/passports/KE-MOT-000003/dpp"

# Tamper evidence
python scripts/anchor_chain_head.py --check
curl "localhost:8000/api/v1/audit/verify"

# The tests behind every claim above
python -m pytest tests/test_compliance.py -v
```

---

## 10. What would have to be true to actually file

1. **Real removals.** The ledger must be fed by real lifecycle events, not a
   seed script.
2. **Weighed mass.** `components.mass_kg` populated, so
   `estimated_mass_share_percent` falls from 100%.
3. **CRM from bills of materials.** Supplier declarations per article, not
   per-material averages.
4. **Verified standards clauses.** §6.
5. **A real economic operator** and a deployed resolver. §8.
6. **An external anchor witness.** §7.
7. **Verified identity.** The audit `actor` is still an unverified `X-Actor`
   header (`plan.md` §4, gap 4). Every figure in this document is attributed to
   a string someone typed. That is P4, and it is load-bearing for all of the
   above: a disclosure signed by "whoever sent the request" is not assurable.

Items 1-6 are data and configuration. Item 7 is the one that needs code, and
it is the next phase.
