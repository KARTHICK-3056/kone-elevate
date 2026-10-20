# Component Passport — Progress Report

**Where the build stands, in plain language, as of 21 September 2026.**

This is a companion to [`plan.md`](plan.md), which is the original audit and
the master 7-phase roadmap (P0–P6). This file answers a narrower question:
**of that roadmap, what actually exists in the code right now, and what is
the single next thing to build?**

Any technical term is defined the first time it appears, in *(italics like
this)*.

---

## 1. The one-paragraph version

Four of seven planned phases are fully done, and a fifth is almost all the
way there: the project now has version control and automated testing (P0),
the AI model can say "I'm not sure" instead of guessing and reports how
confident it really is (P1), it can predict *when* parts will need attention
and whether the workshop can handle the workload (P2), it now produces the
actual sustainability reports EU and Indian regulators require, from a
permanent record of material it keeps itself (P3), and — once Docker and a
real database turned out to be available in this build environment after all
— **production hardening (P4)** is now done except for one piece that
genuinely needs a real company Microsoft account this environment has no
access to. Real logins, keeping different companies'/countries' data
separate, handling a fleet many times larger than the 60-part demo, proper
monitoring and alerting, and backups that can restore to any exact moment
are all built and tested against a real (not simulated) 200,000-part
database — not just the 60-part demo fleet. Everything still runs on
made-up (*synthetic*) data — nothing here has been checked against a real
elevator yet. The next piece worth building is P5, which — like the small
remaining slice of P4 — needs things this environment doesn't have: a KONE
developer account and real removal data from actual elevators.

---

## 2. Status at a glance

| Phase | Name | Status | Can it be finished here? |
|---|---|---|---|
| **P0** | Make it real (git, CI, reproducibility) | ✅ Done | Two small items need a real GitHub account + Docker installed |
| **P1** | A model a safety engineer will accept | ✅ Done | Yes — fully finished |
| **P2** | Forecasting & refurbishment capacity | ✅ Done | Yes — fully finished |
| **P3** | The compliance engine | ✅ Done | Yes — code complete; three items need real-world inputs (see below) |
| **P4** | Production hardening (logins, security) | ✅ Done, except SSO | Almost fully — real logins/roles, multi-tenancy, scale, observability, secrets/rate-limiting/SBOM, threat model, and a real tested backup restore are **done**; only swapping local login for the company's real Microsoft sign-in needs infrastructure this environment lacks |
| **P5** | Field reality (offline app, real KONE systems) | ⬜ Not started | Partly — needs a KONE developer account |
| **P6** | Validation & pilot (real elevators) | ⬜ Not started | No — needs real KONE removal data that doesn't exist yet |

---

## 3. What is done — explained simply

### P0 — Make it real

**The problem before:** the project had no version history at all — no way
to undo a bad change, no record of who changed what. It also weighed 82
tests that nothing ever ran automatically, and had genuine bugs no one had
found because nothing was checking.

**What exists now:**

- **Git** *(a running history of every change made to the code — like
  "track changes" for an entire project, letting you rewind or compare any
  two points in time)* — 8 commits, each with a clear explanation of what
  changed and why.
- **CI** *(Continuous Integration — a robot that automatically re-runs every
  test the moment code changes, so a mistake is caught in minutes instead of
  being discovered by a user)* — set up and passing.
- **A lockfile** *(a list that pins the exact version number of every
  external library the project depends on)* — so the project builds
  identically on any machine, forever, instead of quietly picking up a newer
  library version that changes behaviour.
- **A startup safety check** — the app now refuses to start if it's still
  using the default placeholder password, closing a real hole where the
  documented "one-command demo" would have deployed insecurely.
- **`derive_impact_claims.py`** — a script that recalculates every rupee and
  CO₂ figure used in the pitch, straight from the code, and explicitly flags
  one pitch number ("₹4.9L saved per site per quarter") as **impossible to
  verify** because no code tracks "a site" as a concept yet.

**Three real bugs found and fixed** (not hypothetical — each was reproduced
with a failing test first, then fixed):

1. **The tamper-proof history could break itself.** If two people saved
   changes at the exact same moment, the system would wrongly report
   "tampering detected" on data nobody had touched.
2. **The backend would crash on startup** in the real deployment
   configuration, because of how one setting was being read.
3. **The frontend's automatic code-quality checker was silently doing
   nothing** on every file that used a certain type of check.

**What's genuinely left in P0** (blocked on things outside this environment,
not on unfinished work):
- Pushing the code to an actual GitHub/GitLab account with branch
  protection — needs your own account credentials.
- Running `docker compose up` on a machine with Docker installed — this
  sandbox has no Docker daemon.

---

### P1 — A model a safety engineer will accept

**The problem before:** the AI always gave a confident-looking answer, even
when it was genuinely unsure. And when it said "80% confident," there was no
proof that meant anything — it might really only be right 60% of the time.

**What exists now, and why it matters:**

- **Calibration** *(making a confidence number mean what it says — "80%
  confident" should be right about 80% of the time, checked and corrected
  mathematically)*. Measured error: **0.019** (0 is perfect). There's a
  chart on the Analytics page proving this — dots on the diagonal line mean
  honest confidence.
- **The model can now say "I don't know."** A fifth outcome,
  `DEFER_TO_INSPECTION`, using a technique called **conformal prediction**
  *(instead of forcing one answer, calculate the smallest set of answers
  mathematically guaranteed to contain the correct one 90% of the time — if
  that set has more than one item, the case is genuinely ambiguous)*.
  - It abstains on **17.8%** of cases.
  - On the 82% it does answer, accuracy rises from 81.8% → **86.8%**.
  - On the cases it declined to answer, it would only have been right 58%
    of the time if forced — proving it's correctly finding its own blind
    spots, not abstaining randomly.
