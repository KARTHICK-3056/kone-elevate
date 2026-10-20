# Website guide — what every page and panel does

A plain-language tour of the KONE ELEVATE app: what each page is for, what
every section inside it does, and — at the end — a simple script for showing
an evaluator that it actually works. No jargon left unexplained.

If a term needs defining, it's defined the first time it shows up, in
*(italics like this)*.

---

## The big picture in one paragraph

Every elevator part (a motor, a brake, a steel rope...) gets a **digital
passport**: a permanent record of its whole life. An AI model looks at a
part's condition and recommends what to do with it — **Continue Using – No
Changes Required** (it stays in its current lift, unchanged), **Component
Recovery** (recover its usable sub-components for lower-demand uses),
**Material Recovery**, or **Dispose**. A complete part is never resold or
moved to another lift. A **tamper-proof history** records every action
ever taken so nobody can quietly edit the past. The **Simulation** runs a lift
forward in time from its KONE record to show how the parts wear under a
different load. And the **Compliance** page turns all of that into the
actual paperwork regulators ask companies to file.

Ten pages, each covering one piece of that story:

| Page | One-line job |
|---|---|
| Sign in | Prove who you are, so the record can name you |
| Dashboard | The whole fleet's health and value, at a glance |
| Components | The searchable list of every part being tracked |
| QR Passport | One part's complete life story, scannable from a phone |
| AI Prediction | Ask the AI what to do with a part, and see its reasoning |
| Simulation | Run a lift forward in time - KONE API data first, simulation only where KONE has none |
| Analytics | Fleet-wide numbers, plus proof the AI's confidence is honest |
| Forecast | Predicts *when* parts will need attention, months ahead |
| Compliance | The actual sustainability reports a regulator would ask for |
| Audit Log | The tamper-proof history, and a button that proves it's intact |

---

## 0. Sign in

**What it's for:** the app is closed until you sign in. Nothing else loads
first — this is the front door.

**Why it exists:** every action you take gets written permanently into the
tamper-proof history with your name on it. Before this screen existed, that
name was simply whatever the sender claimed it was, with nothing checking —
which made the history prove very little.

**What's on it:**

- **Email and password.** Passwords are stored *hashed* — scrambled into a
  fingerprint that cannot be reversed, and deliberately slow to compute so
  guessing millions of them is impractical.
- **Five demo accounts, listed right on the screen.** Click one to fill the
  form. There's no "create account" button on purpose: a page that lets
  anyone choose their own permission level would be a security hole. Real
  accounts are created by a supervisor, like normal company onboarding.
- **An honest note** stating this checks against the app's own account list,
  not a company Microsoft sign-in — which is what a real deployment would use.

**The five permission levels:**

| Role | Can do |
|---|---|
| Technician | Register components, log service events, run AI assessments |
| Supervisor | Everything a technician can, plus creating accounts |
| Recovery planner | Component-recovery capacity planning and forecasts |
| Sustainability controller | ESRS/BRSR reporting, and anchoring the audit chain |
| **Read-only auditor** | See absolutely everything — change absolutely nothing |

The read-only auditor is the interesting one: it can read every record
*including the audit trail*, and every attempt to change anything is refused
with a plain-English explanation. That separation is what makes the audit
trail worth anything — the person checking the books can't write in them.

**One page deliberately skips all of this:** the QR passport (see §3). A
technician scanning a label in a basement machine room has no account and no
signal, so that page stays open to anyone with the link. That's the feature,
not a gap.

---

## 1. Dashboard — "Portfolio Command Centre"

**What it's for:** the first thing anyone sees. One screen answering "how is
the whole fleet doing, and what's it worth?"

**What's on it:**

- **Total components / Average health score / Potential recovery value /
  Estimated CO₂ avoided** — four headline numbers. Recovery value and CO₂ are
  marked "Prototype estimate" because they're calculated from configurable
  assumptions, not audited financial or engineering data — see the Analytics
  section below for exactly which assumptions.
- **Continue Using – No Changes Required / Component Recovery / Material
  Recovery / Dispose** — four tiles showing
  how many parts fall into each AI-recommended category. Click any tile to
  jump straight to that filtered list on the Components page.
- **Awaiting inspection / Safety-critical components / Audit records** —
  three operational counters, each a shortcut to the page that explains it.
