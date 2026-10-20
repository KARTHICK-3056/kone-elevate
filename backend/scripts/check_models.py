#!/usr/bin/env python
"""Check the committed model artefacts are usable on this machine.

The trained classifier and forecast model are committed (backend/models/) so
a new machine does not retrain. A joblib bundle is only trustworthy under the
exact scikit-learn/joblib versions that pickled it - app.ml.model_registry
refuses to load the classifier otherwise - so this checks, for each bundle,
that it exists, unpickles, and was written by the versions installed here.

Run:
    python scripts/check_models.py

Exit code: 0 when every model is present and compatible, 1 otherwise (the
setup scripts then retrain with scripts/train_model.py and
scripts/train_forecast.py).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib  # noqa: E402
import sklearn  # noqa: E402

from app.core.config import settings  # noqa: E402

MODELS = (
    ("classifier", settings.model_file, settings.metrics_file),
    ("forecast", settings.forecast_model_file, settings.forecast_metrics_file),
)


def check(name: str, model_path: Path, metrics_path: Path) -> bool:
    if not model_path.exists():
        print(f"  {name:<10} MISSING   {model_path}")
        return False
    try:
        bundle = joblib.load(model_path)
    except Exception as exc:  # corrupted file, or pickled by an incompatible version
        print(f"  {name:<10} UNREADABLE {model_path}: {exc}")
        return False

    mismatches = []
    for lib, running in (("sklearn", sklearn.__version__), ("joblib", joblib.__version__)):
        trained = bundle.get(f"{lib}_version")
        if trained and trained != running:
            mismatches.append(f"{lib} trained {trained}, installed {running}")
    if mismatches:
        print(f"  {name:<10} VERSION MISMATCH ({'; '.join(mismatches)})")
        return False

    summary = ""
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        if "accuracy" in metrics:
            summary = f", accuracy {metrics['accuracy']:.2%}"
    version, trained_at = bundle.get("model_version"), bundle.get("trained_at")
    print(f"  {name:<10} OK        {version} (trained {trained_at}{summary})")
    return True


def main() -> int:
    print("Checking model artefacts:")
    results = [check(*model) for model in MODELS]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