- **A cost matrix** *(a table stating that not all mistakes are equally
  bad — recommending "reuse" for a worn brake is dangerous; recommending
  "refurbish" for a good part just wastes money)*. Previously every mistake
  was scored identically.
- **Three independent ways of explaining each answer** instead of one,
  including **SHAP** *(a method that shows, for one specific part, exactly
  how much each individual reading pushed the recommendation in each
  direction)*.
- **An honest accuracy number published alongside the flattering one.** The
  82% headline accuracy comes from randomly shuffling the data. Trained on
  older installations and tested on newer ones — which is what actually
  happens in the real world — accuracy drops to **71.7%**. Both numbers are
  now in the code's own output, not just the higher one.
- **A drift detector** *(a script that checks whether new data still looks
  statistically similar to the data the model was trained on, and raises an
  alarm if it doesn't)* — verified to correctly stay silent on real data and
  correctly alarm on deliberately corrupted data.

---

### P2 — Forecasting and refurbishment capacity

**The problem before:** the pitch promised "forecast end-of-life, plan
refurbishment capacity ahead." Zero code existed for this. It was purely a
slide.

**What exists now:**

- **A survival model** *(the branch of statistics built for "how long until
  X happens" — the same kind of maths used for medical trials and machine
  reliability)*, specifically a **Weibull AFT model** *(a mathematical curve
  shape for time-to-failure that has a dial called "shape" — if that dial
  reads above 1, things become more likely to fail as they age, which is
  exactly what wearing out looks like)*. This project's model reads **1.51**
  — a genuine physics sanity check, passed.
- Correctly handles **censoring** *(most of your parts haven't failed yet —
  you only know they've lasted at least this long, not the full lifespan.
  Throwing that information away, or worse, ignoring it, badly skews the
  answer)*. 41% of the training data is censored, which is most of it, not
  an edge case.
- **Forecasts removals per quarter** — grouped by part type, physical site,
  or country — for the next 3 to 60 months, each with a confidence range.
- **A capacity planner** — turns those forecasts into workshop labour hours,
  compares them against how much the workshop can actually handle, names the
  bottleneck part type, and produces a schedule that pushes overflow work
  into the following quarter rather than silently dropping it.
- **A published accuracy report (backtest)** — the forecast was checked
  against data it hadn't seen: **13.1% average error**, ranging from a very
  good 1.5% at the 6-month mark to a weaker 23.4% at 3 months (expected,
  since so few events happen in such a short window that any error looks
  large as a percentage).
- **A new Forecast page** in the app with both charts live.

**A mistake worth knowing about, because it shows the verification process
working as intended:** the first version of this put **34 of 40 predicted
removals into the very first quarter** — statistically nonsensical. The
cause: the model predicts *when a part will first need attention*, but most
of the demo fleet had **already** been flagged as needing attention. The fix
separates "already overdue" (counted as this quarter's existing backlog)
from "still healthy, being forecast" (the population the model is actually
valid for). This also fixed a second issue where the app displayed "workshop
0.3% busy" while 147 hours of real work sat waiting.

**A second bug caught by directly questioning the plan's own checklist**
rather than trusting the test suite: one specific forecast row could show a
confidence range with the bottom number *higher* than the top number — a
mathematically invalid state. The test that should have caught this had
passed anyway, because it used too small a sample to reach the part of the
curve where the bug appeared. Both the bug and the weak test are now fixed,
with a new test that was verified to fail on the old code before being
accepted.

### P3 — The compliance engine

**The problem before:** the pitch promised "auditable lifecycle data for
CSRD/BRSR." What existed was a tamper-proof history — proof that a record was
never edited — which is not the same thing as a report. Worse, the platform
had never once recorded a **kilogram**. A part's weight was looked up from a
settings file at the moment a number was drawn on screen, then forgotten. The
two disclosures that actually matter (see below) are measured in *tonnes of
material*, so no amount of clever querying could have produced one.

**What exists now:**

- **A material-flow ledger** *(a permanent, append-only list of every time a
  part's material moved — "260 kg of steel left the fleet for recycling on
  this date")*. Weight stops being a throwaway calculation and becomes a
  recorded fact. Every single lifecycle change now writes one of these rows.
- **Each row is tied to the tamper-proof history.** A row carries the
  fingerprint of the history entry recording the same event, so a regulator
  can start from a single line in a report — "12 tonnes of steel" — and walk
  back to the individual, individually-fingerprinted events that add up to it.
  A report that just states a number is a claim; one that names its evidence
  is evidence.
- **The actual ESRS E5 report** *(ESRS E5 is the EU's rulebook for reporting
  how much material a company takes in and sends out)*. It produces the real
  tables: material coming in, material going out, split by type of material and
  by what happened to it — reused, recycled, or thrown away. Any period:
  a year, a quarter, a month, or a custom range. Downloadable as a spreadsheet.
- **The circularity number the whole product exists to prove.** When a part is
  removed, refurbished and refitted, it correctly appears twice — once as
  material leaving, once as *reused* material coming back. On the demo data
  that now reads **0.26 tonnes of reused material in, 0.91 tonnes out with
  100% kept out of landfill**. Getting this right was subtle: moving a part
  between two "gone" states must *not* count as it leaving twice, or the
  numbers silently inflate. There is a test for exactly that.
- **The Indian equivalent (BRSR)**, covering the two principles that ask about
  reclaimed material and waste.
- **A critical-raw-materials count** *(the EU now separately tracks scarce
  substances like copper and rare earths)*, broken down by substance — which
  points straight at the electronics, exactly as intended.
- **A real digital product passport.** Each part now has a permanent
  identifier that will never change, and the QR code on the label encodes it.
  **Previously the QR code pointed at `localhost`** — a web address that only
  works on the machine running the demo. A passport whose link dies when you
  switch the server off is not a passport. Old labels still scan.
- **Engineering standards, finally cited.** The pitch called the passport
  "standards-based" while no standard number appeared anywhere in the code.
  Each part type now names the published standards that govern it (ISO 4344
  for lift ropes, ISO 281 for bearing life, EN 81-80 for modernising old
  lifts, and others), shown on the passport.
- **A new Compliance page** in the app, with the reports, the charts, and an
  Evidence tab showing exactly which history entries each figure came from.

**Three things this deliberately does NOT claim** — each is marked in the code,
the API responses and the UI rather than quietly glossed over:

1. **Every tonne is still an estimate.** No part has ever been weighed, so the
   ledger falls back to a per-type guess and *records that it did so*. Every
   report publishes the percentage of its own mass that rests on estimates.
   Today that reads **100%**, which is the correct answer, not a bug. Weigh
   the parts and the figure drops on its own, with no code change.
2. **The standards clause numbers are unverified.** Standards are copyrighted
   documents that must be purchased, and they were not available here. The
   standard names and years are right; the pointers to specific clauses inside
   them were assembled from public summaries. Every one carries a visible
   "CLAUSE UNVERIFIED" badge. Showing a technician an invented clause number as
   though it were authoritative would be precisely the confident-sounding
   wrongness this project spends its effort avoiding.
3. **The tamper-proofing still can't stop a database administrator.** The
   fingerprint chain catches anyone editing a record in place. It does not
   catch someone who deletes a record and rebuilds every fingerprint after it —
   from inside the database that forgery is invisible. The fix is to publish a
   daily fingerprint somewhere outside the company's own systems. That
   machinery is built and runs; there is nowhere external to publish to in this
   environment, so the app reports **"NOT PROTECTED against a database
   administrator"** in plain words rather than implying a safety that isn't
   there.

**One real bug found and fixed on the way:** the form for adding a component
accepted a weight field and then silently threw it away before saving. It was
caught by writing the test first — the test that proved a weighed value is
preferred over an estimate failed, and it was right to.

**A test proven to be worth having:** the deliverable asked for a stress test
writing 1,000 history entries from 10 directions at once. It passes. To check
the test was actually capable of failing, the safeguard it tests was
temporarily switched off — the history broke at record 6, exactly as predicted.

---

### P4 — Production hardening *(in progress — logins done)*

**What it is:** turning this from "a demo one person can run" into "something
IT security would actually approve." Five separate pieces: real logins,
keeping different clients' data apart, monitoring, handling 1.8 million parts,
and locking the doors (secrets, backups).

#### ✅ What is now done — real logins and roles

**The problem before:** nobody logged in. Anyone could type any name into a
hidden field and the system simply believed them — and that unverified name
was then written permanently into the tamper-proof history as "who did this."
The app's own navigation bar said it out loud: *"Prototype - no auth."* This
mattered far more after P3, because the sustainability reports P3 produces
cite that name as part of their evidence.

**What exists now:**

- **A real sign-in screen.** The app is closed until you log in. Accounts have
  properly protected passwords *(hashed — stored as a scrambled fingerprint
  that cannot be turned back into the password, deliberately made slow to
  compute so guessing millions of passwords is impractical)*.
- **Five permission levels**, each seeing a different slice: technician,
  supervisor, refurbishment planner, sustainability controller, and a
  **read-only auditor** who can see absolutely everything — including the
  audit trail — and change nothing. Try to act as the auditor and the app
  refuses with a plain-English explanation.
- **The tamper-proof history now names a verified person.** This is the whole
  point of the phase: a compliance report signed by "whoever sent the request"
  is not something an auditor can rely on. Now it is signed by an account that
  actually had to prove who it was.
- **No sign-up page — on purpose.** A page that lets someone pick their own
  permission level is a security hole wearing a registration form. Accounts
  are created by a supervisor, exactly as a real company's HR onboarding
  works. Five demo accounts are listed right on the sign-in screen so an
  evaluator can get in immediately.
- **The QR passport deliberately still needs no login.** A technician scanning
  a label in a basement machine room has no account and no signal. Locking
  that page would break the single thing the QR code exists to do, so it stays
  open — and there is a test that fails if anyone ever accidentally closes it.

**A second, worse hole found while fixing the first:** accepting or rejecting
a recovered-part match let the *body of the request* name who made the
decision. A caller did not even need to fake the hidden field — they could
just write any name in the message itself. Both paths are now gone. To prove
the tests genuinely catch this rather than merely passing, the old behaviour
was deliberately switched back on: all three tests failed immediately, naming
"ceo@kone.com" as the culprit exactly as designed.

**A real bug found by clicking the button:** signed in as the read-only
auditor, pressing "Run AI assessment" appeared to do nothing at all. The
server was correctly refusing it, but the screen threw the refusal away
silently. Now it shows the reason.

#### ✅ Also now done — everything except real-company sign-in

Docker and a real Postgres database turned out to be available in this build
environment after all, which changed what "can't be finished here" actually
meant for the rest of P4. Six more pieces landed, all validated against a
real (not just simulated) Postgres instance, not just described:

- **Keeping clients apart (multi-tenancy).** Every account now belongs to a
  country — a hard wall: a technician in one country gets the exact same
  "not found" response for a component in another country as for one that
  plain doesn't exist, so no one can even tell the difference between "wrong
  country" and "never existed." A home branch *(frontline unit)* is a softer
  default — a technician sees their own branch's parts by default, but can
  ask to see the whole country. The Recovery Exchange (part-matching page)
  deliberately ignores the branch wall, on purpose — routing a recovered part
  from one branch to another is the entire point of that page. Two accounts
  — the sustainability and audit roles — see across every country, because a
  country-scoped sustainability report or tamper-check would not actually be
  the company-wide thing it claims to be.
- **Handling the real fleet size.** Every dashboard number is now computed by
  the database directly instead of the app loading every part into memory and
  counting by hand. Tested for real against 200,000 parts and 600,000+
  service records in a real database (not the full 1.8 million KONE's real
  fleet would be, but 3,000x more than the 60-part demo fleet): the main
  dashboard page went from taking almost 2 seconds to well under a quarter of
  a second. One page (the combined "everything at once" analytics view) is
  faster than before but still slower than the target — written down
  honestly rather than rounded up to "done."
- **Monitoring.** Every log line the app writes can now be traced back to the
  exact request that caused it. There's a page (`/metrics`) a monitoring tool
  can read showing how fast the AI is responding, how often it says "I'm not
  sure," and whether the tamper-proof history last checked out clean. Two new
  scripts can be put on a timer to watch for the AI's data drifting away from
  what it was trained on, or the tamper-proof chain breaking, and can ping a
  Slack/alerting channel when either happens.
- **Locking the doors.** Login and sign-up pages now refuse a caller who
  tries too many times in a row (guards against automated password/code
  guessing). Every response now carries standard browser security headers.
  Secrets like the login-signing key can be pulled from a proper secrets
  vault instead of a plain settings file, if one is available — tested
  against a stand-in, since no real vault server existed in this
  environment to test against for real. Every dependency the project uses is
  now listed in a standard machine-readable inventory *(SBOM — a receipt of
  every ingredient, the software equivalent of a food label)*, generated
  automatically. That inventory check found the backend has zero known
  security holes, but the frontend genuinely has some in its build tools and
  in the page-navigation library — written down rather than hidden, because
  fixing the navigation one properly means rewriting how every page link in
  the app works, which deserves its own careful pass, not a rushed one here.
- **A written-down list of "here's what could go wrong and what we did about
  it"** *(a threat model)*, including the one uncomfortable finding that
  matters most: a technician's name and an auditor's email are both stored
  permanently in the tamper-proof history, and — because the whole point of
  that history is that nothing in it can be edited or removed — there is
  currently no way to honor someone's legal right to have their name erased.
  That is written down as the single most important thing to fix before any
  real person's data (not the made-up demo names) goes anywhere near this
  system.
- **Backups that can restore to any moment, not just to the last save
  point**, and proven, not just described: a real backup of the real
  200,000-part database was taken, a marker was written to the database, a
  little time passed, a second marker was written, and the database was
  restored to the exact moment between the two markers — the first marker
  came back, the second did not, and — the part that actually matters for
  this product — the tamper-proof history was checked afterward and still
  came back completely clean. The exact clock times and the restore's own
  printed log are kept as the evidence.

#### ⬜ What is still left in P4

- **Real company sign-in (Entra ID / SSO)** — still needs a real company
  Microsoft account this environment has no access to; local login with the
  same guarantee (every action tied to a verified identity) works today, and
  swapping in Entra later only touches the login step itself.
- **No second pair of eyes on granting extra permissions** — a compromised
  supervisor account can still hand out other accounts' extra permissions on
  its own signature; the standard fix (requiring a second approval) was not
  built.
- **The frontend's own security holes** are found and written down, not
  fixed — see above.
- **A rehearsed backup restore exists; a rehearsed full-blown "everything is
  on fire" drill with a stopwatch and a runbook someone unfamiliar with the
  system can follow does not.**

---

## 4. What is NOT done — and what's next

The rest of P4 is listed in its own section above. The two phases below have
not been started, and neither can be finished in this environment.

---

### P5 — Field reality and systems integration

**What it is:** making the technician's phone app work with no signal in a
basement machine room (an offline-capable app), and connecting to KONE's
actual existing systems (KONE already streams live elevator data — this
project should plug into that, not build a second, competing system).

**Why it can't be finished here:** connecting to KONE's real systems
requires registering a real developer account on KONE's own API portal —
this environment has no such account, and building a fake connection would
be actively misleading. The offline-capable phone app itself is pure code
and *could* be built here — it just wasn't prioritized yet.

---

### P6 — Validation and pilot

**What it is:** running the AI silently alongside a real KONE workshop for
one financial quarter, comparing its guesses to what human engineers
actually decided, and using that comparison to prove (or disprove) whether
the model works on real elevators — not just on a synthetic dataset this
project built.

**Why it can't be finished here:** this fundamentally requires real KONE
parts, real removals, and real engineers' decisions. No amount of coding
substitutes for that. This phase can only start once a real organization
agrees to run the pilot.

---

## 5. Two gaps closed against the original submitted abstract

A separate pass compared this codebase word-for-word against the abstract
originally submitted for this project (tech stack, impact numbers, solution
claims), not just against `plan.md`'s own audit. Almost everything in that
abstract turned out to already be built and exceeded — see the full ledger
in conversation. Two things were genuinely missing or unreproducible, and
both were fixable without any external dataset or KONE access, so both were
closed:

- **"PostgreSQL (JSONB for variable sensor metadata)"** was a tech-stack
  claim nothing in the code actually did — every sensor reading lived in
  four fixed columns. `service_events.sensor_metadata` (migration
  `0013_sensor_metadata`) is now real JSONB on PostgreSQL — confirmed with
  `\d service_events` against a live Postgres instance, including that it
  propagates onto the table's year partitions, not just the parent — for
  vendor/sensor-specific readings that don't fit the fixed columns (current
  draw, acoustic emission, door-cycle count, ...). It is on the service-event
  form in the UI, round-trips through the API, and appears in the audit
  snapshot the same event writes.
- **"₹4.9 L and 1.7 t CO₂ saved per site per quarter"** was flagged in
  `plan.md`'s P0 as `NOT DERIVABLE`, correctly — there was no site model
  anywhere in the codebase. `app.services.site_impact_service` is that model,
  built entirely from data and forecasts this system already has: for each
  site, expected quarterly load (current backlog + the P2 survival
  forecaster's arrivals) × that site's own historical average recovery
  value/CO₂ per assessed component, falling back to the fleet-wide average —
  and saying so — for a site with no history yet. Exposed at
  `GET /api/v1/forecast/site-impact`, shown on the Forecast page, and printed
  by `derive_impact_claims.py`. On the 60-component demo fleet this comes out
  to ≈₹78,000 and 0.33 t CO₂ per site per quarter, well under the original
  slide guess — expected, since a real KONE site carries far more components
  than this demo fleet's ~6 per site. The mechanism is now real and
  reproducible; the magnitude will only resemble the slide once it runs
  against a fleet the size the slide assumed.

Both were verified against a real PostgreSQL instance (not just SQLite),
with the full backend test suite (289 tests, up from 247) passing against
both databases, and the frontend build/lint/vitest suite passing with the
new UI wired in.

---

## 5a. The loop now actually closes (CE-1)

A circular-economy audit of our own claim found something worse than a
missing feature. `LifecycleStatus` ran `ACTIVE → REMOVED → RECOVERED →
REFURBISHMENT → AVAILABLE → ALLOCATED` **and stopped**. Nothing ever moved
a component back to `ACTIVE`, so:

- a recovered part could never be assessed again, because assessment only
  runs on in-service components;
- its second life accrued no history, no hours, no passport entries;
- nothing counted how many lives a component had had — the single number a
  circular economy is actually judged on;
- and the seed script papered over it by setting `current_status = ACTIVE`
  and writing a material-flow row **by hand**, which is why the demo could
  report reused material while no component's own history recorded a refit.

A platform whose central pitch is a closed loop could not represent one
component going round it even once.

**What exists now:**

- **`REINSTALLATION`**, the counterpart to `REMOVAL`. A component allocated
  to a demand goes back into service through the ordinary service-event
  endpoint, and is rejected with a 409 if it was never allocated.
- **`app/utils/lifecycle.py`** — the state machine the codebase never had.
  `ALLOCATED → ACTIVE` is the edge it exists to add; `RECYCLED` and
  `DISPOSED` are deliberately terminal, because material that went to a
  foundry or a landfill does not come back and a system that let it would
  be overstating circularity in a disclosure someone is meant to rely on.
- **`Component.life_cycle_number`** (migration `0014`). 1 for a part
  installed new, incremented on every refit. The passport and component
  page show a **Life 2** badge.
- **The part follows the part.** Reinstatement reads the accepted match's
  service demand and moves the component's location to where it was
  actually fitted, instead of still naming the building it came out of.
- **`app/services/reinstatement_service.py`** — one implementation, used by
  both the API and the seed script, so the two cannot drift apart again the
  way they already had.
- **The exchange records it.** A refitted listing becomes `INSTALLED`
  (distinct from `WITHDRAWN`, which means pulled off the exchange unused),
  and the Recovery Exchange page has a **Loops closed** tile.

**Verified end to end against real PostgreSQL**, not just SQLite: the
seeded fleet now refits `KE-STE-000004` at Delhi on life 2, the exchange
reports `installed: 1`, and — the payoff — that refit lands in the
**ESRS E5-4 disclosure as a 0.095 t secondary inflow at 100% secondary
share**, traced back through the audit chain. 298 backend tests pass
(9 new, up from 289); frontend lint, production build and vitest all pass.

**Not verified:** the two new UI badges and the Loops-closed tile were
checked by compilation, lint, production build and the API payloads behind
them — no browser was available in this environment to look at them
rendered.

**Two defects found reviewing CE-1, both reproduced before being fixed,
and both with a test verified to fail on the old code:**

1. **A just-refurbished part was filed as its own backlog.** Once a
   component could be refitted, its *pre-recovery* assessment stayed its
   `latest_prediction`. A control board recovered on a DISPOSE verdict,
   refurbished and refitted still read **DISPOSE on its passport**, and
   `forecast_service.split_fleet` counted it as refurbishment backlog the
   instant it re-entered service — the capacity planner queueing labour
   hours for work that had just been completed. This is the same class of
   error P2 already fixed once ("34 of 40 removals in quarter one"),
   reappearing through the new loop edge. Fixed by tying each assessment to
   the life it describes (`predictions.life_cycle_number`, migration
   `0015`); `latest_prediction` now skips earlier lives, and reinstatement
   clears the cached recommendation, confidence and health score so a
   refitted part reads as *awaiting reassessment* rather than carrying a
   verdict about a part that no longer exists in that condition.
2. **The branch did not follow the part.** `location` moved to the
   destination site but `frontline_unit` — the soft tenancy default that
   decides which branch sees a component — stayed behind, so the two
   contradicted each other and the branch that had just fitted the part
   could not see it in its own default view. Country is deliberately left
   alone: the exchange is country-scoped, so a refit never crosses that
   hard boundary.

300 tests pass after the fixes.

---

## 5b. Circularity is now measured, not inferred (CE-2)

**The problem:** every impact figure this platform produced was rupees or
kilograms of CO₂e. Neither is a circularity measure. A fleet can improve
both while becoming *less* circular — swap steel for lighter virgin
composite and carbon falls while material still goes to landfill. For a
product whose whole pitch is a circular economy, the system measured the
*co-benefits* of circularity and never circularity itself.

**What exists now:** the Ellen MacArthur Foundation's **Material
Circularity Indicator** (0 = fully linear, 1 = fully circular), computed
over the same material-flow ledger the ESRS E5 report uses — arithmetic
over data already kept, not new instrumentation.
`GET /api/v1/reports/circularity` for the fleet,
`/reports/circularity/{id}` for one component with every input exposed so
the number can be re-derived by hand. On the demo fleet: **MCI 0.40**
mass-weighted across 60 components.

**The three strategies are reported separately**, because a single score
hides which lever a fleet is actually pulling:

- **Narrow** (use less material) — **reported as not measured, on
  purpose.** It is a design-stage decision this platform never sees.
  Inventing a number for it would undo the credibility the other two buy.
- **Slow** (extend life) — components on a 2nd+ life, and mean life
  achieved against design life (68.1%). This is only non-zero *because*
  CE-1 exists.
- **Close** (cycle material back) — 100% diverted from disposal, 1.4%
  secondary inflow share. The same figures E5-4/E5-5 disclose, expressed
  as circularity rather than tonnage.

**One modelling error caught by its own test.** The first version applied
the MCI utility penalty — which docks a component for a service life cut
short — to *every* component. That drove the whole fleet to a clamped zero
and destroyed the ordering the indicator exists to express. The penalty is
correct only once service has genuinely ended: a part pulled early and
prepared for reuse has not lost those years, the next building gets them.
It now applies only to material that actually left for recycling or
disposal, and the per-component response reports
`utility_penalty_applied` either way.

**What it deliberately does not claim:** `F_R` (recycled content of a *new*
part) is structurally always 0, because that is supplier data this platform
has never held — so MCI is *understated* for any component made from
recycled stock, and every response says so. Utility intensity is assumed
1.0. Lifetimes are the placeholder per-type design envelopes. The masses
carry the same estimated-mass caveat as the E5 report. All of it ships in
an `assumptions` block attached to the figure.

307 tests pass (7 new). Verified end to end against real PostgreSQL through
the running API, and surfaced on the Compliance page.

---

## 5c. The R-ladder, and naming the circularity cost (CE-3, CE-4)

### CE-3 — three missing rungs

The platform recommended four dispositions. The circular-economy field
works from an ordered hierarchy (R0–R9) whose governing principle is to
prefer the innermost viable loop, and measured against it we skipped three
rungs that matter for elevator components: **R4 repair** (fix in place,
never remove), **R6 remanufacture** (strip the core, rebuild to as-new —
routine for motors and drives), and **R7 repurpose** (a sheave retired from
a high-rise is fine in a low-rise).

`app/ml/r_ladder.py` adds them as a **decision layer**, not as new model
classes. Adding them to the Random Forest would have meant inventing three
synthetic label distributions and republishing every metric in the model
card on the strength of them. Instead the classifier still predicts four
classes and explicit rules refine the output into a rung — reported
**alongside** `recommendation`, never replacing it, which is the precedent
`cost_analysis` already set in this codebase.

On the demo fleet the three new rungs pick up **9 of 48 placed components,
and R8 Recycle drops from 12 to 6** — six parts the model would have
shredded now have a tighter loop proposed, which is the entire argument.

Two categories are never refined: an **abstention** (inventing a strategy
on top of "I don't know" defeats the abstention) and **safety-critical
types** (quietly proposing "repurpose this governor" is exactly the
confident-sounding wrongness the safety gate exists to prevent).

**A rule that could never fire, caught before it shipped.** The first draft
hung remanufacture off `REFURBISH and health < 45`. The classifier's
REFURBISH band sits at health 71–80 and anything under 45 is already a
DISPOSE, so the condition was **unreachable** — the rung appeared in the
taxonomy, was advertised as reachable, and could never fire on any real
component. Every threshold was then re-derived against the fleet's actual
distributions, remanufacture moved to the RECYCLE branch (where rescuing a
core from the shredder is both reachable and the stronger circular
argument), and `test_every_refinement_rung_is_actually_reachable` now fails
if a future threshold change strands a rung again.

### CE-4 — the circularity cost had no name

`app/ml/cost_matrix.py` priced a *conservative* error — recycling a part
that was perfectly reusable — at roughly a third of the equivalent
optimistic one, and never named the reason. The decision layer therefore
treated destroying recoverable value as nearly free: a defensible safety
trade-off that **nobody had actually made on purpose**.

v2 splits every cost into three named terms — `operational`, `safety`,
`circularity` — so a reviewer can see which lever they are pulling, and
adds an explicit circularity-loss term that scales with how far value was
destroyed (1.10 → 2.20 → 3.30 across one, two and three rungs).

Safety still dominates, and should. The point is that the ratio is now
published rather than inherited:
`GET /api/v1/model/metrics` returns `safety_circularity_exchange_rate`,
which on a safety-critical type reads **4.36×** — this table charges 4.36
times as much for putting a worn part back into service as for needlessly
destroying a good one. That is a reviewed decision now, and an argument
someone can have with us.

325 tests pass (18 new). Both verified through the running API against real
PostgreSQL; the R-ladder distribution renders on the Compliance page and
the tighter-loop note on the prediction card.

---

## 5d. KONE-backed adapters and the apportionment layer (K-1, K-2)

P5 built an anti-corruption layer with three interfaces and a swap point,
and then had nothing to swap to. Reading KONE's official Apache-2.0
reference implementation (`github.com/konecorp/kone-api-examples`, verified
genuine — see `docs/kone-integration.md` §4.1) supplied the endpoints,
OAuth scopes and response shapes needed to write the real thing.

**What exists now:**

- `kone_client.py` — OAuth2 client-credentials, **per-scope** token cache
  (a token minted for one KEN is not valid for another), the documented
  paths. Credentials come through the P4 secrets provider, never a
  settings file.
- `kone_adapters.py` — `KoneEquipmentIdentityAdapter` (Equipment Status
  API v2) and `KoneServiceRecordAdapter` (Service Info API v2). The only
  module in the codebase allowed to know KONE's field names.
- `kone_features.py` — the apportionment layer (K-2).
- The registry selects them on `KONE_CLIENT_ID`/`KONE_CLIENT_SECRET`, and
  `GET /integrations/status` reports which implementation is live. Every
  integration response now reads its `source` off the active adapter
  instead of a hardcoded `"fixture"` that would have become a lie.

**Spare parts has no implementation and will not get one.** KONE publishes
no spare-parts API, so there is no backend to point at. It stays
fixture-backed whatever is configured, and says so.

**The two-client split is what makes this testable.**
`RecordedKoneApiClient` replays fixtures written in KONE's *real* field
names (`failedComponentCode`, `equipmentConditionOnDeparture`, …) taken
from their published TypeScript interfaces. The mapping logic — the part
that actually breaks if the schema was misread — runs identically against
that and the HTTP client, so it is fully covered today. The HTTP transport
is covered by a test that stands up a local stub speaking the documented
protocol and drives the **real** `get()` through it (an earlier draft
re-implemented `get()` inside the test, which covered the copy and not the
code; the client grew a `base_url` seam so the real method could run).
Verified load-bearing by breaking the auth scheme and watching it fail.

**Still uncovered, and only a live call can fix it:** a documented field
the service omits, a pagination envelope the examples don't show, an
insufficient scope, rate limits.

### K-2 — the assumption that has to stay visible

KONE addresses *equipment*: one whole lift per KEN. We assess
*components*. Attributing a lift's duty to one sheave is **our
assumption**, not KONE's measurement, so every derived field carries a
provenance tag — `measured`, `apportioned`, `derived` or `unavailable` —
and the result reports what share of the vector is grounded (75% on the
recorded fixture). A door operator comes out with twice the load cycles of
the motor in the same lift, and a fraction of the running hours, because
the `APPORTIONMENT` table says so and states why for each type.

Two mismatches are recorded rather than smoothed over: `average_load` is a
**percentage** (KONE publishes `loadPercentage` and no rated-load field,
while our feature is in kg), and `vibration`/`temperature` have no channel
in any KONE feed at all. They return `unavailable`, never a default —
`missing_for_model()` hands the list back so a caller must decide
explicitly. A prediction built on an invented vibration reading must never
be indistinguishable from one built on a measurement.

350 tests pass (25 new). The adapter swap was verified by configuring
credentials and confirming the registry returns the KONE classes.

---

## 5e. Label harvesting, and the assumption register (K-3, K-4)

With no prospect of a KONE contact answering anything, the remaining Track
B work was done on assumptions — written down rather than made silently.

### K-3 — what the API can actually label

`kone_labels.py` derives weak disposition labels from service orders, in
the `WorkshopOutcome` vocabulary the P6 agreement machinery already
consumes. Reading the fields carefully turned up a finding worth more than
the code:

**`technicianActionCode` records what was done to the *equipment*, not
where a removed *component* went.** So the source can observe "this part
was kept in service" directly, and **cannot distinguish refurbished from
recycled from scrapped** for anything that came out. KONE publishes no
disposition field anywhere.

Those cases are returned **censored** — `outcome: None` with a reason —
never guessed. On the fixtures: 4 orders → 2 observed, 1 inferred
(down-weighted to 0.4), 1 censored, and `REFURBISHED_AND_REDEPLOYED` /
`RECYCLED` / `DISPOSED` all land in `classes_never_observed`.

This is structural. A model retrained on these labels alone would drift
**optimistic** — the exact error direction `cost_matrix` prices highest —
so `label_coverage()` reports `usable_for_training: false` and the
censoring percentage. Use it to measure agreement, not to train.

A censored observation is excluded from agreement scoring rather than
counted as a miss: a removal nobody recorded the destination of is missing
data, and scoring it as a disagreement would understate the model on
precisely the cases this source cannot see.

### K-4 — `docs/kone-assumptions.md`

Every assumption across K-1/K-2/K-3, rated by what breaks if it is wrong
and how it would be detected: 🔴 silent, 🟠 loud, 🟡 bounded.

Most of the transport block is 🟠 — one successful call retires it. The
one that matters is 🔴 and worth repeating here: **if KONE's condition
codes run `1` = worst rather than `1` = best, every `inspection_score`
this layer produces inverts** — no error, no crash, a degraded lift
scoring 90. `kone_features.validate_condition_code_direction()` detects it
by checking that orders with recorded failures skew to the worse end, and
returns `insufficient_data` rather than concluding from noise. Run it on
the first real equipment history, before anything consumes a score.

The register also states the conclusion the whole of Track B points at:
**the APIs fix the features, not the target.** The ask worth making is a
historical removal dataset, or a workshop recording outcomes for a
quarter — not API access, which is the instinctive request and the least
valuable of the three.

358 tests pass (33 new across Track B). Verified through the running API.
Nothing here relabels an estimate as a measurement:
`/integrations/status` still reports `live_call_ever_made: false`.

---

## 5f. Two bullets caught by auditing the plan against the code

Re-reading the published plan line by line — rather than trusting the
summaries written while building — turned up two deliverables that had
been reported done and were not:

1. **CE-2 said the circularity report should carry "the same audit-hash
   provenance the other disclosures carry."** It did not. Every ESRS E5 and
   BRSR response embeds a `derivation` block naming the audit range it was
   computed over; the MCI shipped without one. A circularity figure that
   cannot name its evidence is a claim, not a disclosure. Now reuses
   `compliance_service.derivation_evidence` — 93 ledger rows, 93 audit
   entries, chain head, plus a re-derivation note.
2. **K-3 said the harvested labels should "feed into the P6 agreement
   report."** They were built in the right vocabulary and never actually
   wired to the scorer. `agreement_service.score_weak_labels()` now scores
   them through the *same* `COMPATIBLE_OUTCOMES` and
   `OPTIMISTIC_RECOMMENDATIONS` definitions, so "agreement" means one
   thing in this codebase.

It is a **separate** entry point rather than folded into the pilot report,
deliberately: a workshop outcome is somebody stating what they did, a
harvested label is this platform inferring it from a service order, and
one agreement rate over both would launder the second into the first. It
is also weighted — an `inferred` label counts 0.4 of an `observed` one —
so on the fixtures the weighted rate (0.83) sits above the unweighted
(0.67), and both are reported.

One thing it exposed: **the join key does not exist.** KONE addresses
equipment by KEN, this platform addresses components, and nothing maps one
to the other. `score_weak_labels` therefore takes caller-supplied pairs
rather than pretending it can do the join, and the gap is recorded in
`docs/kone-assumptions.md`.

362 tests pass. Every bullet in the plan is now either done or explicitly
blocked on a KONE account.

---

## 5g. `docker compose up` finally verified — and it found something

Both `plan.md` and this file had carried "no Docker daemon available in
this build environment" since P0. That stopped being true at some point
and nobody re-checked, so a P0 item sat open for no reason.

**Run for real on 2026-09-21**, no `.env`, exactly the documented
one-command path. Result: all three services build and reach healthy,
migrations apply to head (`0015_prediction_life`), the demo fleet seeds
into Postgres (60 components, 326 audit rows), the frontend serves and its
nginx tier proxies `/api` to the backend correctly.

**It surfaced one real defect**, which is precisely why the item existed.
The Postgres host port defaulted to **5432**, which collides with a
locally installed Postgres — and the headline command died on a bare
`address already in use`. Any evaluator with Postgres on their laptop
would have hit it. Default is now **55432**, still overridable with
`POSTGRES_PORT`; the database never needed publishing to the host for the
demo anyway, since the backend and pgAdmin both reach it over the compose
network.

Everything built this session was then re-verified **through the real
deployment**, not a test harness:

| | Result in the compose stack |
|---|---|
| CE-1 closed loop | `KE-STE-000004` — ACTIVE, **life 2**, at Delhi |
| CE-2 circularity | MCI **0.434** over 60 components, derivation cites 93 ledger rows / 93 audit entries |
| CE-3 R-ladder | R3=12, R4=4, R5=6, **R6=4, R7=3**, R8=7, R9=17 |
| CE-4 cost matrix | safety-critical exchange rate **4.36×**, matrix v2 |
| Track B | `live_call_ever_made: false`, adapters on fixtures — honest |
| K-3 labels | 25% censored, disposal classes still in `classes_never_observed` |

---

## 6. The one sentence to remember

**Every accuracy number, every forecast, every tonne and every dollar figure
in this project still describes a simulator this project wrote — not a real
elevator.** That is stated honestly in more than a dozen places in the code
and documentation on purpose, and it is genuinely the project's strongest
asset with a safety-regulated buyer: a team that states its limits is more
credible than one that doesn't.

---

## 7. How to check any of this yourself

```bash
# Run every automated backend test (289 checks, ~40 seconds)
cd backend && python -m pytest -q

# See the honest vs. flattering accuracy numbers directly
python scripts/train_model.py

# See the forecast's own accuracy report
python scripts/train_forecast.py

# See every dollar/CO2 figure recalculated from scratch, including the
# per-site-per-quarter figure that used to be flagged NOT DERIVABLE
python scripts/derive_impact_claims.py

# Rebuild the demo fleet, which now records a material ledger as it goes
python scripts/seed_database.py --reset

# Create the five demo sign-in accounts (one per permission level) and
# print their credentials
python scripts/seed_users.py

# Ask whether the tamper-proofing is actually protected (it is not,
# and the script exits 1 to say so)
python scripts/anchor_chain_head.py --check
```

With the app running, the compliance engine answers for itself. Everything
below now needs a sign-in token, which is the point — try any of them without
the `-H "Authorization: ..."` line and you get a 401 instead:

```bash
# Sign in and keep the token
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -d "username=sustainability@kone-elevate.demo&password=elevate-demo-2026" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# The sustainability reports, with the evidence they were derived from
curl -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/reports/esrs-e5?period=2026"
curl -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/reports/brsr?period=2026"

# The kilogram ledger underneath them, and how much of it is estimated
curl -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/reports/ledger-summary"

# One component's passport needs NO token - that is the QR-scan path,
# deliberately left open for a technician with no login
curl "localhost:8000/api/v1/passports/KE-MOT-000003/dpp"

# Projected quarterly recovery value/CO2 per site - the site model that
# used to be missing, with each site's own N and mix source shown
curl -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/forecast/site-impact"
```

Full architecture, API reference, and the original audit are in
[`README.md`](README.md), [`docs/`](docs/), and [`plan.md`](plan.md)
respectively. How every disclosure figure is derived — and what would have to
be true before any of it could be filed — is in
[`docs/compliance.md`](docs/compliance.md).
