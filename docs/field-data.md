# Real-world data without a KONE account

**Written 24 September 2026.** The team will not get a KONE API account. This
document covers what the platform does instead to work from real data, and
what is still missing.

The principle is the same one used everywhere else in this project: every
figure says where it came from. Real measurements, sensor readings and
simulated projections sit side by side, and none can be mistaken for another.

## 1. Measured inspections (standards-based)

**Where:** component page → **Record inspection**. API:
`POST /components/{id}/inspections`, `GET /inspections/checklists`.
**Code:** [`app/ml/inspection.py`](../backend/app/ml/inspection.py).

Technicians already measure these things at maintenance visits, because the
standards require it. The inspection score is now computed from those
measurements rather than typed in:

| Part | Measurements |
|---|---|
| Steel rope | Diameter reduction vs. nominal, broken wires over 6d, corrosion (ISO 4344 discard criteria) |
| Sheave | Groove wear depth, depth difference between grooves, cracks |
| Brake | Lining worn towards minimum thickness (manufacturer), air gap in range, torque/holding test (EN 81-20/-50) |
| Motor | Insulation resistance (log scale), bearing vibration (ISO 10816-3 / 20816-3 zones), bearing temperature, abnormal noise |

- **Scoring:** each measurement is placed between new condition (0) and its
  limit (1). The **worst one governs**, and the score is 100 − 65 × that
  value, the same scale the life model uses.
- **Discard criteria:** a measurement at its limit, or a failed safety test,
  is flagged as a **discard criterion met**. That is a safety finding, not
  just a low score.
- **What gets saved:** the measurements go into the service record, so the
  life model, the early-warning trends and the AI classifier all work from
  measured condition.

**Limits are labelled.** Standards were not purchased for this build, so:
- **Prototype default** limits are typical values that must be replaced with
  the named standard's or the manufacturer's value before any real discard
  decision.
- **Manufacturer** limits are entered for each component.

## 2. Sensor and controller data (vendor-neutral)

**Where:** component page → **Sensor and controller data** (CSV upload). API:
`POST /components/{id}/telemetry` (JSON batches),
`POST /components/{id}/telemetry/csv`, `GET /components/{id}/telemetry`.
**Code:** [`app/services/telemetry_service.py`](../backend/app/services/telemetry_service.py).
**Reference gateway:** [`scripts/telemetry_gateway.py`](../backend/scripts/telemetry_gateway.py).

Any source that can produce timestamped rows can feed it:
- a retrofit sensor kit (accelerometer and temperature probe on the machine,
  plus a trip counter),
- a CSV exported from the lift controller's event log,
- a building's lift monitoring system.

| Column | Effect on the component record |
|---|---|
| `trips`, `run_seconds` (increments) | Add to load cycles and operating hours through the per-component duty shares |
| `load_kg` or `load_percent` | Become the component's equivalent load (same load physics as the simulation), trip-weighted into its lifetime average |
| `vibration`, `temperature` | Latest reading becomes current; **monthly averages feed the early-warning trends**, so a sensor-fitted part is trended from continuous data |

How it behaves:
- **Idempotent:** the same (component, timestamp, source) is ignored if sent
  again, so a gateway on a flaky connection can safely retry.
- **Checked:** future timestamps, readings before installation and
  out-of-range values are rejected row by row, with reasons.
- **Traceable:** every row keeps its source, and every accepted batch is
  written to the audit chain.

## 3. Simulating a real component, and saving scenarios

**Where:** component page → **Simulate**, or Simulation page → **Start from a
real component**. API: `POST /simulation/start/{id}`,
`POST|GET /simulation/scenarios/{id}`.

**Seeding.** The simulation starts from the part's real record: age,
counters, service history and readings. Its hidden true wear starts at
today's life-model estimate.

**Calibration.** The simulated temperature and vibration are anchored to the
unit's own recorded readings. Changing the load then moves them from that
real baseline instead of from a generic lift.

**Implied load.** The part's recorded load is converted back to an average
car load. For a motor there are two answers, because a motor feels an empty
car and a full car alike, either side of the counterweight balance. Both are
shown.

**Saving.** **Save to passport** stores the focus part's simulated future in
its own table, labelled SIMULATION. It is shown on the passport and the
component page. Saving never changes the component and is never counted in
dashboards, forecasts or reports; a test proves the dashboard is identical
before and after a save.

## What each of the 13 parameters can now come from

| Parameter | Technician (measured) | Sensor / controller | Still manual |
|---|---|---|---|
| Component type, material, grade | | | ✓ at installation (QR scan) |
| Age | | | ✓ install date at installation |
| Operating hours | | ✓ `run_seconds` | |
| Load cycles | | ✓ `trips` | |
| Average load | | ✓ `load_kg` / `load_percent` | |
| Vibration | ✓ motor bearing vibration | ✓ | |
| Temperature | ✓ motor bearing temperature | ✓ | |
| Service visits, repairs, failures | ✓ service events | | |
| Inspection score | ✓ **computed from measurements** | | |
| Days since service | ✓ | | |

## Still missing, honestly

- **Real measurements.** Everything above is ready to receive real data, but
  the demo database is still the synthetic seed. The next step is a
  **pilot**: one lift, one technician using the inspection form, and one CSV
  export or sensor feed.
- **Verified limits.** The inspection limits must be checked against the
  purchased standards and manufacturer data.
- **Per-component duty shares.** The shares that turn lift trips into
  per-component cycles and hours are engineering judgements
  ([kone-assumptions.md §2.2](kone-assumptions.md)).
- **Where removed parts went.** Still only captured if a workshop records
  outcomes. That remains the one thing that would make the AI's accuracy
  claim real.
