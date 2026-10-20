"""Train the end-of-life forecaster (Weibull AFT) and publish its backtest.

Run:  python scripts/train_forecast.py
      python scripts/train_forecast.py --regenerate --records 20000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.forecast_train import (  # noqa: E402
    format_forecast_report,
    load_or_generate_survival,
    train_forecast_model,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the KONE ELEVATE end-of-life forecaster.")
    parser.add_argument("--records", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--regenerate", action="store_true", help="Force dataset regeneration")
    args = parser.parse_args()

    metrics = train_forecast_model(
        n_records=args.records,
        seed=args.seed,
        test_size=args.test_size,
        regenerate=args.regenerate,
    )
    frame, _ = load_or_generate_survival(n_records=args.records, seed=args.seed)
    print(format_forecast_report(metrics, frame))


if __name__ == "__main__":
    main()
