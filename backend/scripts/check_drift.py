"""Feature-drift check: compare a "live" feature sample against training data.

Run:
    python scripts/check_drift.py --current data/synthetic/test.csv

There is no real live-traffic feed in this prototype, so `--current` defaults
to a held-out slice of the synthetic dataset (test.csv) purely to demonstrate
the mechanism end to end with real numbers - it is not itself evidence of
drift, since it was drawn from the same generator as the reference set.

Wiring this to production data means pointing `--current` at a CSV export of
recently-assessed component feature vectors (e.g. from
`GET /api/v1/predictions/export`, minus the label) and scheduling this script
(cron / Task Scheduler / a CI scheduled workflow) with alerting on a non-zero
exit code.

Exit code: 1 when any feature shows a "significant_shift" PSI, 0 otherwise -
so this script is CI/cron-alerting-ready as-is.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.core.alerting import post_alert  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.ml.drift import drift_report  # noqa: E402

LINE = "-" * 78


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare a feature sample against training data for drift.")
    parser.add_argument(
        "--reference",
        type=str,
        default=None,
        help="CSV of the training distribution (default: data/synthetic/train.csv)",
    )
    parser.add_argument(
        "--current",
        type=str,
        default=None,
        help=(
            "CSV of the distribution to check (default: data/synthetic/test.csv - "
            "a demo stand-in, not live data)"
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print the full report as JSON")
    args = parser.parse_args()

    dataset_dir = settings.dataset_file.parent
    reference_path = Path(args.reference) if args.reference else dataset_dir / "train.csv"
    current_path = Path(args.current) if args.current else dataset_dir / "test.csv"

    if not reference_path.exists() or not current_path.exists():
        print("Missing dataset file(s). Run scripts/generate_data.py first.", file=sys.stderr)
        sys.exit(2)

    reference = pd.read_csv(reference_path)
    current = pd.read_csv(current_path)
    report = drift_report(reference, current)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=" * 78)
        print("KONE ELEVATE - feature drift report")
        print("=" * 78)
        print(f"Reference : {reference_path} ({report['reference_records']:,} records)")
        print(f"Current   : {current_path} ({report['current_records']:,} records)")
        print(LINE)
        print(f"{'feature':<26}{'PSI':>8}{'band':>20}{'KS stat':>12}{'KS p-value':>14}")
        for row in report["numeric_features"]:
            print(
                f"{row['feature']:<26}{row['psi']:>8.4f}{row['psi_band']:>20}"
                f"{row['ks_statistic']:>12.4f}{row['ks_pvalue']:>14.6f}"
            )
        print(LINE)
        for row in report["categorical_features"]:
            print(f"{row['feature']:<26} max category share change: {row['max_abs_share_change']:.4f}")
        print(LINE)
        if report["alert"]:
            print(f"ALERT: significant shift in {report['features_with_significant_shift']}")
        elif report["features_with_moderate_shift"]:
            print(f"Moderate shift in {report['features_with_moderate_shift']} - watch, no alert yet")
        else:
            print("No significant drift detected.")
        print("=" * 78)

    if report["alert"]:
        alerted = post_alert(
            settings.DRIFT_ALERT_WEBHOOK_URL,
            {
                "system": settings.APP_NAME,
                "alert": "feature_drift_detected",
                "features_with_significant_shift": report["features_with_significant_shift"],
                "reference_records": report["reference_records"],
                "current_records": report["current_records"],
            },
        )
        if settings.DRIFT_ALERT_WEBHOOK_URL and not alerted:
            print("! DRIFT_ALERT_WEBHOOK_URL is set but the POST failed - see stderr above.", file=sys.stderr)
        elif not settings.DRIFT_ALERT_WEBHOOK_URL:
            print(
                "(DRIFT_ALERT_WEBHOOK_URL is not set - this alert was printed here only.)",
                file=sys.stderr,
            )

    sys.exit(1 if report["alert"] else 0)


if __name__ == "__main__":
    main()
