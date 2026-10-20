# Pre-registered pilot protocol

The P6 deliverable this covers: *"Pre-register the pilot. Two sites, one
quarter, metrics fixed before the start... Pre-registration is what stops
the pilot from becoming a demo."*

> **Status.** This is the protocol document itself - the pre-registration.
> No pilot has started; there are no sites, no dates, and no real data
> behind any of it yet. What is real: every metric named below is backed by
> a working `GET /api/v1/pilot/metrics` endpoint (see
> `app/services/pilot_service.py`), computed from live data rather than
> promised as a future report.

---

## 1. Why pre-registration, specifically

A pilot whose success metrics are chosen *after* seeing the results is not
a pilot, it is a demo with better production values. Pre-registration -
naming every metric and every threshold before a single real component goes
through the system - is what makes a "the pilot succeeded" claim
falsifiable rather than retrofitted.

## 2. Scope

- **Sites:** two, to be named once a pilot partner exists. Not this build's
  synthetic demo fleet - real removals from a real component-recovery workshop.
- **Duration:** one quarter (13 weeks) from the first real outcome
  recorded, not from installation of the software.
- **Population:** every component removed at the two sites during the
  pilot window that is assessed through this platform - no cherry-picking
  which removals go through the pilot and which do not.

## 3. The six metrics, fixed in advance

Three are computed today by `GET /api/v1/pilot/metrics`
(`app/services/pilot_service.py`) - diversion rate, technician trust score
and mass diverted - the same code path a reviewer can exercise against the
demo fleet. The recovered-parts yield, decision-reversal rate and value
recovered were computed from workshop outcomes and accepted matches recorded
on the Recovery Exchange; the exchange was removed, so they are **not
computed** and a pilot would need a new outcome-recording source for them.

| Metric | Definition | Success threshold (to be confirmed with the pilot partner before start) |
|---|---|---|
| Diversion rate | Share of assessed components whose recommendation routes them away from disposal (Continue Using / Component Recovery / Material Recovery vs. Dispose) | ≥ current workshop baseline, measured over the same population before this platform's involvement |
| Recovered-parts yield *(not computed - needs recorded outcomes)* | Of lots recorded as parts recovered and used (`PARTS_RECOVERED`), the share that survived in service | ≥ 90% (illustrative - the real number should come from the workshop's own historical yield, which this build does not have) |
| Decision-reversal rate *(not computed - needs recorded outcomes)* | Share of recorded outcomes that disagreed with the AI's recommendation at the time of the decision | Published, not gated on a threshold - the point of shadow mode and this metric is to *learn* the real rate, not assume one in advance |
| Technician trust score | Average 1-5 one-tap rating (`Prediction.technician_trust_rating`) | ≥ 3.5 average, with a published distribution, not just the mean |
| Value recovered *(not computed - the Recovery Exchange was removed)* | INR value of recovered parts actually used | Reported alongside the workshop's existing scrap and parts revenue for direct comparison |
| Mass diverted | kg diverted from disposal, from the material-flow ledger (`docs/compliance.md`) | Reported in tonnes for the pilot period, comparable to the ESRS E5-5 shape this platform already produces |

**On thresholds:** every "illustrative" threshold above is a placeholder
for review with an actual pilot partner and their own baseline data, which
this build does not have. The metrics themselves - what gets measured and
how - are fixed; the pass/fail bar on each is not invented here.

## 4. What "shadow mode first" means operationally

Per `docs/shadow-mode.md`, the pilot's first phase runs assessments in
shadow mode - computed, stored, never surfaced to a technician - against
real removals, purely to accumulate agreement data against recorded
outcomes *before* the AI's recommendation is allowed to influence a real
decision.
Only after a pre-agreed shadow-mode agreement rate is reached does the
pilot move to live mode, where the recommendation is actually shown.

## 5. Governance during the pilot

- Every prediction and status change during the pilot is
  already in the tamper-evident audit chain (`docs/architecture.md`) - no
  additional logging infrastructure is needed for the pilot itself.
- `GET /api/v1/pilot/metrics` is run
  weekly during the pilot and the results are reviewed with the named
  stakeholders (`docs/stakeholders.md`), not just at the end.
- Any optimistic miss (`docs/shadow-mode.md` §1) - a safety-adjacent
  component recommended to continue in use or for component recovery that failed inspection or
  was disposed - is reviewed individually, not just counted, per the same
  reasoning the original build audit gave for weighting error types
  differently (`plan.md` §4.1).

## 6. What happens after

The pilot's real-label outcomes are the input to `scripts/promotion_gate.py`
via a retraining pass not yet built (see `docs/shadow-mode.md` §3 for
exactly what is and is not automated). A pilot that produces enough
real-label data to make retraining meaningful, and a governance pack
reviewed against real pilot experience rather than a synthetic fleet, are
the two concrete outputs this protocol is written to produce.
