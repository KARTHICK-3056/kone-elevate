# Pre-emptive issue forecast (pre-analysis)

**Written 24 September 2026, in response to the first mentor review.**
Code: [`backend/app/ml/early_warning.py`](../backend/app/ml/early_warning.py),
[`backend/app/services/early_warning_service.py`](../backend/app/services/early_warning_service.py).
Tests: [`backend/tests/test_early_warning.py`](../backend/tests/test_early_warning.py).

The review asked for **pre-analysis, not post-analysis**: predict the issue
well before it arrives, tell the technician what to do before then, and show
the justification and evidence for the prediction.

## Where it appears

- **When an AI assessment is run.** The result card shows a *Pre-emptive
  issue forecast* strip. It gives a headline (e.g. "3 issues predicted ahead.
  Next: rope approaching discard criteria in about 10 months — act by
  2027-05-18") and one chip per predicted issue. **Show evidence,
  justification and measures** expands the full detail.
- **Component page and QR passport:** a full *Pre-emptive issue forecast*
  card, always current.
- **Audit chain:** every assessment records which issues were predicted,
  their predicted dates and their confidence (`predicted_issues` in the
  PREDICT audit entry). This is tamper-evident proof that an issue was
  predicted *before* it happened, and the basis for later measuring how
  accurate the forecasts were.

Scope: motor, steel rope, sheave, brake, governor and door operator (the same
types as the [life model](life-model.md)).

## How an issue is predicted

The idea comes from reliability-centred maintenance, where it is called the
**P–F interval**. A developing defect becomes detectable (P) well before it
becomes a failure (F). The forecast looks for that detectable stage in two
ways.

**1. Condition trends (leading indicators).** Vibration, temperature and
inspection score are recorded at each service visit. A least-squares line
through the last 8 readings is extended to the indicator's limit, and the
crossing date is the predicted arrival of the issue. A trend needs at least 3
readings spanning 6 months, and drift under 1% of the limit per year counts
as stable. Anything less is reported as "too few readings" rather than
extrapolated.

**2. Usage-adjusted life.** This is the date the component enters the
replace band at its current rate of use (from the life model).

Each indicator is mapped to a named failure mode of that component type:

| Component | Indicator → predicted issue |
|---|---|
| Motor | vibration → bearing wear / misalignment · temperature → winding insulation over-temperature · inspection → condition decline · life → end of life |
| Steel rope | inspection → approaching ISO 4344 discard criteria · vibration → uneven rope tension · life → end of life |
| Sheave | vibration → groove wear / misalignment · inspection → groove profile beyond gauge · life → end of life |
| Brake | temperature → lining overheating / fade · inspection → lining wear to minimum thickness · life → end of life |

## Justification: why we believe it

One extrapolated line is weak evidence. Each predicted issue is therefore
checked against signals produced **independently** of the trend:

| Signal | What it is | Agrees when |
|---|---|---|
| Usage-based life model | Physics-of-failure, uses no condition readings | Past half of its adjusted life, or replace band within 3 years |
| Survival model | Weibull model fitted on the fleet | P(no longer suitable to continue using within 12 months) ≥ 30% |
| AI classifier | Random Forest on the current snapshot | Verdict is anything other than Continue Using, or DEFER_TO_INSPECTION |
| Service record | Recorded repairs and failures | At least one |

**Confidence** = 0.4 × (quality of the trend fit, R²) + 0.6 × (share of
independent signals that agree), capped at 95%. It is labelled HIGH (≥ 70%),
MEDIUM or LOW. Every signal is shown with its reading and whether it agreed,
so a technician can see exactly why a warning was raised and disagree with a
specific part of it.

The survival model is only used where it is valid. It was fitted on
components still suitable to continue using. For a component the classifier
already rates past Continue Using, the survival model's probability
saturates near 100% and only echoes the classifier, so it is left out rather
than counted as a second, independent vote.

## Evidence shown

- **Trend issues:** a chart of the recorded readings (dots), the fitted trend
  extended to the limit (dashed line), the limit and "today". Alongside it:
  the slope per year, R² and the number of readings.
- **Life issues:** life used, ageing rate, and each stress factor's
  multiplier.
- **Every indicator monitored**, including those that are stable or have too
  little history. A forecast that only showed what it flagged would hide how
  much it looked at.

## Measures, timed by lead time

A warning is only useful if the part and the visit can be arranged in time.
Each issue carries:

- **Predicted date**
- **Act-by date:** predicted date minus the type's planning and procurement
  lead time. Prototype lead times: motor 90 days, rope 60, sheave 75,
  brake 45.
- **Urgency:**
  - `ACT_NOW` — within the lead time
  - `WITHIN_A_YEAR`
  - `PLAN_AHEAD` — up to 3 years
- **Specific measures to take before the issue arrives**, e.g. "Measure rope
  diameter at the most-used section", "Count broken wires per reference
  length (ISO 4344)", "Order a replacement rope set now".

A limit that has **already been crossed** is labelled `PRESENT` ("limit
already crossed — a current problem"), never passed off as a prediction. The
headline reports present problems and predicted ones separately.

## Honest limits

- The service history the trends are fitted on is **synthetic** in this
  build, so every prediction here demonstrates the method, not real accuracy.
- Linear extrapolation is the simplest defensible trend. Real wear often
  accelerates near the end of life, which makes a linear forecast
  *optimistic* about timing. The lead-time buffer partly offsets this.
- Limits, lead times and confidence weights are documented prototype choices,
  not KONE specifications.
- Real validation is straightforward once real data exists: the audit chain
  already holds each prediction and its date, so comparing those against
  later inspection and removal records gives the forecast's actual hit rate
  and lead time.
