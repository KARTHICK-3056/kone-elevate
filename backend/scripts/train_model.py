#!/usr/bin/env python
"""CLI wrapper: train, evaluate and persist the Random Forest model.

The script generates the dataset first if it does not exist, so a fresh clone
only needs this one command to obtain a working model.

Usage
-----
    python scripts/train_model.py
    python scripts/train_model.py --regenerate --records 20000
    python scripts/train_model.py --estimators 600 --no-cv
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.train import main  # noqa: E402

if __name__ == "__main__":
    main()
