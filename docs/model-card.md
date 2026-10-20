# Model card - RF-v1.0-synthetic

Shaped after the EU AI Act's Annex IV technical-documentation headings, so
this file is reusable if the classification question in `plan.md` §6 (Aligning
to KONE) is ever revisited. It is **not** a regulatory submission: no
conformity assessment has been performed, and this system is assessed as
outside Annex I high-risk scope for the reasons given in that section (it
scores components already removed from service; it never operates a lift or
returns a safety-critical part to service without the mandatory human
inspection the safety gate enforces).

Numbers below are read from `backend/models/metrics.json` after training on
`backend/data/synthetic/dataset.csv` (10,000 rows, seed 42). Regenerate both
with `python scripts/generate_data.py && python scripts/train_model.py` and
this file's figures should reproduce within noise.

---

## 1. Intended use

**Purpose.** Advisory disposition triage for elevator components removed (or
being considered for removal) during service or modernisation: recommend
Continue Using – No Changes Required / Component Recovery / Material Recovery /
Dispose (via the four-gate decision flow in `app/ml/decision_flow.py`), or
abstain (`DEFER_TO_INSPECTION`) when
the model is not confident enough to be useful.

**Intended users.** Field technicians and component-recovery workshop engineers, as
one input among several to a human decision - never as an automated release
mechanism.

**Out of scope.**
- Authorising a component's return to service. The safety gate
  (`app/ml/predict.py::_apply_safety_gate`) makes this structurally
  impossible for steel ropes, brakes and governors; for every other type the
  output is still advisory only (`RECOMMENDATION_DISCLAIMER`).
- Any real-time or safety-instrumented function of an operating lift.
- Any use on data outside the trained feature contract
  (`app/ml/features.py::FEATURE_COLUMNS`).
- Production deployment on real KONE data without the validation programme in
  `plan.md` P6 (shadow mode against real removals before this model or its
  successor influences anything).

---

## 2. Training data

100% synthetic. `app/ml/generate_dataset.py` is a causal simulator (traffic,
maintenance quality and environmental stress drive a hidden wear variable;
every observable feature is a noisy view of that wear; the label comes from
thresholding wear, not from the model's own features - see
`docs/machine-learning.md` §4 for the full causal diagram). No real KONE
service, inspection, sensor or removal record was used or is available to this
project.

10,000 records, class distribution: Continue Using 15.6%, Component Recovery
25.4%, Material Recovery 56.4%, Dispose 2.6%. Labels follow the same decision
flow as the live recommendation, applied to the simulator's latent wear.

**Three-way split** (`app/ml/train.py`):

| Split | Records | Purpose |
|---|---|---|
| `dev` | 6,400 (64%) | Fed into `CalibratedClassifierCV`'s internal 5-fold CV |
| `conformal_calib` | 1,600 (16%) | Split-conformal threshold only - never seen by the classifier or the isotonic calibrators |
| `test` | 2,000 (20%) | Every metric on this page |

---

## 3. Model architecture

`Pipeline(OneHotEncoder + RandomForestClassifier)` wrapped in
`CalibratedClassifierCV(method="isotonic", cv=5)`. 400 trees, max depth 16,
`class_weight="balanced_subsample"`. Full hyperparameters in
`app/ml/train.py::DEFAULT_HYPERPARAMETERS`.

13 features (2 categorical, 11 numeric), contract shared by the generator,
trainer and inference path (`app/ml/features.py`) so training and serving
cannot drift apart.

---

## 4. Performance (random split, held-out test set, n=2,000)

| Metric | Value |
|---|---|
| Accuracy | 87.10% |
| Precision (macro) | 86.75% |
| Recall (macro) | 85.80% |
| F1 (macro) | 86.24% |
| F1 (weighted) | 87.17% |
| 5-fold CV F1 (macro), `dev`+`conformal_calib` only | 85.35% (+/- 1.23) |

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Continue Using – No Changes Required | 0.79 | 0.76 | 0.77 | 312 |
| Component Recovery | 0.76 | 0.80 | 0.78 | 508 |
| Material Recovery | 0.94 | 0.93 | 0.94 | 1,129 |
| Dispose | 0.98 | 0.94 | 0.96 | 51 |

Most errors are one category away on the wear scale. Material Recovery and
Dispose are separated by the material itself and are never confused with each
other on the test set.

### Cohort (temporal) validation - the honest number

Trained on the older 70% of (synthetic) installation years, tested on the
newer 30%:

| Metric | Random split | Cohort split |
|---|---|---|
| Accuracy | 87.10% | **80.54%** |
| F1 (macro) | 86.24% | 77.44% |

The ~10-point drop is the expected, honest cost of testing on genuinely
unseen (later) installations rather than a random shuffle. Publishing it,
not hiding it, is the point of this section.

---

## 5. Calibration

`CalibratedClassifierCV` (isotonic, 5-fold), fitted on `dev`, evaluated on
`test`:

| Metric | Value |
|---|---|
| Expected Calibration Error (ECE), 10 bins | **0.0134** |
| Brier score - Continue Using | 0.0494 |
| Brier score - Component Recovery | 0.0863 |
| Brier score - Material Recovery | 0.0572 |
| Brier score - Dispose | 0.0020 |
| Mean confidence (all) | 0.877 |
| Mean confidence (correct) | 0.896 |
| Mean confidence (incorrect) | 0.746 |

Reliability bins (mean confidence vs. observed accuracy) track the diagonal
within a few points across every populated bin from 0.4-1.0 - see the live
reliability diagram on the Analytics page or `GET /api/v1/model/calibration`.

