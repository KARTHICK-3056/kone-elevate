# KONE integration: the assumption register

**Written 21 September 2026. Supersedes "ask the mentor" as the way these
questions get resolved.**

The KONE integration (K-1, K-2, K-3) is built entirely against KONE's
published Apache-2.0 reference implementation. No account, no credentials,
no live call, and no contact who can confirm anything. Proceeding anyway
means making assumptions — so the alternative to a mentor answering them is
not to avoid them, it is to **write every one down, rate what breaks if it
is wrong, and say how it would be detected.**

That is this document. It is the deliverable that replaces K-4.

Nothing here licenses relabelling estimates as measurements. Every figure
this integration produces still carries its provenance tag, and
`/integrations/status` still reports `live_call_ever_made: false`.

---

## How to read the risk column

| Risk | Meaning |
|---|---|
| 🔴 **Silent** | If wrong, the system keeps working and produces wrong numbers with no error. The dangerous class. |
| 🟠 **Loud** | If wrong, something fails visibly on first contact — a 401, a 404, a parse error. Cheap to find. |
| 🟡 **Bounded** | If wrong, one figure is off but the error is contained and obvious in context. |

---

## 1. Transport and auth (K-1)

| # | Assumption | Basis | Risk | How it gets caught |
|---|---|---|---|---|
| 1.1 | OAuth2 client-credentials, HTTP Basic, form-encoded `grant_type`/`scope` | Reference impl `koneapi.ts` | 🟠 Loud | 401 on first token request |
| 1.2 | Scopes are `serviceinfo/{ken}` and `rtm/{ken}` | Reference impl demos | 🟠 Loud | 403 on first call |
| 1.3 | Paths `/api/v2/equipment/{ken}/serviceOrders[/{id}]`, `/api/v2/equipment/search/{endpoint}` | Reference impl | 🟠 Loud | 404 on first call |
| 1.4 | `/serviceOrders` returns a **bare JSON array**, not a paginated envelope | Reference impl types it `ListServiceOrder[]` | 🟠 Loud | Parse error, or a silently truncated history |
| 1.5 | HTTP 404 means "not found", not "no access" | Ordinary REST convention | 🟡 Bounded | An accessible equipment would read as missing |
| 1.6 | Token response carries `expires_in` | Standard OAuth2 | 🟡 Bounded | Falls back to a 5-minute TTL; worst case is extra token calls |

**Assessment:** this whole block is cheap. Every one of these fails loudly
on the first real call, so a single successful request retires most of the
register. That is the strongest argument for getting *any* account, even a
sandbox with one virtual lift.

---

## 2. Feature derivation (K-2)

| # | Assumption | Basis | Risk | How it gets caught |
|---|---|---|---|---|
| 2.1 | **Condition codes are ordinal with `1` = best** | Nothing. Pure inference from the `Desc` values in the examples | 🔴 **Silent** | `kone_features.validate_condition_code_direction()` — see below |
| 2.2 | `APPORTIONMENT` duty factors per component type | Prototype engineering judgement | 🔴 Silent | Nothing automatic. Needs a workshop engineer |
| 2.3 | `failedComponentCode` token spellings (`DOOR_OPERATOR`, `TRACTION_SHEAVE`, …) | Examples plus ordinary vocabulary | 🟡 Bounded | Unmapped codes return `None` rather than mis-mapping |
| 2.4 | `loadPercentage` is % of **rated** load | Field name | 🟡 Bounded | Recorded in provenance as a percentage, never converted to kg |
| 2.5 | One movement document = one journey | Reference impl says "last saved events" | 🟡 Bounded | Duty figures come out implausibly small, which is visible |

### 2.1 is the one that matters

If KONE's condition codes run the other way — `1` = worst — then **every
`inspection_score` this layer produces is inverted**, with no error, no
crash, and no way to notice by reading the output. A degraded lift would
score 90 and a healthy one 20, and the model would be fed a confident,
precisely wrong condition signal.

