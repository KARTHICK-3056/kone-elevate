# Forecasting and component-recovery capacity

> **Synthetic data.** The forecaster is fitted to the same simulator as the
> disposition classifier. Every figure here describes simulated wear physics,
> not observed KONE removals.

The disposition classifier answers *"what should happen to this component?"*.
This model answers the other half of the pitch: *"what is coming off the fleet,
when, and can the workshop absorb it?"*

---

## 1. Why survival analysis

Most components in a fleet have **not yet** reached end of life. Fitting a
regression on only the ones that already have throws away every healthy
component and biases the estimate badly short.

Survival analysis is built for exactly this. A component still healthy when
observation stopped is **right-censored**: it contributes the information
"it lasted at least this long", which is real evidence, not a missing value.
In the training data, **41% of rows are censored** - so this is not a
theoretical nicety, it is most of the dataset.

`tests/test_survival.py::test_ignoring_censoring_biases_the_estimate_downwards`
asserts this directly: it fits the same data twice, once treating censored
rows correctly and once pretending they were events, and checks the naive fit
understates median life.

## 2. Why Weibull AFT

| Requirement | Why Weibull AFT |
|---|---|
| `P(event within h)` for arbitrary h | Parametric, so `S(t\|x)` is closed-form and extrapolates past the last observed event - a Cox baseline hazard cannot |
| A physical sanity check | The shape parameter *k* has a meaning: **k > 1 means hazard rises with age**, which is what wear-out looks like. The fitted k is **1.51**. A k ≤ 1 would mean the model had stopped describing wear-out |
| Intervals | Coefficient covariance gives `Var(x'β)`, mapped through the survival function to a CI on the probability |
| Auditability | ~150 lines in `app/ml/survival.py`, likelihood written out, rather than a dependency |

The implementation is hand-written rather than imported from `lifelines`. That
is a deliberate trade: it avoids adding `autograd`/`formulaic` to a build that
was just made reproducible, and - more importantly - a hand-written likelihood
can be *proved* correct by recovering known parameters from simulated data,
which a library call cannot. See §6.

## 3. Where the training data comes from

The generator's wear function is **linear in age** once the per-component
latent draws are fixed:

```
wear(t) = [0.34·duty·n₁ + 0.18·duty·n₂ + 0.14]/L · t
          + [0.10·load_stress + 0.13·(1−mq) + 0.11·env + ε]
```

because operating hours and load cycles both accumulate linearly with age at a
rate set by duty. So the age at which a component stops being suitable to
continue using has a **closed form** - no time-stepping loop, and no simulation
noise in the event time itself.

`generate_survival_dataset` therefore:

1. draws the same latent parameters as the classifier's generator,
2. solves `t* = (threshold − intercept) / slope` for the crossing age,
3. picks an observation age uniformly in `(0.2, t*)` - i.e. observes the
   component **while it is still healthy**,
4. emits the observable features *at that age*,
5. draws a follow-up window `F ~ U(0.5, 6)` years, giving
   `duration = min(t* − t_obs, F)` and `event = (t* − t_obs) ≤ F`.

The crossing time derives from latent variables (duty, maintenance quality,
environmental stress) the model never sees - exactly as the classifier's label
does. **No target leakage.**

The classifier's dataset is untouched by this: `generate_dataset` is
byte-identical to the run that produced the published classifier metrics.

## 4. The at-risk population (the thing that is easy to get wrong)

A component whose latest assessment is already past Continue Using has
**already crossed** the threshold this model forecasts the crossing of. Feeding
it to the survival model produces a meaningless "it should have crossed
already" probability of ≈1, piling the entire fleet into the first quarter.

The first version of this page did exactly that: 34 of 40 forecast removals
landed in quarter one. That is not a forecast, it is a restatement of the
current backlog with extra steps.

So `forecast_service.split_fleet` separates:

| Bucket | Definition | Reported as |
|---|---|---|
| `already_due` | latest assessment is Component Recovery / Material Recovery / Dispose | **Current backlog** - this quarter's workload |
| `at_risk` | still Continue Using, or never assessed | **Forecast** - the population the model is valid for |

