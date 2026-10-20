#!/usr/bin/env python
"""CLI wrapper: generate the synthetic degradation dataset.

Usage
-----
    python scripts/generate_data.py
    python scripts/generate_data.py --records 25000 --seed 7 --noise 1.2
    python scripts/generate_data.py --types Motor "Steel Rope" --records 4000
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.generate_dataset import main  # noqa: E402

if __name__ == "__main__":
    main()
