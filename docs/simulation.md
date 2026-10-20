# Interactive lift simulation

**Written 24 September 2026.** Page: **Simulation** in the sidebar
(`/simulation`, sign-in required).
Code: [`backend/app/simulation/`](../backend/app/simulation/),
[`frontend/src/pages/Simulation.jsx`](../frontend/src/pages/Simulation.jsx),
[`frontend/src/components/ElevatorScene.jsx`](../frontend/src/components/ElevatorScene.jsx).
Tests: [`backend/tests/test_simulation.py`](../backend/tests/test_simulation.py),
[`frontend/src/test/simulation.test.jsx`](../frontend/src/test/simulation.test.jsx).

## What the user does

The user sets **one number: the average load the car carries per trip**
(0–1100 kg, the EN 81-20 overload limit). They can run, pause, step or restart
the lift. Load changes take effect from the next simulated month.

Everything else comes from the **KONE API first**, and is simulated only
where no KONE API publishes it. For each of motor, steel rope, sheave and
brake, the page shows all **13 model parameters**:

- component type, material, age
- operating hours, load cycles, equivalent load
- vibration, temperature
- service visits, repairs, failures, inspection score
- days since service

Every life-span figure on the page is calculated from those 13 parameters:

- the usage-adjusted life model,
- the pre-emptive issue forecast,
- the trained AI classifier.

## Where the numbers come from — the honest version

**There is no real KONE data in this build.** The recorded KONE API responses
carry KONE's published field names, but their own README states the values
were invented for the prototype, and no live call has ever been made. So the
simulation cannot be "trained on real-world trends". Instead, every fixed
value takes the most real source that exists for it, and the page labels each
one:

| Source | Used for |
|---|---|
| **KONE API** (through `kone_adapters.equipment_telemetry` and `service_order_details`) | **8 of the 13 parameters.** Floors served and floor height, trip duration (→ operating hours), one cycle per journey (→ load cycles), the default load (`loadPercentage` → equivalent load), and **the reference lift's KONE record at month 0**: service count, repairs, failures, days since the last service order and the condition code on departure (→ inspection score), all through the platform's own KONE feature mapping (`kone_features.derive_features`). These are **example values today**. The same code reads the live lift once credentials are configured, and the simulation then recalibrates with no code change. The page shows which mode ran. |
| **Simulated** | Only what no KONE API publishes: **vibration, temperature and each part's age** (KONE publishes no installation date), plus the forward evolution of every count after month 0. |
| **Your input** | The average load per trip once you change it from the KONE default. |
| **Standard** | Trips per day: ISO 25745-2:2015 usage category 3 (300 trips/day; the table values come from public summaries and are unverified against the purchased text). 75 kg per person and the 110% overload limit (EN 81-20). |
| **Physics** | How load stresses each part (below), heat, vibration growth, Miner's-rule damage. |
| **Assumption** | Lift geometry (1000 kg rated, 1100 kg car, 50% counterweight balance), machine-room ambient temperature, and a 6-month service interval **only while the KONE orders cannot give one**. |

### KONE first, and what happens when the KONE record is too thin

`reference.kone_record()` reads the reference lift's KONE data and returns the
month-0 starting values plus two rates the forward months use:

- **service interval** - the mean gap between KONE preventive visits, when
  there are at least two;
- **callout rate** - KONE repair/callout orders per month, when the orders
  cover at least 12 months (a shorter window cannot tell a rate from chance).
  The rate is shared across the four drivetrain parts.

When the KONE record cannot establish a rate, the simulation uses its own
figure and the page says why. The recorded example orders hold **one**
preventive visit over **6.5 months**, so today both rates fall back: visits
every 6 months (assumption) and faults from the wear-driven fault model. The
parameter table shows each row's first source and, where it differs, what
carries the value forward ("KONE API, then Simulated"). The month-0 counts are
lift-level, exactly as the KONE feature layer maps them - KONE records service
orders per lift, not per component.

A run started from a real component (`?component=...`) uses that component's
own record instead; its companion parts start new rather than borrowing the
KONE reference lift's record.

## How load becomes stress

Per-trip load varies around the user's average (gamma distribution, CV 0.7),
because a real lift runs nearly empty and nearly full within the same day.
Each part feels that load differently:

| Part | Stress follows | Consequence |
|---|---|---|
| Steel rope | car + load (car-side tension) | Heavier load, faster wear |
| Sheave, brake | car + load + counterweight (whole moving mass) | Heavier load, faster wear, but diluted by the fixed masses |
| Motor | \|load − balance\| + friction and acceleration of the moving mass | **U-shaped**: easiest at a half-full car, hard when empty *or* full |

Damage follows Miner's rule, so the equivalent load is (E[s^p])^(1/p) with the
mechanism's exponent. A few heavy trips cost more than their average suggests.

Motor heat: about 70% of motor losses are fixed (iron losses, the cooling
fan), and copper losses scale with torque². The model is sized so that at
full rated load the housing runs near its limit (~87 °C against 85 °C), as a
correctly sized traction motor does.

## Truth vs. what the models see

The simulation keeps two layers deliberately apart:

- **True wear:** hidden. It grows each month by the same damage laws the life
  model documents, plus unit-to-unit variation and month-to-month scatter that
  no model is told about.
- **Observations:** vibration, temperature and the inspection score are read
  only at service visits, with measurement noise. The life model, the
  forecast and the AI classifier work **only** from these observations.

The chart plots both, the model's estimate against the simulated truth, so
the accuracy of the estimates is visible rather than assumed.

## Closing the loop: does the pre-analysis work?

At each service visit, the estimate decides what to do:

- **Estimate below the replace band:** the part continues in use unchanged.
- **Estimate in the replace band:** replace it proactively. The removed part
  is given its category through the decision flow (Component Recovery,
  Material Recovery or Dispose); the complete removed part never goes into
  another lift.
- **Part reaches true end of life between visits:** it **breaks down** and is
  replaced reactively.

The KPIs count the outcomes:

- proactive replacements vs. breakdowns,
- where the removed parts went (`to_component_recovery`,
  `to_material_recovery`, `to_dispose`) and callouts,
- early warnings raised, and **how many months of warning each replacement
  had**.

That is the pre-analysis, measured.

## The 3D model

A three.js model of the lift: shaft and floors, the car with passengers, the
counterweight, ropes, traction sheave, motor and brake.

- **Visual only.** It is driven by the same results: the number of passengers
  follows the load, and parts are coloured by their life band (green / amber /
  red).
- **Condition cues:** the motor glows with temperature, the machine and car
  shake as vibration nears its limit, and the brake flashes at each stop.
- **Camera:** drag to orbit, scroll to zoom. **Whole lift** and **Machine
  room** buttons switch views.

The car's travel is animated in real time; it is not simulation time.

## Limits

- It is a model, not a record. Shapes and directions are physically grounded;
  absolute lifetimes rest on the prototype design lives and exponents in
  [life-model.md](life-model.md).
- Until KONE credentials exist, the "KONE API" values are recorded examples.
- Trips per day are fixed at the ISO category, because the user controls only
  the load.