Survival analysis applies to the at-risk set. Both numbers are surfaced; the
backlog is queued ahead of the first quarter in the capacity plan, so the
workshop is never modelled as starting empty.

## 5. From probabilities to a plan

**Expected removals in a quarter** = Σ over components of
`P(event by end of quarter) − P(event by start of quarter)`.

Summing probabilities rather than counting thresholded predictions is
deliberate: it is an unbiased estimator of the count, and it does not discard
the information in a component that is 45% likely to need attention.

**Capacity**: forecast removals × per-type labour hours × routing rate,
against declared workshop hours per quarter. The planner reports utilisation
per quarter, names the bottleneck component type, and produces a levelled
intake schedule that **carries un-absorbable work forward** rather than
silently dropping it, so the consequence of a breach accumulates visibly.

> **PROTOTYPE ESTIMATES.** Labour hours per type, workshop capacity
> (1,200 h/quarter) and the 45% component-recovery routing rate are illustrative
> configuration values in `app/core/config.py`, **not** KONE workshop
> standards. They are the first thing to replace with real routing data.

## 6. Validation

**Parameter recovery** (`tests/test_survival.py`) - the implementation is
fitted to data with known ground truth and must recover it:

| Check | Result |
|---|---|
| Recovers β, intercept and shape with no censoring | within ±0.06 |
| Recovers them under ~50% censoring | within ±0.08 |
| Beats the naive "treat censored as events" fit | asserted |
| `P(event within h)` monotone in h, bounded [0,1] | asserted |
| CI brackets the point estimate | asserted |

Standard errors were separately verified to shrink as `1/√n` across a 64×
range of sample sizes, confirming the covariance rescaling in `fit`.

**Backtest** (`models/forecast_metrics.json`) - predicted vs actual event
counts on a held-out split. Only rows whose follow-up window covers the
horizon are scored: a row censored at 2 years tells you nothing about what
happened at 5, and counting it as a non-event would flatter the error.

| Horizon | Scored | Predicted | Actual | APE |
|---|---|---|---|---|
| 3 months | 2,500 | 140.2 | 183 | **23.4%** |
| 6 months | 2,500 | 343.9 | 349 | **1.5%** |
| 12 months | 2,251 | 656.2 | 608 | **7.9%** |
| 24 months | 1,807 | 907.5 | 881 | **3.0%** |

MAPE by component type ranges 9.1% (Steel Rope) to 22.0% (Brake); **13.1%
overall**.

The 3-month horizon is the weakest and that is worth stating plainly: only 183
events occur in that window, so small absolute errors produce large ratio
errors. The model is most trustworthy at 6-24 months, which is fortunately the
range a capacity planner actually schedules in.

## 7. Limitations

1. **Same simulator, same caveat.** The forecaster learns the generator's wear
   physics. If real degradation differs, it has learned the wrong thing.
2. **Valid only for the at-risk population** (§4). It cannot tell you anything
   about a component that has already crossed the threshold.
3. **Weakest at short horizons** (§6).
4. **Capacity constants are illustrative** (§5) - the forecast half is modelled,
   the workshop half is assumed.
5. **No competing risks.** A component removed for an unrelated reason
   (modernisation of the whole lift, site closure) is not modelled; the only
   modelled event is crossing the wear threshold.
6. **Linear wear.** The closed-form crossing age depends on wear being linear
   in age, which is true *of the simulator*. Real wear may accelerate.

## 8. Running it

```bash
python scripts/train_forecast.py                     # fit + backtest + persist
python scripts/train_forecast.py --regenerate --records 20000
```

| Endpoint | Returns |
|---|---|
| `GET /forecast/eol?horizon=&group_by=type\|site\|region` | Expected removals per quarter with intervals, plus current backlog |
| `GET /forecast/capacity?horizon=` | Utilisation per quarter, bottleneck type, levelled intake schedule |
| `GET /forecast/model?full=` | Fit summary and the published backtest |
| `POST /forecast/reload` | Reload after retraining |

The UI is the **Forecast** page: stacked quarterly removals, the capacity
utilisation strip (red above 100%), the intake schedule, and the forward
supply/demand table.
