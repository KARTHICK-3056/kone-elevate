# KONE systems integration: the anti-corruption layer

The P5 deliverable this covers: *"KONE integration adapters behind an
anti-corruption layer. Register a sandbox application on the KONE API
Portal and demonstrate one live call for equipment identity. Define
adapter interfaces for service-record ingest and spare-parts inventory,
with contract tests against recorded fixtures."*

> **Status.** The interfaces, the API layer, contract tests, *and*
> KONE-backed adapters written against KONE's published reference
> implementation all exist (§4.5). **No KONE API Portal account was ever
> obtained, so no live call to a KONE system has ever been made** - what is
> missing is the account, not the code. Spare-parts inventory has no KONE
> API at all and stays fixture-backed permanently. This document says
> exactly where the line between "done" and "not done" sits.

---

## 1. Why an anti-corruption layer

Quoting the plan directly: *"Build to the documented APIs; do not assume
internals you cannot see."* Nothing outside `app/integrations/` should ever
import a KONE-shaped response object, a KONE SDK, or a KONE endpoint URL.
Every other part of this codebase depends only on the three interfaces in
`app/integrations/base.py`:

| Interface | Resolves | Fixture data |
|---|---|---|
| `EquipmentIdentityAdapter` | An equipment id → identity record (type, site, install date, status) | `app/integrations/fixtures/equipment.json` |
| `ServiceRecordAdapter` | An equipment id → maintenance/inspection history | `app/integrations/fixtures/service_records.json` |
| `SparePartsInventoryAdapter` | A part number → current availability | `app/integrations/fixtures/spare_parts.json` |

`app/integrations/registry.py` is the single place that decides which
implementation is active. That design has now been paid off: KONE-backed
adapters exist (§4.5) and wiring them in was a change to that one
function, guarded by a setting - not a hunt through every call site that
might have imported a KONE type directly. Without credentials configured
it still returns the fixture-backed implementations.

## 2. What is real, and what is not

**Real:**

- The interfaces and data shapes (`EquipmentIdentity`, `ServiceRecord`,
  `SparePartAvailability`) are genuinely used end-to-end: the fixture
  adapters implement them, `app/api/integrations.py` calls them, and
  `GET /api/v1/integrations/equipment/{id}` (plus the service-records and
  spare-parts routes) answer real HTTP requests with them today.
- The contract tests (`tests/test_integrations.py`) describe what *any*
  implementation must satisfy - not just the fixture one. A future real
  adapter is expected to pass `assert_equipment_identity_contract`,
  `assert_service_record_contract` and `assert_spare_parts_contract`
  before it is trusted, exactly the discipline a "documented interface,
  swappable implementation" design is supposed to buy.
- Every response from these endpoints carries `"source": "fixture"`
  explicitly - the same "state which parts are real" discipline the DPP
  export's `registry_status` and the chain anchor's `published_to` already
  use elsewhere in this codebase (see `docs/compliance.md`,
  `docs/disaster-recovery.md`).

**Not real:**

- The exact field names in `EquipmentIdentity` / `ServiceRecord` /
  `SparePartAvailability` are this build's own reasonable, generic
  modelling of "what an elevator equipment record probably looks like" -
  not a copy of KONE's actual published API Portal schema, which this
  build never had credentials to see. Expect field names, required-ness,
  and enumerated values to need adjustment once the real schema is
  available. **§4 now records what KONE's own published reference
  implementation says those shapes actually are** - the code has not been
  changed to match, so the divergence is documented, not yet closed.
- No KONE API Portal developer account exists for this build. Registering
  a sandbox application, authenticating against it, and demonstrating one
  live call for equipment identity - the plan's explicit "done when" for
  this item - was not attempted, because it needs an account this
  environment has no path to create. **The client and adapters that would
  make that call now exist** (§4.5); what is missing is the account, not
  the code.

## 3. Swapping implementations

`registry.py` selects on one setting:

```python
@lru_cache
def service_record_adapter() -> ServiceRecordAdapter:
    if settings.kone_api_configured:      # KONE_CLIENT_ID + KONE_CLIENT_SECRET
        return KoneServiceRecordAdapter()
    return FixtureServiceRecordAdapter()
```

`GET /api/v1/integrations/status` reports which implementation is live for
each interface, and every integration response carries the `source` read
off the active adapter rather than a hardcoded string.

