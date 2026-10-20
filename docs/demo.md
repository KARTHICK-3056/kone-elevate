# Evaluator demo guide

A 6-8 minute walkthrough of KONE ELEVATE. Every screen below has been verified
against the seeded demo database.

---

## 0. Setup (do this before the demo)

```bash
cd backend
python scripts/generate_data.py     # 10,000 synthetic records
python scripts/train_model.py       # trains and saves the Random Forest
python scripts/seed_database.py --reset   # 60 components + full history
python scripts/seed_users.py        # the five sign-in accounts

python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm run dev
```

| Service | URL |
|---|---|
| Frontend | <http://localhost:5173> |
| Backend | <http://localhost:8000> |
| Swagger | <http://localhost:8000/docs> |

### Signing in

The app now requires a sign-in. The five demo accounts are listed on the
sign-in screen itself - click one to fill the form. Password for all five:
`elevate-demo-2026`.

| Account | Role | Use it to show |
|---|---|---|
| `supervisor@kone-elevate.demo` | Supervisor | The main walkthrough - broadest access |
| `auditor@kone-elevate.demo` | Read-only auditor | **The access-control moment** (step 9a) |
| `sustainability@kone-elevate.demo` | Sustainability controller | Compliance reporting and chain anchoring |
| `technician@kone-elevate.demo` | Technician | Field-level access |
| `planner@kone-elevate.demo` | Recovery planner | Component-recovery capacity and forecasts |

Sign in as **supervisor** for the main walkthrough.

Confirm the top bar reads **"API + model online"** in green, and that it shows
your name and role at the top right, before you start.

### The five demo components

| Scenario | Component ID | Expected outcome |
|---|---|---|
| 1. Healthy motor | `KE-MOT-000001` | Continue Using – No Changes Required, ~98% confidence, health 96.8 |
| 2. Moderately degraded motor | `KE-MOT-000002` | Component Recovery, ~90% confidence, health 70.8 |
| 3. Heavily degraded sheave | `KE-SHE-000001` | Material Recovery, ~92% confidence, health 52.0 |
| 4. **Safety-critical steel rope** | `KE-STE-000001` | Continue Using – No Changes Required **+ MANDATORY HUMAN INSPECTION** |
| 5. **Safety-critical brake, worn lining** | `KE-BRA-000001` | Component Recovery, ~86% confidence, health 80.8 **+ MANDATORY HUMAN INSPECTION** |

Dispose is reserved for material with no recovery route (composites), so none
of the five scenarios reaches it. Open `/passport/KE-BRA-000001` to show
that the brake carries the same deep dive as the motor, rope and sheave: material profile,
usage-adjusted life projection and pre-emptive issue forecast.

Scenario 4 is the important one. Do not skip it.

---

## The walkthrough

### Step 1 - Dashboard (60 seconds)

Open <http://localhost:5173>.

Point at, in order:

- **60 components**, all assessed, average health **59.9/100**
- The recommendation split: **11 Continue Using – No Changes Required, 10 Component
  Recovery, 34 Material Recovery, 3 Dispose** (2 deferred to inspection)
- **Potential recovery value Rs. 15.0L** and **7.26 t CO2e avoided** - and read
  the "Prototype estimate" caption out loud
- **8 awaiting inspection**, **259 audit records**

> "Today a technician facing an unlabelled sheave has no evidence either way, so
> it goes to scrap. This dashboard is what that decision looks like when every
> component carries its own history."

Scroll to show the charts: disposition donut, health histogram, fleet
composition, lifecycle, recovery value, environmental impact, monthly activity,
confidence distribution.

### Step 2 - Components (30 seconds)

Sidebar → **Components**.

Show search, the filter panel (type, material, status, recommendation,
location) and the sortable columns. Point at the red **Safety** chips on steel
ropes, brakes and governors.

Search `KE-MOT-000002` and open it.

### Step 3 - Component Passport (45 seconds)

From the component page click **Passport**, or go straight to
<http://localhost:5173/passport/KE-MOT-000002>.

Show:

- The QR code - it encodes `http://localhost:5173/passport/KE-MOT-000002`
- Identity, origin and installation date
- The complete operating and condition dataset
- The service history timeline - installation, maintenance, inspections, repairs
- The audit trail with linked hashes

> "This is the passport. Scan the label on the physical component and this page
> opens on a phone, in the machine room, with no login."

If you have a phone handy: scan the QR code on screen. The page is designed
mobile-first for exactly this.

### Step 4 - Run AI Assessment (20 seconds)

Click **Run AI Assessment**.

### Step 5 - Read the result (60 seconds)

The AI Circular Intelligence panel appears:

```
Health Score:    70.8 / 100   GOOD
Recommendation:  Component Recovery
Confidence:      93%
Class probabilities: Component Recovery 93% | Material Recovery 6% | Continue Using 2% | Dispose 0%

How the category was decided:
  x Suitable for its current application?        No
  v Usable individual sub-components recoverable? Yes
```

### Step 6 - Explain why (45 seconds)

Read the **Key factors** list. Each entry names the factor, its severity band,
a plain-language sentence with the actual reading, and how much the model
relies on that feature overall - for example:

> "Vibration of 4.60 mm/s is elevated but not severe (limit 7.0 mm/s)."
> Model importance 9.1%

Expand **"How the health score was calculated"** to show the weighted penalty
breakdown.

> "The system never just says Component Recovery. It shows each gate of the
> decision flow, which measurements drove it,
> how far each one is from the design envelope, and how much the model actually
> weighs it."

Point at the footer: "SHAP values are not used." Then:

> "We are explicit about what our explainability is and is not. It is Random
> Forest importance plus envelope deviation. We are not claiming SHAP."

### Step 7 - The safety gate (60 seconds) - **the key moment**

Go to <http://localhost:5173/passport/KE-STE-000001> (steel rope).

The page opens with a red banner **before** anything else:

```
MANDATORY HUMAN INSPECTION
Steel Rope is a safety-critical component. Any AI recommendation is
advisory; a qualified engineer must inspect it before the recommendation is acted on.
```

Click **Run AI Assessment**. The result is:

```
Recommendation:  Continue Using – No Changes Required
Confidence:      98.4%
Health score:    97.3 / 100

MANDATORY HUMAN INSPECTION
AI recommendation: Continue Using – No Changes Required. Human inspection is
required before this recommendation is acted on.
This component type is safety-critical. The AI output is advisory only and is
never an approval, certification or authorisation to operate an elevator.
```

> "This rope is two years old, low hours, excellent condition. The model is
> 98% confident it can continue in its current lift - and the system still refuses to let that
> stand on its own. The safety gate sits outside the model, so it cannot be
> trained away, and high confidence cannot override it. An AI system must never
> autonomously authorise a safety-critical elevator component."

Try `Brake` or `Governor` on the AI Prediction page to show it is the type that
triggers the gate, not the condition.

### Step 8 - Simulation (60 seconds)

Sidebar → **Simulation**.

- Scroll to **The 13 model parameters - KONE API first**. Each row carries a
  source chip: **KONE API** for everything the KONE API publishes (operating
  hours from trip duration; service count, repairs, failures, days since
  service and the condition score from the reference lift's KONE service
  orders), and **Simulated** only for vibration, temperature and part age -
  which no KONE API carries.
- Open **Calibration reference** and point at **KONE record at month 0** - the
  four service orders the run starts from.

> "KONE data comes first. We only simulate what KONE does not publish, and
> where the KONE record is too thin to give a rate - one preventive visit,
> six months of orders - the page says so instead of inventing one."

Press **Run** and raise the load: the early-warning forecast and the AI react
month by month.

### Step 9a - Access control (45 seconds) - **the second key moment**

Sign out (top right), then sign back in as `auditor@kone-elevate.demo`.

Open any component and click **Run AI assessment**. It is refused:

```
Read-only auditors cannot make changes. This account has view access to
every record, including the audit chain.
```

> "This account can see every record in the system, including the audit chain
> itself, and cannot alter a single one of them. That separation is what makes
> the audit trail worth anything to an assurance provider - the person checking
> the books is structurally unable to write in them."