It is also detectable, which is why
`kone_features.validate_condition_code_direction(orders)` exists. Orders
carrying a recorded failure should skew toward the worse end of the scale.
If they skew the other way on real data, it returns `SUSPECT_INVERTED` and
says not to use derived features until it is resolved. It returns
`insufficient_data` below three of each rather than concluding from noise.

**Run it first, on the first real equipment history available, before
anything downstream consumes an inspection score.**

### 2.2 has no automatic check, and should not pretend to

The apportionment factors — a door operator actuating twice per journey and
loaded ~15% of running time, a motor running throughout — are the layer's
load-bearing assumption and there is no data-driven way to validate them
from the API alone. They are stated per type with reasoning so an engineer
can disagree with a specific number rather than the whole table. That is
the honest ceiling here.

---

## 3. Label harvesting (K-3)

| # | Assumption | Basis | Risk | How it gets caught |
|---|---|---|---|---|
| 3.1 | `technicianActionCode` enumeration (`INSPECTED`, `ADJUSTED`, `REPLACED`, …) | Examples plus service vocabulary | 🟡 Bounded | Unrecognised codes produce *no label* rather than a wrong one |
| 3.2 | `REPLACED` means the component left the equipment | Plain reading | 🟡 Bounded | — |
| 3.3 | A replacement following a recorded failure implies the removed part had failed | Inference | 🟠 Loud-ish | Down-weighted to 0.4 and labelled `inferred`, never `observed` |
| 3.4 | The 0.4 weight for inferred labels | Arbitrary | 🟡 Bounded | One tunable constant, not a structural claim |

### The finding that no assumption can fix

`technicianActionCode` records what was done to the **equipment**, not
where a removed **component** went. KONE publishes no disposition field
anywhere. So this source:

- **can** observe "the part was kept in service" directly;
- **cannot** distinguish component recovery from material recovery from disposal.

On the recorded fixtures: 4 orders → 2 observed, 1 inferred, **1 censored**,
and `PARTS_RECOVERED` / `MATERIAL_RECOVERED` / `DISPOSED` are in
`classes_never_observed`.

This is structural, not a tuning problem. A model retrained on these labels
alone would drift **optimistic** — toward putting parts back into service —
which is the exact error direction `app/ml/cost_matrix.py` prices highest.
`label_coverage()` therefore reports `usable_for_training: false` and the
censoring percentage, so volume is never mistaken for coverage.

---

## 4. What this means for the pitch

Two things follow, and both are better said than discovered by a reviewer.

**The APIs fix the features, not the target.** Seven of thirteen model
inputs become real measurements. The label stays synthetic. Every accuracy
figure this platform publishes still describes a simulator, and the KONE
integration does not change that.

**So the ask is not API access.** It is, in priority order:

1. **A historical removal dataset** — component, condition at removal, what
   the workshop actually did. This is the only thing that makes the model's
   accuracy claim real. It needs no API and no integration work.
2. **A workshop recording outcomes for one quarter** through the capture
   endpoint P6 already built. Slower, but it accumulates a real training
   set from day one.
3. **Any API account, even a one-lift sandbox** — which retires §1 of this
   register in a single call and lets §2.1 be checked.

Asking for (3) first is the instinct, and it is the least valuable of the
three.

---

## 5. Review protocol

When someone with KONE access is eventually available, this register is the
agenda — not a re-explanation of the project:

1. Run `validate_condition_code_direction()` on a real equipment history.
   Resolve §2.1 before anything else.
2. Make one live call. Tick or correct §1 wholesale.
3. Get the real `technicianActionCode` and `failedComponentCode` code
   lists. Reconcile §2.3 and §3.1.
4. Put the `APPORTIONMENT` table (§2.2) in front of a maintenance
   engineer and have them mark up the numbers.
5. Ask the disposition question directly: *does any KONE system record
   where a removed component went?* If one does and it is simply not in the
   public API, that single answer is worth more than everything else here.
