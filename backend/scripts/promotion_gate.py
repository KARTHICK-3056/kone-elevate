#!/usr/bin/env python
"""Promotion gate: refuse to deploy a candidate model that regresses.

The P6 deliverable this is: "a retraining plan on real labels, with a
promotion gate." There is no real-label retraining pipeline yet - training
still runs on synthetic data either side of this comparison
(scripts/train_model.py). What is real is the gate logic itself: whatever
eventually retrains this model on real removal outcomes (see
scripts/agreement_report.py and docs/shadow-mode.md for that side of the
loop) should call this script, or logic identical to it, before a candidate
model ever reaches models/random_forest.joblib. Nothing about this file
changes when the training data does.

Usage:
    python scripts/promotion_gate.py --candidate path/to/candidate_metrics.json
    python scripts/promotion_gate.py --current models/metrics.json --candidate ...

Checks the honest metric (cohort/temporal validation), not just the random
split, alongside the headline f1_macro, the abstention rate, and average
per-class calibration (Brier score) - a candidate that is more accurate but
badly miscalibrated, or that abstains dramatically more or less than today,
does not pass just because f1_macro went up.

Exit code: 1 if the candidate fails the gate (do not promote), 0 if it
clears every check.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Maximum allowed regression per metric. "Regression" always means "worse",
# regardless of whether the metric's natural direction is up or down.
MAX_F1_MACRO_REGRESSION = 0.02
MAX_COHORT_F1_MACRO_REGRESSION = 0.03
MAX_ABSTENTION_RATE_INCREASE = 0.10
MAX_MEAN_BRIER_INCREASE = 0.02


def _load(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _mean_brier(metrics: Dict[str, Any]) -> Optional[float]:
    per_class = metrics.get("brier_score_per_class") or {}
    values = [v for v in per_class.values() if isinstance(v, (int, float))]
    return sum(values) / len(values) if values else None


def _check(
    name: str,
    current_value: Optional[float],
    candidate_value: Optional[float],
    max_regression: float,
    higher_is_better: bool,
) -> Tuple[str, str, str]:
    if current_value is None or candidate_value is None:
        return (name, "SKIPPED", "metric missing from one of the two reports")
    delta = candidate_value - current_value
    regression = -delta if higher_is_better else delta
    verdict = "PASS" if regression <= max_regression else "FAIL"
    detail = (
        f"current={current_value:.4f} candidate={candidate_value:.4f} "
        f"delta={delta:+.4f} (max allowed regression: {max_regression:.4f})"
    )
    return (name, verdict, detail)


def evaluate_gate(current: Dict[str, Any], candidate: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    return [
        _check(
            "f1_macro (random split)",
            current.get("f1_macro"),
            candidate.get("f1_macro"),
            MAX_F1_MACRO_REGRESSION,
            higher_is_better=True,
        ),
        _check(
            "f1_macro (cohort/temporal split - the honest one)",
            (current.get("cohort_validation") or {}).get("f1_macro"),
            (candidate.get("cohort_validation") or {}).get("f1_macro"),
            MAX_COHORT_F1_MACRO_REGRESSION,
            higher_is_better=True,
        ),
        _check(
            "abstention_rate",
            (current.get("abstention") or {}).get("abstention_rate"),
            (candidate.get("abstention") or {}).get("abstention_rate"),
            MAX_ABSTENTION_RATE_INCREASE,
            higher_is_better=False,
        ),
        _check(
            "mean per-class Brier score (calibration)",
            _mean_brier(current),
            _mean_brier(candidate),
            MAX_MEAN_BRIER_INCREASE,
            higher_is_better=False,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--current", default="models/metrics.json", help="Currently deployed model's metrics"
    )
    parser.add_argument("--candidate", required=True, help="Candidate model's metrics.json to evaluate")
    args = parser.parse_args()

    current = _load(args.current)
    candidate = _load(args.candidate)
    checks = evaluate_gate(current, candidate)

    print("=" * 78)
    print("MODEL PROMOTION GATE")
    print("=" * 78)
    print(f"current   : {args.current} ({current.get('model_version', 'unknown')})")
    print(f"candidate : {args.candidate} ({candidate.get('model_version', 'unknown')})")
    print("-" * 78)
    for name, verdict, detail in checks:
        print(f"[{verdict:<8}] {name}\n           {detail}")
    print("-" * 78)

    failed = [c for c in checks if c[1] == "FAIL"]
    if failed:
        print(f"PROMOTION BLOCKED - {len(failed)} check(s) failed.")
        return 1

    print("PROMOTION APPROVED - no check regressed beyond its allowed threshold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