- **Charts** — disposition split (donut), health-score distribution
  (histogram), fleet composition by part type, lifecycle-stage breakdown,
  recovery value by part type, environmental impact by part type, monthly
  activity, and how confident the AI was across its recent assessments.
- **Safety-critical inspection queue** — a table of steel ropes, brakes and
  governors waiting for a human to look at them. These three part types can
  *never* be released on the AI's word alone, no matter how confident it is.
- **Recent AI assessments** — the last few times someone ran the AI on a
  part, with the result and whether it required inspection.

**In plain terms:** it's the fleet manager's morning check-in screen.

---

## 2. Components — the part registry

**What it's for:** find, filter and manage every individual tracked part.

**What's on it:**

- **Search bar** — type a part ID, serial number or manufacturer.
- **Filter panel** — narrow by part type, material, lifecycle status, AI
  recommendation, or location, in any combination.
- **Sortable table** — click any column header (health score, install date,
  operating hours...) to sort by it.
- **Safety chips** — a red badge on any steel rope, brake or governor row, so
  the safety-critical parts are visible without opening each one.
- **Add component** — a form to register a brand-new part into the system.
- **Export CSV** — download the current filtered list as a spreadsheet.

**In plain terms:** it's a searchable spreadsheet of every part, with a
button to add new ones.

---

## 3. QR Passport — one part's life story

**What it's for:** the complete, permanent record for a single part —
designed to open on a phone when someone scans a label in a machine room,
with no login needed.

**What's on it:**

- **QR code** — scan it and this exact page opens. The code encodes a
  permanent web address for this part (not a temporary demo link — see
  "Digital Product Passport" below).
- **Identity and origin** — manufacturer, plant of origin, install date, age.
- **Operating and condition data** — every reading the AI uses: operating
  hours, load cycles, vibration, temperature, inspection score, and more.
- **Latest AI assessment** — the most recent recommendation, confidence and
  health score, with a "Run AI Assessment" button to get a fresh one.
- **Circular impact of this component** — the estimated money recovered and
  CO₂ avoided if this specific part follows its recommended path.
- **Standards basis** — which published engineering standard governs this
  *type* of part (e.g. steel ropes are covered by ISO 4344), and which clause.
  Some clause numbers are flagged **"Clause unverified"** — that's explained
  in the section on honesty below; it means the standard is real but the exact
  clause pointer hasn't been checked against the purchased document yet.
- **Digital Product Passport** — a permanent, government-registry-style
  identifier for this part (`urn:kone:dpp:...`), separate from any particular
  website, plus who's legally responsible for it (the "economic operator" —
  currently unassigned, which the panel says outright rather than hiding it).
- **Service history** — every maintenance visit, inspection and repair, in
  order.
- **Prediction timeline** — every AI assessment ever run on this part.
- **Audit trail** — the tamper-proof history entries for this specific part,
  each one showing its cryptographic fingerprint linked to the one before it.

**In plain terms:** scan the QR code on a physical part, and this page tells
you everything that's ever happened to it and what the AI thinks should
happen next.

---

## 4. AI Prediction — ask the AI, see its reasoning

**What it's for:** run the AI model on a part — either one already in the
system, or hypothetical numbers you type in — and see not just the answer but
*why*.

**What's on it:**

- **Two input modes:**
  - *Existing component* — type or pick a part ID already in the system.
  - *Manual entry* — four one-click demo presets (healthy motor, moderately
    degraded motor, heavily degraded sheave and a safety-critical steel rope) or type your own numbers for all eleven
    inputs the model uses (age, operating hours, load cycles, vibration,
    temperature, service/repair/failure counts, inspection score, days since
    service).
- **Model performance panel** — the model's actual measured accuracy, F1
  score, precision/recall and how many records it trained on, with an honest
  note that these numbers describe simulated data, not real elevators.
