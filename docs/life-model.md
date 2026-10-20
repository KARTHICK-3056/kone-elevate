# Material composition and usage-adjusted life

**Written 24 September 2026, in response to the first mentor review.**
Code: [`backend/app/ml/life_model.py`](../backend/app/ml/life_model.py).
Tests: [`backend/tests/test_life_model.py`](../backend/tests/test_life_model.py).
Surfaced on the passport as two cards: *Material composition and
characteristics*, and *Pre-emptive life projection*.

The review raised three points. Scope, as agreed: the four drivetrain focus
components first — **traction motor, steel rope, sheave, brake** — and then
the **overspeed governor** and **door operator** (see §5), so every component type in the registry has an expected
life. A type added later without a mechanism returns `supported: false`
rather than a number with nothing behind it.

---

## 1. "The passport must include what each component is made of"

A passport that says only *Steel* or *Cast Iron* cannot explain why two
sheaves of the same type last differently. The passport now records the
**material grade**, not just the dominant material:

| Component | Grades catalogued | Life factor |
|---|---|---|
| Motor | PM synchronous Class F (reference) · PM Class H · induction Cu Class F · induction Al Class B | 1.00 · 1.20 · 0.95 · 0.80 |
| Steel rope | fibre core (reference) · IWRC · compacted-strand IWRC | 1.00 · 1.15 · 1.30 |
| Sheave | ductile iron EN-GJS (reference) · grey iron EN-GJL · hardened steel | 1.00 · 0.80 · 1.30 |
| Brake | cast-iron drum + organic lining (reference) · steel + sintered lining · polymer composite | 1.00 · 1.30 · 0.75 |

For each grade the passport shows:

- **Constituents with mass fractions**, e.g. a PM motor is about 42%
  electrical steel, 33% frame, 15% copper and 3% NdFeB magnets.
- **Properties that drive wear**: insulation class, groove hardness, lining
  type, wire tensile grade.
- **Life factor and the reason for it.** This is the mentor's steel-vs-plastic
  point: a polymer-composite brake lining gets ×0.75 because polymers wear
  faster and degrade with heat, and a sintered metallic lining gets ×1.30.
- **Material recoverability** (the metal share of the bill of materials),
  which feeds gate 3 of the decision flow (Material Recovery vs Dispose).
- **Which constituents are separable sub-components** (bearings, brake shoes,
  springs, hubs, coils ...), which is what Component Recovery may name.
- **A formal grade designation and the standard it is graded under**, shown
  after the grade name (e.g. *Steel with induction-hardened grooves —
  42CrMo4+QT*, EN 10083-3, ≈ AISI 4140), plus a **part-by-part specification**
  for assemblies: a motor's M270-50A laminations (EN 10106), 42CrMo4 shaft,
  100Cr6 bearings (≈ AISI 52100) and class F insulation (IEC 60085); a
  brake's EN-GJL-250 drum, 51CrV4 springs and SAE J866 lining code.

| Component | Grade → designation (standard) |
|---|---|
| Motor | PM class F / H → M270-50A core, 42CrMo4 shaft (EN 10106, EN 10083-3, IEC 60085) · induction Cu → M400-50A, C45E · induction Al → M600-50A, C45E |
| Steel rope | 8x19S-FC 1570/1770 · 8x19S-IWRC 1770 · 8xK19S-IWRC 1770/1960 (EN 12385-5, wire EN 10264-2) |
| Sheave | EN-GJS-600-3 (EN 1563, ≈ ASTM A536 80-55-06) · EN-GJL-250 (EN 1561, ≈ ASTM A48 Class 40) · 42CrMo4+QT (EN 10083-3, ≈ AISI 4140) |
| Brake | EN-GJL-250 drum + SAE J866 FF · C45 disc + J866 GG sintered · PA66-GF30 housing + J866 EE |
| Governor | EN-GJL-250 sheave · C45E+QT sheave · EN AC-46000 housing (≈ A380); type examination EN 81-50 5.3 |
| Door operator | EN AW-6063-T6 header (≈ AA 6063-T6) · S235JR header + ISO 606 chain · PA66-GF30 track |

These are **typical grades for each construction**, cited by standard - not
read from a supplier. The passport says so, and each must be confirmed
against the nameplate, mill certificate or bill of materials before it is
relied on.

The grade is stored in the new `components.material_grade` column (migration
`0016`). When none is recorded, the **industry-standard grade for the
material** is attached (`INDUSTRY_DEFAULT_GRADES`) and shown everywhere with
the suffix **"(industry standard - assumed, not recorded)"**, together with its
typical composition. Where a material allows more than one grade, the assumed
one is the shortest-lived of them (a grey-iron sheave, a copper-wound
induction motor, a fibre-core rope), so an assumption can never flatter a
component's life - a test enforces this. The assumption is derived on read and
never written to the record, and the decision flow still names recoverable
sub-components only from a *recorded* grade. A recorded grade that doesn't fit
the material, such as a "hardened steel" grade on a cast-iron sheave, is
rejected and the industry-standard grade is used instead. **Not Determined**
remains only for a material with no catalogued grade.