---

## 6. Abstention (DEFER_TO_INSPECTION)

Split-conformal (LAC, Sadinle/Lei/Wasserman 2019) prediction sets at
alpha=0.1 (90% target marginal coverage), `q_hat = 0.5975`, computed on the
1,600-record `conformal_calib` split disjoint from both `dev` and `test`.
Abstain when the top-class confidence is below 0.5 **or** the prediction set
contains more than one class.

| Metric | Value |
|---|---|
| Abstention rate | **5.9%** (117 / 2,000) |
| Accuracy without abstention | 87.10% |
| Accuracy on the 94.1% answered | **89.3%** |
| Accuracy on the abstained 5.9%, if forced to answer anyway | 51.3% |

Read this as: the model is right 89.3% of the time when it answers, and it
correctly identifies the cases where it would otherwise be wrong far more
often (48.7% error rate on abstained cases vs. 10.7% on answered ones).

---

## 7. Explainability - three independent methods

| Method | Rank 1 | Rank 2 | Rank 3 | Scope |
|---|---|---|---|---|
| Gini (impurity) | inspection_score (26.3%) | operating_hours (15.7%) | load_cycles (11.9%) | Global |
| Permutation (f1_macro drop) | inspection_score (40.7%) | component_type (23.0%) | operating_hours (16.6%) | Global, on `test` |
| SHAP TreeExplainer | inspection_score (27.5%) | component_type (17.5%) | operating_hours (16.0%) | Global (mean \|value\|, 300-row sample) and per-prediction |

All three agree `inspection_score` dominates - a sanity check on the
generator, since assessed condition should matter most. Permutation and SHAP
both rank `component_type` well above where Gini puts it, which is exactly
the high-cardinality bias Gini is known for (`docs/machine-learning.md` §7).
Per-prediction SHAP factors are returned alongside the blended
importance/design-envelope factors on every `/predict` response
(`shap_factors`), computed from one representative fold of the calibrated
ensemble (`app/ml/model_registry.py::explainer_pipeline`).

---

## 8. Cost-sensitive decision analysis

`app/ml/cost_matrix.py` defines a reviewed, versioned (`v1`) relative-cost
table: optimistic errors (predicting a less-conservative disposition than the
truth) cost more than conservative ones, and any optimistic error on a
safety-critical component type is further multiplied.

| Strategy | Mean expected cost | Mean realised cost |
|---|---|---|
| Argmax probability (the classifier's `underlying_recommendation`) | 0.561 | 0.660 |
| Cost-optimal | 0.459 | 0.466 |

The two strategies disagree on 4.50% of test-set decisions. The API reports
both the argmax choice and this cost analysis (`cost_analysis` on every
prediction) so a reviewer can see where they diverge; `recommendation` itself
is not switched to the cost-optimal choice by default, to keep "the model's
answer" legible and auditable.

---

## 9. Known failure modes

- **Confusion around the Component Recovery category** (with Continue Using
  on one side and Material Recovery on the other) is the largest error mass in
  the confusion matrix - components genuinely near a
  policy threshold are hard, by construction of the simulator's label noise.
- **Temporal generalisation is materially worse than random-split metrics
  suggest** - see §4. Any claim using the 87.10%/86.24% figures without the
  cohort figures is materially misleading.
- **The model partly learns the simulator, not physical reality.** Where a
  real degradation relationship differs from the one modelled, the model has
  learned the wrong thing. This cannot be fixed without real labelled data
  (`plan.md` P6).
- **Gini importance overweights `component_type`'s true influence** relative
  to permutation/SHAP - use the latter two when the question is "does this
  feature actually help."

---

## 10. Human-oversight requirement

- Safety-critical component types (steel rope, brake, governor) always carry
  `safety_flag=true` and a mandatory-inspection message, regardless of
  confidence or recommendation. This is enforced in code
  (`is_safety_critical`), not by convention.
- `DEFER_TO_INSPECTION` routes low-confidence/ambiguous cases to a human by
  construction rather than presenting a guess as an answer.
- Every prediction is advisory (`RECOMMENDATION_DISCLAIMER`) and is never
  represented as a certification, approval or authorisation to operate an
  elevator, in the API or the UI.
- No prediction acts autonomously on a component's physical or lifecycle
  state; a human always initiates the resulting service event.

---

## 11. Retraining and monitoring

- Retrain: `python scripts/train_model.py` (regenerates data if missing;
  `--regenerate` forces a fresh synthetic dataset).
- `app/ml/model_registry.py` refuses to load a bundle pickled by a different
  scikit-learn/joblib version than the one currently installed
  (`ModelVersionMismatchError`), rather than silently unpickling something
  that may predict incorrectly.
- Drift: `python scripts/check_drift.py` computes PSI + KS per feature
  against the training distribution and exits non-zero on a significant
  shift - see its module docstring for how to point it at real assessment
  traffic once that exists. Nothing schedules it yet.
- Every prediction, however it is used, is written to the append-only audit
  chain (`app/services/audit_service.py`), so a later review can reconstruct
  exactly what the model returned and when.

---

## 12. Disclosures

This model is trained entirely on synthetic data and is not validated against
real KONE service, inspection, sensor or removal records. It is a prototype
built by Team CodeFather (SRM Institute of Science and Technology, Ramapuram)
and is not affiliated with, endorsed by, or connected to KONE Corporation.
Nothing in this document or the system it describes constitutes an approval,
certification or authorisation to operate an elevator.