Then make the point that matters most:

> "Before this, the name recorded against every entry in the tamper-proof
> history was whatever string the caller typed into a header. The chain proved
> that an *unverified claim* had not been edited afterwards - which is not
> evidence of anything. Now it is the verified subject of a signed token, and
> the header is gone entirely."

Sign back in as **supervisor** before continuing.

### Step 9 - Audit Log (45 seconds)

Sidebar → **Audit Log**.

Show the chain: **259 records**, 4 entity types, 7 distinct actions. Expand one
entry to reveal the immutable JSON snapshot and both hashes, and point at the
`prev abc123... → def456...` link line.

> "Every action - registering a component, running an assessment, changing a
> status - appends a record that hashes its own content together with the hash
> of the record before it."

### Step 10 - Verify integrity (30 seconds)

Click **Verify audit integrity**.

```
AUDIT CHAIN VALID
227 records checked. Every SHA-256 hash was recomputed from its stored
content and matched.
Head hash 21ca6039b4c3bcf1...7717750cd373
```

> "Editing any historical record breaks every hash after it, and verification
> names the first broken record. That is what makes the sustainability numbers
> auditable rather than merely asserted. It is tamper evidence, not a
> blockchain - we are not claiming distributed consensus."

We test exactly that: `tests/test_audit.py` writes records, verifies, tampers
with an old snapshot, and asserts verification now returns `valid: false` with
the right record id.

---

## Optional extras if time allows

**AI Prediction page** (`/prediction`) - five one-click presets covering all
four dispositions plus the safety-critical rope. Good for a live "what if I
change the vibration reading" moment.

**Analytics page** (`/analytics`) - fleet-level filters, the model feature
importance chart (inspection score 26.6%, operating hours 16.0%, load cycles
11.7%), the impact assumptions table, and the safety-critical inspection queue.

**Swagger** (<http://localhost:8000/docs>) - shows the whole API is documented
with schemas and examples. `POST /api/v1/sensors/{id}` returning **501** is
worth showing: the IoT hook is documented but deliberately not pretending to
work.

**Terminal** - run `python scripts/train_model.py` live. It prints the
confusion matrix and feature importances in about 30 seconds.

---

## Questions to expect, and honest answers

**"What accuracy do you get?"**
86.7% on a held-out split, macro F1 84.5%, 5-fold CV 85.9% (+/- 0.71). All on
synthetic data. Most errors are between neighbouring categories; the cohort
(installation-year) split drops accuracy to 76.9%, and we publish both.

**"Why not higher?"**
Because higher would mean we leaked the target. The model sees noisy
observations of a latent wear variable it never sees directly, plus 5.5%
adjacent-class label noise modelling real inspector disagreement. A prototype
reporting 99% would be evidence of a bug.

**"Is this trained on KONE data?"**
No. No real KONE data was available. It is trained on a synthetic degradation
simulator that is committed in full and reproducible from seed 42. Production
would need historical service, removal, inspection and - hardest of all -
recovery *outcome* records to build validated labels.

**"Could the AI approve a component for service?"**
No, and structurally it cannot. The safety gate for ropes, brakes and governors
sits outside the model as a hard rule. Every recommendation everywhere in the
UI and API carries the advisory disclaimer.

**"Is the CO2 number real?"**
No. It is a prototype estimate from configurable constants in
`backend/app/core/config.py`, labelled as such on every screen that shows it.
The framework is the deliverable; an engineering team swaps in validated
factors without touching application code.

**"Is there real authentication?"**
Yes, with five enforced roles - but it authenticates against the platform's
own account table, not company single sign-on. A real KONE deployment would
use Entra ID; that needs a tenant this build has no access to. The sign-in
screen says so itself. What is real: every change is attributed to a verified
account, the spoofable `X-Actor` header is deleted, and a read-only auditor is
structurally unable to write anything.

**"What is missing for production?"**
Single sign-on, multi-tenancy, validated engineering constants, real training
labels, time-based validation with drift monitoring, observability, and
regulatory review. `plan.md` P4-P6 lists these without softening them.