---

## 2. "On what basis do you determine the life of a component?"

### The model

A physics-of-failure life-consumption model based on Miner's rule. It is
simple enough to check with a calculator:

```
life consumed  D = calendar age × ageing rate ÷ (design life × material factor)

ageing rate = (time share + (1 − time share) × duty × load)
              × thermal × vibration × maintenance
```

- **Design life** is the type's nominal life at design duty (motor 25 years,
  rope 12, sheave 28, brake 18). These are prototype values.
- **Time share** is the part of ageing that happens whether or not the lift
  runs: corrosion, lubricant ageing, insulation ageing.
- Each **stress factor** comes from the physics of that component's own
  failure mechanism:

| Component | Dominant mechanism | Load law | Heat | Vibration |
|---|---|---|---|---|
| Motor | Bearing fatigue and insulation ageing | load^1.5 (bearing L10 ∝ load³, ISO 281, softened for the whole machine) | Doubles every 10 K above (limit − 10 K) — the Arrhenius "10 K rule" | Yes |
| Steel rope | Bending fatigue over the sheave | load^2 (Feyrer: rope life falls steeply with tension) | Not dominant | No |
| Sheave | Groove wear (Archard) | load^1 (wear ∝ contact pressure) | Not dominant | Yes |
| Brake | Lining wear per stop | load^1 (energy per stop ∝ moving mass) | Doubles every 15 K above (limit − 10 K) | No |

**Evidence beats the model.** Life consumed is also estimated from the
inspection score, and the *worse* of the two governs. When they disagree by
more than 25 points, the passport flags it: "worn more than usage explains"
points to a fault the counters can't see.

### What KONE actually collects, and what it does to the prediction

Every input on the passport carries a data-source badge. For the life model:

| Input | Where a KONE deployment would get it | Status |
|---|---|---|
| Load cycles | Equipment API movement events (one journey = one cycle, apportioned per component — `kone_features.APPORTIONMENT`) | Published API |
| Running hours | Movement `durationSeconds` × journeys | Published API |
| Load | `decks[].loadPercentage` (% of rated load) | Published API |
| Days since service | Service Info API, `finishedDateTime` | Published API |
| Inspection condition | `equipmentConditionOnDeparture`: a 4-level code for the **whole lift** | Published API (proxy) |
| Temperature | No channel in any published KONE feed | **Not published** |
| Vibration | No channel in any published KONE feed | **Not published** |
| Material grade, install date | Bill of materials / installation record | Manual record |

What this means for the prediction:

- **Duty and load are the largest drivers, and they are the best-sourced
  inputs.** Usage speeding up or slowing down ageing can be computed from the
  published API. That is the core of what the mentor asked for.
- **Temperature and vibration have no public source.** KONE's connected
  services use equipment sensors, but those channels are not in the published
  API. Until a data-sharing agreement or a retrofit sensor exists, both
  factors run on demo values. They are bounded (thermal 0.8–4×, vibration
  1–2×) so an unmeasured default can't claim a large life gain.
- **The inspection code describes the lift, not the part.** It is used as a
  cross-check, not as a measurement of the component.
- **What only an inspector can measure** is listed per type on the passport:
  rope broken wires and diameter reduction (ISO 4344 discard criteria), sheave
  groove profile, brake lining thickness and air gap, motor insulation
  resistance. No feed replaces these.

---

## 3. "A pre-emptive evaluation based on actual usage, with a green/red graph"

The passport chart plots **life consumed (%) against calendar year**:

- **Grey dashed:** the design baseline, i.e. how the part would age at design
  duty.
- **Solid:** its actual history at the observed ageing rate.
- **Red dotted:** the projection forward at current usage.
- **Background bands:** green (< 50%, suitable to continue using), amber
  (50–80%, plan component recovery), red (> 80%, replace band).

The gap between the grey and red lines is the mentor's question answered
visually: how much actual usage has sped up (or slowed down) the life cycle.
Above the chart the passport states it in words, for example: "Ageing at 1.65×
the design rate. Actual usage is shortening this component's life by 9.9
years." It also shows:

- **Six plain-language figures:**
  - *Expected life* - how long this type and grade should last at normal
    (design) use: the type's design life x the grade's material factor.
  - *Actual age* - time since installation.
  - *Usage-based age* - how old it is in wear terms, given how hard it has
    been used (life used x expected life). Older than the actual age means it
    has been used harder than design.
  - *Life used* - usage-based age as a share of the expected life.
  - *Remaining life* - years until 100% used if today's usage continues.
  - *Projected total life* - actual age + remaining life, against the
    expected life.
