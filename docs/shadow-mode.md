# Shadow mode and the agreement/disagreement mechanism

The P6 deliverables this covers: *"Run against historical removals with
outputs hidden from technicians. Measure agreement with what the
recovery workshop actually did. Publish the disagreement analysis, by
component type"* and *"Add a one-tap outcome capture ... so a real training
set starts accumulating from day one of the pilot."*

> **Status.** Shadow mode, the technician trust rating, the KONE weak-label
> agreement score and the promotion gate are implemented and tested. The
> one-tap workshop-outcome capture and the agreement report built on it
> (`scripts/agreement_report.py`) lived on Recovery Exchange listings and
> were **removed together with the Recovery Exchange** (migration
> `0019_remove_recovery_exchange`). **No real removal or real workshop
> outcome exists in this build.**

---

## 1. What remains

### Shadow mode

`Prediction.shadow` (migration `0012_p6_outcome_and_shadow`) plus
`prediction_service.assess_component_shadow()` and
`POST /components/{id}/predict/shadow`
(`app/api/predictions.py::predict_shadow`). A shadow assessment is computed
and persisted exactly like a normal one, **except it never updates**
`Component.health_score` / `latest_recommendation` / `latest_confidence` -
the cached columns every technician-facing view (the passport, the
component list, the dashboard) actually reads (see
`docs/database-scale.md` for why those columns exist). `Component.latest_prediction`
(the property backing those same views) also explicitly skips shadow rows
even when one is the chronologically newest prediction: without that second
check, a shadow assessment would stay out of the *cached* columns but still
leak into any view built from the relationship instead. A shadow prediction
is still visible in the component's *full* prediction history and in CSV
exports (tagged `shadow: true`) for anyone deliberately looking, and is
excluded from `GET /predictions/recent`, the fleet-wide live feed.

### Technician trust rating

`Prediction.technician_trust_rating`, a 1-5 one-tap rating on any
assessment (`POST /predictions/{id}/feedback`), averaged by
`GET /api/v1/pilot/metrics`.

### Agreement against weak labels

`app/services/agreement_service.py::score_weak_labels` scores the AI's
recommendation against outcomes *harvested* from KONE service orders
(`app/integrations/kone_labels.py`), using one fixed compatibility table:
`CONTINUE_USING` → `CONTINUED_IN_SERVICE`; `COMPONENT_RECOVERY` →
`PARTS_RECOVERED`; `MATERIAL_RECOVERY` → `MATERIAL_RECOVERED`; `DISPOSE` →
`DISPOSED`. It reports a weighted and an unweighted agreement rate, and
**optimistic misses** separately - the AI said `CONTINUE_USING` or
`COMPONENT_RECOVERY` but the outcome was `FAILED_INSPECTION`, `DISPOSED` or
`MATERIAL_RECOVERED`. `DEFER_TO_INSPECTION` is excluded: an abstention is
the model declining to have an opinion, not a wrong answer. Harvested labels
are censored wherever KONE records no disposition - see
[`kone-integration.md`](kone-integration.md).

## 2. The promotion gate

`scripts/promotion_gate.py` compares a candidate model's `metrics.json`
against the currently deployed one and blocks promotion if the
cohort/temporal-split F1, the random-split F1, the abstention rate, or
mean per-class Brier score regress beyond a fixed threshold. It was tested
against a deliberately regressed candidate (worse F1, higher abstention)
and correctly blocked it; run against the same metrics file twice, it
correctly approves.

**What it is not:** there is no automated retraining pipeline feeding it
real-label outcomes. With the workshop-outcome capture removed, a real pilot
needs a new source of recorded outcomes before retraining on real labels is
possible.

## 3. What this does and does not prove

**Proves:** the shadow-mode prediction path, the trust rating, the weak-label
agreement calculation and the promotion gate work correctly against real
database rows and API calls.

**Does not prove:** anything about how well this model agrees with a real
KONE recovery workshop, because no real workshop has ever used it, and this
build no longer records workshop outcomes.

## 4. Reproducing this

```bash
cd backend
python -m pytest -q tests/test_pilot_mechanisms.py tests/test_kone_integration.py
python scripts/promotion_gate.py --candidate models/metrics.json   # compares a file to itself: PASS
```
