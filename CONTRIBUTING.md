# Contributing

## Branching

- `main` is protected: no direct pushes, merges only through a reviewed pull request with a green CI run.
- Branch names: `<type>/<short-description>`, e.g. `feat/calibration-endpoint`, `fix/audit-chain-race`, `docs/model-card`.
- Rebase (don't merge `main` in) to keep history linear before opening a PR.

## Commits

Conventional Commits, imperative mood, one logical change per commit:

```
<type>(<scope>): <summary>

[optional body: why, not what]
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `perf`. Scope is the
touched area (`ml`, `api`, `audit`, `frontend`, `docs`, ...). Example:

```
feat(ml): add isotonic calibration to the disposition model

CalibratedClassifierCV wraps the Random Forest so predict_proba values are
reliability-diagram-accurate rather than raw vote fractions.
```

## Pull requests

- Keep PRs scoped to one phase deliverable from `plan.md` where possible.
- Every PR must pass CI (`.github/workflows/ci.yml`): ruff, pytest with the
  coverage floor, vitest, `vite build`, and both Docker builds.
- Describe *why*, not just *what* - link the `plan.md` checklist item(s) the PR
  closes.
- No secrets, `.env` files, or generated model/dataset artefacts in a diff
  (`.gitignore` already excludes `backend/models/*.joblib`,
  `backend/data/synthetic/*.csv`, and `.env`).

## Review

- At least one approving review before merge.
- A reviewer should be able to answer, from the PR description alone: what
  changed, why, and how it was verified (tests run, screenshots for UI
  changes, `derive_impact_claims.py` output for anything touching impact
  figures).

## Local setup

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate   # .venv/bin/activate on macOS/Linux
pip install -r requirements.lock
python scripts/generate_data.py
python scripts/train_model.py
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

Run the full local check before pushing:

```bash
cd backend && ruff check . && pytest --cov=app --cov-fail-under=70
cd ../frontend && npm run lint && npm test && npm run build
```
