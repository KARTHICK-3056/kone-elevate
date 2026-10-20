"""Reference sensor gateway: push readings from a CSV to the platform.

This is what the edge side of a real deployment looks like, kept to the
standard library so it runs on a small gateway box (a Raspberry Pi next to
the lift controller, say). It reads rows - from a controller's CSV export,
or a file a sensor logger appends to - and POSTs them in batches to
``/components/{id}/telemetry``.

Retries are safe: the platform ignores a reading it has already stored
(same component, timestamp and source), so a batch that timed out can simply
be sent again. That is the property a real gateway on a flaky machine-room
connection needs.

Usage::

    set KE_API_URL=http://localhost:8000/api/v1
    set KE_TOKEN=<an access token for a technician account>
    python scripts/telemetry_gateway.py KE-MOT-000003 readings.csv --source iot-retrofit

CSV columns: recorded_at, trips, run_seconds, load_kg, load_percent,
vibration, temperature (any subset besides recorded_at).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

NUMERIC = ("trips", "run_seconds", "load_kg", "load_percent", "vibration", "temperature")


def read_rows(path: str) -> List[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = []
        for raw in csv.DictReader(handle):
            row: Dict[str, Any] = {"recorded_at": raw["recorded_at"].strip()}
            for name in NUMERIC:
                value = (raw.get(name) or "").strip()
                if value:
                    row[name] = int(float(value)) if name == "trips" else float(value)
            rows.append(row)
        return rows


def post(url: str, token: str, body: Dict[str, Any], attempts: int = 4) -> Dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code < 500:  # a request the server refused will not improve by retrying
                raise SystemExit(f"Rejected ({exc.code}): {exc.read().decode(errors='replace')}")
        except urllib.error.URLError as exc:
            print(f"  attempt {attempt} failed: {exc.reason}", file=sys.stderr)
        time.sleep(2 ** attempt)  # back off, then resend the same batch - it is idempotent
    raise SystemExit("Giving up after repeated failures; re-run later, nothing will be double-counted.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("component_id")
    parser.add_argument("csv_path")
    parser.add_argument("--source", default="iot-retrofit")
    parser.add_argument("--rated-load-kg", type=float, default=1000.0)
    parser.add_argument("--batch", type=int, default=500)
    args = parser.parse_args()

    base = os.environ.get("KE_API_URL", "http://localhost:8000/api/v1").rstrip("/")
    token = os.environ.get("KE_TOKEN")
    if not token:
        raise SystemExit("Set KE_TOKEN to an access token (sign in via /auth/login).")

    rows = read_rows(args.csv_path)
    url = f"{base}/components/{args.component_id}/telemetry"
    totals = {"accepted": 0, "duplicates_ignored": 0, "rejected_count": 0}
    for start in range(0, len(rows), args.batch):
        batch = rows[start : start + args.batch]
        result = post(url, token, {"source": args.source, "rated_load_kg": args.rated_load_kg, "readings": batch})
        for key in totals:
            totals[key] += int(result.get(key, 0))
        print(f"rows {start + 1}-{start + len(batch)}: {result['accepted']} accepted, "
              f"{result['duplicates_ignored']} duplicate, {result['rejected_count']} rejected")
    print(f"Done: {totals}")


if __name__ == "__main__":
    main()