- **Result panel**, once you run an assessment:
  - **Recommendation** — Continue Using – No Changes Required, Component
    Recovery, Material Recovery, Dispose, or
    **DEFER_TO_INSPECTION** ("I'm not confident enough to answer" — a genuine
    fifth outcome, not a fallback error).
  - **Confidence** and the probability the model assigned to each of the four
    possible outcomes.
  - **Health score** with the weighted penalty breakdown behind it (which
    factors hurt the score and by how much).
  - **Key factors** — plain-English sentences like *"Vibration of 4.60 mm/s
    is elevated but not severe (limit 7.0 mm/s)"*, each with how much weight
    the model gives that factor overall.
  - **Safety gate**, when the part type is a steel rope, brake or governor —
    a mandatory human-inspection notice that appears no matter what the
    recommendation is or how confident the model was.

**In plain terms:** it's a "what would the AI say about this part, and can
you show your work" screen.

---

## 5. Simulation — KONE API first, simulated only where KONE has no data

**What it's for:** run one lift's motor, steel rope, sheave and brake forward
month by month at an average load you choose, and watch how the life model,
the early-warning forecast and the AI react.

**Where each number comes from.** The table of 13 model parameters shows a
source chip on every row:

- **KONE API** — 8 of the 13, taken from the reference lift's KONE data
  first: operating hours and load cycles from KONE's journeys, the load from
  KONE's reported load, and the service count, repairs, failures,
  days since the last service and the condition score from its KONE service
  orders at the start of the run. A second chip ("then Simulated" /
  "then Assumption") says what carries the value forward after that.
- **Simulated** — only what no KONE API publishes: **vibration**,
  **temperature** and each part's **age**.
- **Your input** — the average load, once you change it from KONE's value.
- **Standard / Assumption** — a published standard or a stated assumption.

Where the KONE data is too thin (for example only one preventive visit, so
no service interval can be measured) the page says so rather than guessing.
There are no live KONE credentials in this build, so "KONE API" values are
recorded example responses; with credentials the same page reads the real
lift.

**In plain terms:** a what-if machine that starts from what KONE actually
knows about a lift and only fills in what KONE cannot measure.

---

## 6. Analytics — fleet-wide numbers, and is the AI honest?

**What it's for:** two things at once — deeper fleet-level statistics than
the Dashboard shows, *and* proof that the AI's confidence numbers actually
mean what they say.

**Sections, top to bottom:**

- **Filters** — narrow every chart on the page by part type, lifecycle
  status, location or install-date range.
- **Headline stats** — components in scope, how many the AI has assessed,
  average health, and how many are safety-critical / awaiting inspection.
- **Recovery potential / carbon impact / diverted from disposal /
  component recovery demand** — four more prototype-estimate tiles.
- **Charts** — disposition split, health distribution, part-type breakdown,
  a radar chart of health by band, lifecycle stages, AI confidence
  distribution, recovery value by type, environmental impact by type, monthly
  activity, and **feature importance** — which of the eleven inputs the model
  actually leans on most (inspection score and operating hours dominate).
- **Model credibility panel** — this is the important one:
  - **Calibration error (ECE)** *(Expected Calibration Error — a single
    number measuring whether "80% confident" really is right about 80% of the
    time)*. Lower is better; near-zero means the model isn't overconfident or
    underconfident.
  - **Abstention rate** — what fraction of cases the model refuses to answer
    (`DEFER_TO_INSPECTION`) rather than guess.
  - **Accuracy when it answers** vs. accuracy if it were forced to answer
    everything — showing that letting it abstain makes the answers it *does*
    give more trustworthy.
  - **Conformal coverage target** *(a statistical guarantee — see the
    glossary below)*.
  - **Reliability diagram** — a chart plotting "confidence the model claimed"
    against "how often it was actually right." Dots sitting on the diagonal
    line mean the confidence numbers are honest.
- **Sustainability summary and impact assumptions** — the exact constants
  (cost per part, mass per part, CO₂ per kilogram of material, etc.) used to
  compute every money and carbon figure anywhere in the app, laid out in one
  table so nothing is hidden.
- **Safety-critical inspection queue** — the same queue as the Dashboard,
  with more columns (location, last service date, exact requirement text).

**In plain terms:** this page proves the AI isn't just confident-*sounding* —
it's confident *correctly*, and it tells you when it genuinely doesn't know.

---

## 7. Forecast — predicting the future, not just describing today

**What it's for:** everything above describes parts that already exist and
have already been assessed. Forecast instead predicts *which* parts will
need attention *in the future*, and whether the repair workshop will be able
to keep up.

**Controls:** group the forecast by part type, site, or region; pick a
horizon (12, 24 or 36 months ahead).

