# Governance pack

The P6 deliverable this covers: *"Model card, Annex IV-shaped technical
file, human-oversight standard operating procedure, incident reporting
route, DPIA. Assemble it whether or not you conclude the system is
high-risk - the conclusion is more credible when the file exists."*

> **Status.** Every section below is a real, drafted document or a pointer
> to one that already exists (the model card). None has been reviewed by a
> function external to this build - the same honest limit
> `docs/ai-act-classification.md` states for the classification argument
> itself.

---

## 1. Model card

Already exists: [`docs/model-card.md`](model-card.md), drafted in P1 in
Annex IV technical-documentation shape (intended use, out-of-scope use,
training data provenance, metrics by class and by cohort, known failure
modes, human-oversight requirement). Not duplicated here.

## 2. Annex IV-shaped technical file - what exists and where

Annex IV of the EU AI Act sets out the technical documentation a high-risk
AI system's provider must maintain. This system's own classification
argument concludes it is *not* high-risk (`docs/ai-act-classification.md`),
but the documentation is assembled regardless, per this deliverable's own
instruction - the conclusion is more credible when the file exists than
when it is asserted with nothing behind it.

| Annex IV section (paraphrased) | Where it lives in this repository |
|---|---|
| General description of the system, intended purpose | `README.md`, `docs/architecture.md` |
| Description of elements and development process | `docs/architecture.md`, `docs/machine-learning.md` |
| Detailed information on monitoring, functioning and control | `docs/model-card.md`, `docs/database-scale.md` (observability), `app/core/metrics.py` |
| Risk management measures | `docs/threat-model.md`, this document §3-4 |
| Description of changes made through the system's lifecycle | `plan.md`'s phase-by-phase deliverables, git history |
| Standards applied | `docs/compliance.md` §"Ground the passport in the standards" (ISO 4344, ISO 281, EN 81-80 - flagged `CLAUSE_UNVERIFIED`, see that document) |
| Validation and testing procedures, including metrics | `docs/model-card.md`, `models/metrics.json`, `backend/tests/` |
| Human oversight measures | §3 below |
| Performance metrics and known limitations | `docs/model-card.md`, `plan.md` §4 ("Four gaps that matter") |

**What is genuinely missing:** a single assembled document matching
Annex IV's actual structure line-by-line. What exists is complete in
substance, scattered across the documents named above by design (each
document's primary audience is different - a database reviewer does not
need the model card's calibration discussion inline). Assembling a single
cross-referenced Annex IV file, rather than a table of pointers, is real
follow-on work.

## 3. Human-oversight standard operating procedure

**Who is required to act, and when:**

1. **Every safety-critical recommendation** (steel rope, brake, governor -
   `app/utils/enums.py::SAFETY_CRITICAL_TYPES`) carries `safety_flag: true`
   and the `MANDATORY HUMAN INSPECTION` message on every response,
   regardless of what the AI recommended. **No disposition decision on
   these types may be actioned without a qualified person physically
   inspecting the component first.** This is enforced in code
   (`app/ml/predict.py::_apply_safety_gate`), not policy alone.
2. **Every `DEFER_TO_INSPECTION` outcome** (the abstention path, P1) routes
   to the same mandatory human review, regardless of component type - the
   model has explicitly declined to have an opinion, and no one should act
   as though it had one.
3. **A supervisor or recovery planner reviews the safety-critical
   inspection queue** (`GET /api/v1/dashboard/safety-queue`) as a matter of
   routine, not only when prompted - it exists specifically so this
   oversight step has a place to happen.
4. **A technician's trust rating** (`POST /predictions/{id}/feedback`, P6)
   is a lightweight signal for exactly this oversight function: a pattern
   of low trust ratings on a component type is a prompt to review that
   type's model performance (`docs/model-card.md`'s per-class metrics), not
   just an ignored survey field.

**What this SOP does not yet have:** a named role (not just "a supervisor")
accountable for periodic oversight review, and a documented cadence (weekly?
per-pilot-cohort?) for reviewing the safety queue and trust-rating trends
as a standing practice rather than an ad hoc one. That naming needs a real
organisation to assign the role to, which this build does not have.

## 4. Incident reporting route

**What counts as an incident:**

- A safety-critical component was kept in service, or had parts recovered
  for use, and subsequently failed - a `FAILED_INSPECTION` outcome (recorded
  or harvested from KONE service orders) for the `CONTINUE_USING` or
  `COMPONENT_RECOVERY` categories.
- The audit chain fails verification (`scripts/verify_chain.py` /
  `GET /api/v1/audit/verify` returning `valid: false`) - see
  `docs/disaster-recovery.md` and `app/core/alerting.py` for the existing
  webhook mechanism this would page through.
- A material feature-drift alert fires (`scripts/check_drift.py`) against
  live (not synthetic) traffic, once there is any.

**Where it is reported:**

- `agreement_service.score_weak_labels`'s `optimistic_misses` count (against
  outcomes harvested from KONE service orders) is the standing record of the
  first category - reviewed as part of `docs/pilot-protocol.md` §5's weekly
  cadence during any pilot. The workshop-outcome agreement report was removed
  with the Recovery Exchange.
- The two alert webhooks (`DRIFT_ALERT_WEBHOOK_URL`,
  `CHAIN_VERIFY_ALERT_WEBHOOK_URL`, both in `app/core/config.py`) are the
  mechanism for the second and third categories - unconfigured by default,
  same as the chain-anchor webhook, so a real deployment must point them at
  a real paging system before this is anything more than a printed warning.

**What this route does not yet have:** a named external reporting
obligation analysis (whether an incident of the first kind would trigger a
regulatory report under the Lifts Directive, the AI Act's incident-reporting
provisions, or elsewhere) - that determination depends on the
classification conclusion in `docs/ai-act-classification.md` holding, and
on jurisdiction-specific advice this build cannot provide.

## 5. DPIA (Data Protection Impact Assessment) - a starting structure, not a completed assessment

A full DPIA needs a real data controller, a real legal basis determination,
and (for India specifically) an assessment against the DPDP Act, none of
which exist for a synthetic demo fleet. What is real: the personal-data
inventory and the specific unresolved tension a DPIA would have to grapple
with are already documented in `docs/threat-model.md` §4 - technician names
and audit-chain actor emails inside an append-only, hash-chained log with
**no erasure path**, because the chain's entire value proposition (tamper
evidence) and a right-to-erasure pull in opposite directions by
construction.

A real DPIA, once real personal data is in scope, must at minimum:

1. Confirm the lawful basis (legitimate interest for maintenance records is
   the likely fit, per `docs/threat-model.md` §4) and document it formally,
   not just note it as "likely."
2. Resolve the erasure tension - most plausibly by pseudonymising
   `technician`/`actor` at write time against a separately-erasable
   identity system, per that same document's recommendation - *before* any
   real person's data enters this system, not after.
3. Assess the DPDP Act specifically, given the seeded demo fleet's own
   country (India) and BRSR's applicability to KONE's Indian operations
   (`plan.md` §6).

This section is deliberately not padded out further: a DPIA performed
against a hypothetical data controller who does not exist yet would be
theatre, not governance.
