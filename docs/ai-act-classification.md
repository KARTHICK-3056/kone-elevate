# EU AI Act classification argument

The P6 deliverable this covers: *"AI Act classification argument written
down and reviewed."* This expands the pointer already in `plan.md` §6 and
`docs/threat-model.md` §5 into its own document, because a classification
argument a quality/safety stakeholder is going to ask about deserves to be
findable on its own, not buried inside a broader audit.

> **Status.** This is the argument, written down, as the deliverable asks.
> **"Reviewed" means reviewed in this document's own drafting** - it has
> not been reviewed by a qualified regulatory or legal function external to
> this build, which is what "reviewed" should mean before anyone relies on
> it. That review is the concrete next step, not a formality.

---

## 1. The relevant law

The EU AI Act (Regulation (EU) 2024/1689) classifies an AI system as
**high-risk** under Annex I when it is:

1. a *safety component* of a product, or is itself a product, covered by
   Union harmonisation legislation listed in Annex I, **and**
2. that product is required to undergo third-party conformity assessment
   under that legislation.

The Lifts Directive (2014/33/EU) is listed in Annex I. Obligations for
Annex I high-risk systems apply from **2 August 2028** (deferred by
Regulation (EU) 2026/1744, per `plan.md`'s own sourcing).

## 2. What this product actually does

The Component Passport's AI system:

- takes as input the recorded condition of a component that has **already
  been removed** from an elevator (or is being assessed for removal),
- outputs an advisory end-of-use recommendation (Continue Using – No Changes
  Required / Component Recovery / Material Recovery / Dispose, or
  DEFER_TO_INSPECTION),
- **never controls, operates, or is installed as a component of an
  elevator in service.**

It is decision support for a circular-economy/component-recovery workflow, not
a safety component of a lift. The lift itself, and any safety component
actually fitted to an operating lift, is unaffected by what this system
recommends until a human acts on that recommendation.

## 3. The argument for "not high-risk", and its load-bearing assumption

**Argument:** This system is not a safety component of a product covered by
Annex I legislation, because it does not participate in the operation of a
lift at all - it advises on what to do with a part after it has left
service. The Lifts Directive's conformity-assessment requirements attach to
lift installations and their safety components *while in service*; this
system acts entirely downstream of that boundary.

**The argument rests entirely on one thing holding absolutely: the safety
gate.** `app/ml/predict.py::_apply_safety_gate` guarantees that for the
three safety-critical component types this platform tracks (steel ropes,
brakes, governors), the AI's output can never authorise return to service
without a mandatory human inspection - every response for those types
carries `safety_flag: true` and the verbatim `MANDATORY HUMAN INSPECTION`
message, enforced in code (not just policy) and exercised by tests
including one that asserts the banner appears *even when the AI recommends
Continue Using*.

**The moment that gate is ever weakened or bypassed** - an integration that
lets a recommendation return a rope, brake or governor to service without
that mandatory inspection and a real conformity assessment - **the
classification argument above no longer holds**, and this system would need
to be re-evaluated as a safety component of a product requiring
third-party conformity assessment, squarely inside Annex I. This is not a
UX feature that happens to also help the classification argument; it is
the regulatory boundary of the product, and any future change to it must
be evaluated against this document before being shipped.

## 4. What would change the analysis

- **Direct integration with a lift-control system** (as opposed to a
  removed-component recovery workflow) would put this analysis back on the
  table entirely - not attempted, and not planned, per `plan.md` §9 ("what
  not to build").
- **Any UI or workflow change that lets a recommendation for a
  safety-critical type be actioned without the mandatory-inspection step
  being a real, enforced gate** - not just displayed - would do the same.
- **A live IoT integration** (the currently-501 `/sensors/{id}` endpoint,
  see `plan.md`'s pitch-to-code ledger) feeding real-time telemetry into a
  recommendation that then flows back toward an in-service decision would
  need this argument revisited, even though the current architecture keeps
  it firmly on the "already removed" side of the boundary.

## 5. What is genuinely still open

- **No qualified external review.** This argument was drafted as part of
  this build, not reviewed by legal/regulatory counsel or a notified body.
  That review, with someone whose job is to be wrong about this
  professionally rather than as a side effect of building a hackathon
  prototype, is the actual next step before any organisation relies on this
  conclusion.
- **No documentation of this argument in Annex IV technical-documentation
  shape has been cross-checked against the Annex IV template line by
  line** - `docs/model-card.md` and `docs/governance-pack.md` are shaped
  like it, but a genuine Annex IV filing (were this ever classified
  high-risk after all, or voluntarily prepared regardless) would need a
  dedicated pass against the actual Annex IV text, not an approximation.