- **The dates it passes half of its adjusted life and enters the replace
  band, and its end of life**, at current usage.
- **Status:** `OK` / `WATCH` (half-life within 2 years) / `PLAN` /
  `ACT` / `OVERDUE`.
- **What the life position implies**, through the same decision flow as the
  assessment: Continue Using – No Changes Required while under half its
  adjusted life; Component Recovery while under the replace band *and* the
  type has separable sub-components; otherwise Material Recovery if the
  material allows it, else Dispose - and whether it **agrees with the AI
  assessment**. The two are independent models, so agreement corroborates
  and disagreement is a reason to look. A steel wire rope has no separable
  sub-components, so it goes straight from Continue Using to Material
  Recovery.

The safety gate is untouched. Rope and brake still carry MANDATORY HUMAN
INSPECTION whatever this projection says.

---

## 4. Why predicted (effective) age now tracks calendar age

Effective age ran well ahead of calendar age across the fleet (median ratio
1.41 on the held-out test set, 1.56 on the demo fleet, one part at +84
years). The gap was closed by fixing the model, not by copying calendar age
or adding an offset:

1. **History-aware stress factors.** Vibration and temperature are integrated
   over the part's dated service readings, from new condition at
   installation, instead of applying today's reading to its whole life.
   Historical maintenance comes from the service count over the part's life.
   Current readings drive only the forward projection
   (`historical_ageing_rate`, `history_multiplier` on each factor).
2. **Competing mechanisms, not compounding ones.** Mechanical (load ×
   vibration) and thermal stress are combined as the maximum of the two
   (whichever mechanism governs), not multiplied together.
3. **Calibrated nominal point** (`app/ml/life_calibration.py`,
   `models/life_calibration.json`). The reference load utilisation and
   service interval per component type are the medians of the training data
   (the model had assumed 60% load and a 180-day service interval against a
   fleet at ~67% and ~260 days). The inspection-score → life-consumed mapping
   is fitted too, and an inspection overrides the usage model only when it
   exceeds it by more than the fitted grading scatter (1.645 σ).
   The calibration is fitted on `train.csv` only and refitted every time the
   classifier is retrained (`scripts/train_model.py`).

| Effective vs calendar age | Before | After |
|---|---|---|
| Held-out `test.csv`: median effective/calendar ratio | 1.41 | 1.11 |
| Held-out `test.csv`: median \|gap\| | 4.46 yr | 2.69 yr |
| Held-out `test.csv`: within 25% of calendar age | 33% | 48% |
| Demo fleet: median ratio | 1.56 | 1.14 |
| Demo fleet: mean \|gap\| | 12.5 yr | 4.5 yr |

"Before" covers the four drivetrain types; "After" also includes the control
boards now covered by the life model (1,430 held-out rows, 46 demo components).

`tests/test_recommendation_categories.py` guards this as a regression check.

---

## 5. The overspeed governor and the door operator

- **Governor** - wears by governor-rope groove wear and ageing of the tripping
  linkage (pivots corrode and springs relax between tripping tests, so 35% of
  its ageing is calendar time). Load matters only weakly (exponent 0.5): the
  governor rope is tensioned by its own weight. Grades: cast-iron sheave
  (reference), machined steel sheave (x1.1), compact aluminium housing (x0.9).
  Forecast: bearing / pivot wear, tripping-speed drift, life milestone; 60-day
  lead time.
- **Door operator** - wears per door cycle (rollers, belt, lock). Grades:
  aluminium header with belt drive (reference), steel linkage / chain drive
  (x0.9), polymer-composite track (x0.8). Forecast: roller and track wear,
  door fault trend, life milestone; 30-day lead time.

The governor has a measured inspection checklist (tripping-speed deviation,
governor-rope groove wear, overspeed switch, gripping jaw, tripping linkage);
the door operator does not yet, so its inspection score is entered directly.

(The control board was removed as a component type - migration
`0021_remove_control_board`.)

---

## Honest limits

- Every exponent, life factor, threshold and bill-of-materials fraction is a
  **documented prototype approximation**, not a KONE specification and not
  calibrated against real removals. Each one carries its reasoning in code, so
  an engineer can disagree with a specific number.
- The history line assumes usage was constant since installation, because only
  cumulative counters exist. A real deployment accumulating monthly telemetry
  would plot the actual path.
- Calibration needs the same thing the classifier does
  ([kone-assumptions.md §4](kone-assumptions.md)): removal records that say
  what condition a part was in when it came out.