The contract functions in `tests/test_integrations.py` describe what *any*
implementation must satisfy. They were written in P5 for a real adapter
that did not exist yet; `tests/test_kone_integration.py` now runs the
KONE-backed adapters through them, which is what they were for.

## 4. The real KONE API surface, verified 21 September 2026

§2 above says our field names are "this build's own generic modelling...
not a copy of KONE's actual published schema, which this build never had
credentials to see." That is still true of the *code*, but it is no longer
true of our *knowledge*: KONE publishes an official, Apache-2.0 reference
implementation at
[github.com/konecorp/kone-api-examples](https://github.com/konecorp/kone-api-examples),
and this section records what reading it established. **No credentials
were obtained and no live call was made** - everything below comes from
KONE's published TypeScript interfaces, not from a response we received.

### 4.1 Provenance

Checked before trusting it: the `konecorp` GitHub organisation ("KONE
International Oyj"); commits authored from `@kone.com` addresses
(`shreya.jagtap@`, `hieu.tran@`, `antti.jarvinen@`) plus `@nitor.com`, a
Finnish consultancy KONE works with; 50 commits spanning March 2021 to
November 2025; Apache-2.0; every endpoint pointing at `dev.kone.com`,
whose portal title confirms as "KONE API Portal". Treat as genuine.

### 4.2 Auth and addressing

OAuth2 client-credentials against `https://dev.kone.com/api/v2/oauth2/token`.
Equipment is addressed by **KEN** (KONE Equipment Number), e.g.
`ken:38999833`. Scopes are per-equipment and per-product:

| Scope | Grants |
|---|---|
| `application/inventory` | List the resources this application may access |
| `serviceinfo/{ken}` | Service Info API v2 for that equipment |
| `rtm/{ken}` | Equipment Status API v2 (real-time monitoring) for that equipment |

### 4.3 The two products that matter to this project

**Service Info API v2** - `GET /api/v2/equipment/{ken}/serviceOrders` and
`.../serviceOrders/{serviceOrderId}`. The detail response is far closer to
our domain than the generic `ServiceRecord` shape we invented. It carries
`failedComponentCode`, `equipmentFailureReason`, `technicianActionCode`,
`equipmentConditionOnArrival`/`OnDeparture` (+ `...Desc`), `activityType`,
`workTime`/`workTimeUnit`, and `invoices.costAmount`. `failedComponentCode`
is the **only component-level key anywhere in KONE's public API surface**.

**Equipment Status API v2** - `GET /api/v2/equipment/search` (availability,
status, movement) and `/api/v2/equipment/elevator` (door and button events).
Movement carries `loadPercentage`, `estimatedPersons`, `durationSeconds`,
`distanceMeters`; door events carry `openingDuration`, `closingDuration`,
`reopensByPhotoCell`, `reopensByDOB` - direct wear instrumentation for the
Door Operator type; escalator events carry `brakingDistance` and speed
transitions.

### 4.4 What this does and does not solve

Mapped against `app/ml/features.py`'s thirteen model inputs: seven become
real measurements (`operating_hours`, `load_cycles`, `average_load`,
`service_count`, `repair_count`, `failure_history`,
`days_since_last_service`), three become proxies needing a stated
assumption (`inspection_score` from the ordinal condition codes,
`component_age` from the equipment's install date rather than the
component's own, `component_type` from `failedComponentCode` and only when
something failed), and three have no source at all (`vibration`,
`temperature`, `material`).

Two limits must not be glossed over, and any adapter built here has to
carry them explicitly the way `material_flow.mass_source` already carries
estimated-vs-measured mass:

1. **No disposition label exists.** No KONE API publishes "this component
   had its sub-components recovered" versus "material recovered" versus
   "scrapped". These APIs upgrade our
   *features*; the *target variable* stays synthetic until a workshop
   records real outcomes through the P6 capture endpoint.
2. **Granularity mismatch.** KONE addresses equipment (one whole lift per
   KEN); we track components. Attributing a lift's duty cycle to one sheave
   is an apportionment assumption we would be making, not a measurement
   KONE hands us.

### 4.5 What was built against it (K-1, K-2)

§2's "not real" list is now partly out of date. Two of the three interfaces
have KONE-backed implementations, written against the shapes in §4.3:

| Module | What it does |
|---|---|
| `app/integrations/kone_client.py` | OAuth2 client-credentials, **per-scope** token cache (a token for one KEN is not valid for another), the documented paths, stdlib `urllib` like the rest of this codebase |
| `app/integrations/kone_adapters.py` | The only module allowed to know KONE's field names. `KoneEquipmentIdentityAdapter`, `KoneServiceRecordAdapter` |
| `app/integrations/kone_features.py` | The apportionment layer - equipment telemetry to component features, with provenance |
| `app/integrations/registry.py` | Selects KONE adapters when `KONE_CLIENT_ID`/`KONE_CLIENT_SECRET` are set, fixtures otherwise |

**Spare parts has no implementation and will not get one.** KONE publishes
no spare-parts API, so there is no backend to point at. The registry keeps
serving the fixture adapter whatever is configured, and says so.

Credentials come through the P4 secrets provider (`KONE_CLIENT_SECRET` is
sourced from Vault when one is configured), never from a settings file.

#### The two-client split

`HttpKoneApiClient` talks to the real service. `RecordedKoneApiClient`
replays fixtures written in KONE's **real field names**
(`failedComponentCode`, `equipmentConditionOnDeparture`, …), taken from
`src/common/types.ts` in the examples repo. The adapters' mapping logic -
the part that actually breaks if the published schema was misread - runs
identically against both, so it is fully covered today.

The HTTP transport is covered separately by a test that stands up a local
stub speaking the documented protocol and drives the real `get()` through
it: HTTP Basic client credentials, form-encoded `grant_type`/`scope`, then
a Bearer GET, plus token-cache and 404 behaviour. That proves this client
sends what KONE documents. It proves nothing about what KONE returns.

#### Still not covered, and only a live call can fix it

A documented field the service omits; a pagination envelope the examples
do not show; an auth scope that turns out to be insufficient; rate limits.

#### K-2, and the assumption that has to stay visible

`kone_features.derive_features` turns one lift's telemetry into one
component's features. Every field carries a provenance tag - `measured`,
`apportioned`, `derived` or `unavailable` - and the result reports what
share of the vector is grounded (75% on the recorded fixture, with
`component_age`, `vibration` and `temperature` named as having no source).

`APPORTIONMENT` is the table the honesty of this rests on: a door operator
actuates twice per journey and is loaded ~15% of running time, a motor runs
throughout. Each factor states its reasoning. **These are this platform's
assumptions, not KONE measurements**, and a workshop engineer should expect
to rewrite them.

Two mismatches are recorded rather than smoothed over:

- `average_load` is a **percentage** of rated load. KONE publishes
  `loadPercentage` and no rated-load field; the model's feature is in kg.
  Converting would need a capacity figure nobody here has.
- `vibration` and `temperature` are returned as `unavailable`, never
  defaulted. `missing_for_model()` returns them so a caller has to decide
  explicitly - imputing silently would make a prediction built on an
  invented safety-relevant reading indistinguishable from a measured one.

### 4.6 Every assumption, tracked

The mentor route to confirming these closed, so the assumptions are
tracked instead: **[`docs/kone-assumptions.md`](kone-assumptions.md)** lists
every one made across K-1/K-2/K-3, rated by what breaks if it is wrong and
how it would be detected.

The one to read first is the condition-code direction. If KONE's codes run
`1` = worst rather than `1` = best, every `inspection_score` this layer
produces inverts, silently. `kone_features.validate_condition_code_direction()`
detects it from real data and refuses to conclude from too little.

### 4.7 Access, still open

Registration requires a KONE API Portal account, which requires an
organisation to nominate an owner and create an IBM ID. Whether a sandbox
returns real or simulated service-order data could not be verified - the
portal renders behind JavaScript and a login. That question, and whether
`serviceinfo`/`rtm` scopes can be granted on any real KEN, are the specific
asks for a KONE contact.

## 5. Reproducing what exists today

```bash
cd backend
python -m pytest tests/test_integrations.py tests/test_kone_integration.py -v

# With the API running and a bearer token:
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/integrations/equipment/EQ-CHN-0001
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/integrations/equipment/EQ-CHN-0001/service-records
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/integrations/spare-parts/KE-GOV-STD-01

# Which implementation is actually answering right now
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/integrations/status
```

Point the registry at the KONE adapters without credentials to confirm the
swap happens (the calls will then fail at the network, which is the
expected outcome with no account):

```bash
KONE_CLIENT_ID=x KONE_CLIENT_SECRET=y python -c \
  "from app.integrations import registry; print(registry.integration_status()['adapters'])"
# {'equipment_identity': 'kone-api', 'service_records': 'kone-api', 'spare_parts': 'fixture'}
```
