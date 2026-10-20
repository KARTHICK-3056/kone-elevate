# Stakeholder map

The P6 deliverable this covers: *"Name the stakeholders. Frontline
maintenance operations, the modernization business, sustainability and
reporting, quality and safety, and IT security. Five different questions,
five different answers."*

---

## 1. The five groups, and what each will actually ask

| Stakeholder | What they care about | The question they will actually ask | Where the answer lives |
|---|---|---|---|
| **Frontline maintenance operations** | Does this make a technician's day easier or harder, and does it work with no signal | "What happens when I'm in a basement with no bars?" | `docs/offline-pwa.md` - the offline write queue and cached passport lookup |
| **The modernization business** | Does this help plan capacity and route recovered parts, not just score them | "Can I trust the Q3 removal forecast enough to book workshop hours against it?" | `docs/forecasting.md` - published backtest MAPE, the current-backlog vs. forecast split |
| **Sustainability and reporting** | Can a real ESRS/BRSR disclosure be filed from this | "Where does the kilogram in your E5 table actually come from, and can I re-derive it myself?" | `docs/compliance.md` - the material-flow ledger and each report's embedded audit-hash range |
| **Quality and safety** | Does the safety gate actually hold, and is the AI Act classification defensible | "What stops this from ever returning a rope, brake or governor to service without a human looking at it?" | `app/ml/predict.py::_apply_safety_gate` + `docs/ai-act-classification.md` |
| **IT security** | Is identity real, is data isolated, is there a plan if something breaks | "Who actually wrote this audit-log row, and can I trust the `actor` field in court?" | `docs/threat-model.md` + `app/api/deps.py::current_actor` (the closed `X-Actor` spoofing path) |

## 2. What each group would push back on today, honestly

- **Frontline operations** would ask why offline mode queues an assessment
  request rather than running the model on-device. Answer, stated plainly
  in `docs/offline-pwa.md`: shipping the Random Forest to run inside a
  browser (ONNX/WASM) was not attempted in this pass; the honest
  interim behaviour is "queued, not answered until reconnected."
- **The modernization business** would push on the forecast's 3-month-
  horizon MAPE (23.4%, published in `models/forecast_metrics.json` and
  `docs/forecasting.md`) - the shortest, most operationally relevant
  horizon is also the least accurate one, because event counts are small
  there. That is disclosed, not hidden, but it is a real limitation on
  near-term capacity commitments specifically.
- **Sustainability and reporting** would push on `CLAUSE_UNVERIFIED`
  standards citations and the `CONFIG_ESTIMATE` mass-source flag on rows
  where a component was never actually weighed - both are visible in the
  DPP export and the E5 report themselves, per `docs/compliance.md`.
- **Quality and safety** would ask for the AI Act classification argument
  reviewed by an actual regulatory/legal function, not just written down
  by this build - `docs/ai-act-classification.md` says exactly that.
- **IT security** would ask about the single point of privilege in account
  provisioning (a compromised supervisor can mint arbitrary roles with no
  second approval) and the frontend's open CVEs - both named in
  `docs/threat-model.md` §3.1 and §3.5, not glossed over.

## 3. Who signs off on what, before a real pilot

| Decision | Owner |
|---|---|
| Whether the AI Act classification argument is sound | Quality and safety, with legal/regulatory review |
| Whether ESRS/BRSR figures can be filed as-is or need real (not `CONFIG_ESTIMATE`) mass data first | Sustainability and reporting |
| Whether the pilot's pre-registered metrics and thresholds (`docs/pilot-protocol.md`) are acceptable | Frontline operations + the modernization business jointly - one owns the technician experience, the other owns the capacity commitment |
| Whether the identity/audit model is acceptable for a real deployment (local login vs. Entra ID, the account-provisioning gap) | IT security |