**Sections:**

- **Headline tiles** — total forecast removals over the chosen horizon,
  today's already-overdue backlog, peak workshop utilisation, and the
  bottleneck part type (whichever type will demand the most workshop hours).
- **Forecast removals by quarter** (stacked bar chart) — how many parts of
  each type are expected to need attention, quarter by quarter.
- **Capacity utilisation by quarter** (bar chart) — forecast workshop
  workload as a percentage of declared capacity; bars go red above 100%.
- **A warning banner**, only shown if some future quarter's forecast workload
  exceeds capacity — naming exactly which quarters.
- **Recommended intake schedule** (table) — for each quarter: work arriving,
  work carried over from a previous overloaded quarter, work actually
  scheduled, and work that has to be pushed further out. Nothing is silently
  dropped; a bottleneck shows up as a growing "deferred out" number.
- **Model and assumptions** — the forecasting model's own name and a
  physics sanity-check number (see glossary: "Weibull shape"), its
  backtested accuracy, and the labour-hour/capacity assumptions behind the
  capacity chart.

**In plain terms:** it's a weather forecast for the fleet — "here's what's
going to break down and when, and here's whether the workshop can handle it."

---

## 8. Compliance — turning history into paperwork a regulator wants

**What it's for:** large companies are legally required to report how much
material they send back into use versus how much they throw away, in
kilograms. This page produces that actual report from the platform's own
records — not a rough estimate typed into a slide.

**Controls:** pick a reporting period (a full year, or a specific quarter),
**Export CSV**, and Refresh.

**Headline tiles:** resource inflows (material coming into service),
secondary share (the ESRS term for how much of that was recovered material
rather than brand new), resource outflows (material leaving the fleet), and
the percentage diverted from disposal versus sent to a landfill. These tiles
use the regulation's own category names ("preparation for reuse",
"recycling"), which is why those words still appear on this page.

**A visible warning** stating exactly what percentage of every number above
is an *estimate* rather than a weighed measurement, and why (most parts
haven't been individually weighed yet — the system uses a per-type average
until they are).

**Three tabs:**

- **ESRS E5 (EU)** *(the EU's Corporate Sustainability Reporting Directive —
  the specific rule requiring companies to disclose material flows)* — charts
  of material flows by type, outflows by ESRS route (preparation for reuse,
  recycling, or disposal - the regulation's wording), and a critical-raw-materials breakdown *(scarce
  substances like copper and rare earths the EU separately tracks)*.
- **BRSR (India)** *(India's equivalent sustainability reporting
  requirement)* — the same idea, in the two categories India's rule asks for:
  reclaimed input share, and waste/circularity.
- **Evidence** — this is the trust mechanism: for every number on this page,
  it shows exactly which tamper-proof history entries it was calculated from,
  and whether the platform's own daily "anchor" (a backup fingerprint meant
  to survive even a rogue database administrator) is actually protected by
  an outside witness yet (honestly: not yet — the page says so directly).

**In plain terms:** this is the page that turns "we track our parts
carefully" into an actual filing a company's sustainability team could hand
to a regulator — while being upfront about exactly which numbers are still
estimates.

---

## 9. Audit Log — the tamper-proof history, provable on demand

**What it's for:** every meaningful action anywhere in the app — registering
a part, running an AI assessment, changing a
part's status — gets permanently recorded here, in an order that can't be
secretly rewritten.

**What's on it:**

- **Headline stats** — total records, how many distinct entity types and
  actions are represented, and the current chain "head" fingerprint.
- **Filters** — narrow the log by entity type or action.
- **The log table** — every entry, newest first. Expand one to see its full
  recorded snapshot and its two fingerprints (its own, and the one it points
  back to).
- **Export CSV** — download the whole log.
- **"Verify audit integrity" button** — the single most important control on
  this page. Click it and the system recomputes every fingerprint in the
  entire history from scratch and confirms nothing was ever secretly edited.
  If someone *had* tampered with an old record, this button would say exactly
  which record and why.

**In plain terms:** it's a diary that can't be edited after the fact, with a
button that proves it.

---

## Glossary — terms used above

- **Digital Product Passport (DPP)** — a permanent, standardised ID for a
  physical product, meant to work regardless of which website or company
  system is running at the time. Required by an upcoming EU regulation for
  construction products, which elevator parts count as.
- **Weibull shape** — a single number from the forecasting model's underlying
  statistics. Above 1 means "the older this part gets, the more likely it is
  to fail soon" — i.e., it's actually modelling wear-out, not something
  random. The model here reads 1.51, which is the expected physical behaviour.
- **Conformal prediction / coverage target** — instead of forcing one
  guess, the model calculates the *smallest set* of possible answers that is
  mathematically guaranteed to contain the right one a chosen percentage of
  the time (e.g. 90%). If that set has more than one answer in it, the case
  is genuinely ambiguous, and the model abstains rather than picking one.
- **Calibration** — making a stated confidence level actually mean what it
  says. "80% confident" should be right about 80% of the time; if it's
  really only right 60% of the time, the confidence number is overselling
  itself.
- **Tamper-proof history / hash chain** — every record stores a
  cryptographic fingerprint of the record before it. Edit any old record and
  every fingerprint after it stops matching — so tampering is provable, not
  just discouraged.

---

## How to show an evaluator that it works (simple version)

You don't need to explain any code. Just click through this order and say
the one sentence under each step out loud.

### Step 1 — Sign in
*"The app is locked. I'll sign in as a supervisor — and note the top right now
shows who I am and what I'm allowed to do. Everything I touch from here is
recorded against this account."*

### Step 2 — Open the Dashboard
*"Here is the whole fleet — how healthy it is, and what it's worth if we
recover it instead of scrapping it."*

### Step 3 — Open a part's Passport (Components → click any part → Passport)
*"Every part has a life story. Here's its history, its current condition,
and a QR code you could scan on the real physical part."*

### Step 4 — Click "Run AI Assessment" on that part
*"The AI just looked at this part's actual numbers and recommended
[whatever it says]. It also shows exactly which readings drove that
decision, in plain English — it's not a black box."*

### Step 5 — Go to a safety-critical part (a Steel Rope, Brake or Governor)
and run the assessment there too.
*"Watch — even though the AI is [90-something]% confident, it still shows a
mandatory human inspection warning. For these three part types, the AI is
never allowed to have the final word. That's a hard rule, not a suggestion."*

### Step 6 — Go to AI Prediction, type in a component that's known to be
ambiguous, or point out any part that returned "DEFER_TO_INSPECTION" earlier
*"And sometimes the AI just says 'I'm not sure' instead of guessing. That's
on purpose — a system that admits when it doesn't know is more trustworthy
than one that always sounds confident."*

### Step 7 — Open Analytics, scroll to the reliability diagram
*"This chart is proof, not a claim. It shows that when the model says '80%
confident,' it really is right about 80% of the time. We measured this — we
didn't just assert it."*

### Step 8 — Open Forecast
*"This isn't just describing today — it predicts which parts will need
attention months from now, and whether the repair workshop can keep up with
that workload before it becomes a bottleneck."*

### Step 9 — Open Simulation
*"Every parameter the KONE API publishes comes from KONE first; only
vibration, temperature and part age - which no KONE API carries - are
simulated, and each row says which is which."*

### Step 10 — Open Compliance
*"This is the report a sustainability team would actually have to file with
a regulator — real kilograms of material in and out, not a made-up
percentage on a slide. And it tells you honestly which numbers are still
estimates rather than pretending everything is exact."*

### Step 11 — Open Audit Log, click "Verify audit integrity"
*"This button just recomputed the fingerprint of every single record in the
system's history and confirmed none of it was secretly edited. That's what
makes every number on the Compliance page trustworthy instead of just
asserted."*

### Step 12 — Sign out, sign back in as the read-only auditor, open any part,
and click "Run AI Assessment"
*"It refuses. This account can read every record in the system — including the
audit trail itself — and cannot change a single one. That's what makes the
audit trail worth anything: the person checking the books can't write in
them. And every entry in that trail now names a verified account, not
whatever name the sender felt like typing."*

**That's the whole story in twelve clicks:** prove who you are → track a part
→ get an explainable AI recommendation → enforce a hard safety rule the AI
can't override → predict what's coming → simulate from KONE data → turn the
record into a real compliance report → prove none of it was tampered with →
show that not even the auditor can tamper with it.
