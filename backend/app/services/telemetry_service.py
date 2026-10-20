"""Ingest readings from any sensor, controller export or monitoring system.

This is the platform's route to real usage and condition data that does not
depend on a KONE API account. Anything that can produce timestamped rows can
feed it: a retrofit IoT kit on the machine, a CSV exported from a lift
controller's event log, a building's monitoring system.

What a batch does to the component record
-----------------------------------------
* ``trips`` and ``run_seconds`` are counter *increments* since the previous
  reading. They add to ``load_cycles`` and ``operating_hours`` through the
  same per-component duty shares the KONE integration uses
  (``kone_features.APPORTIONMENT``) - a brake actuates once per trip but is
  only under load for a small share of running time.
* Car load (kg, or % of the lift's rated load) becomes the component's
  equivalent load through the same load physics as the simulation
  (``app.simulation.engine.equivalent_ratio``), and is folded into the
  component's lifetime average weighted by trips.
* The latest ``vibration`` and ``temperature`` become the component's current
  readings, and monthly averages feed the early-warning trends.

Rows are idempotent on ``(component, recorded_at, source)``: a gateway that
retries a batch - which real gateways do - cannot double-count trips.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.kone_features import APPORTIONMENT
from app.ml import life_model
from app.ml.features import reference_for
from app.models.component import Component
from app.models.telemetry import TelemetryReading
from app.services import audit_service
from app.simulation import engine
from app.simulation import reference as ref
from app.utils.enums import AuditAction
from app.utils.helpers import utcnow

MAX_BATCH = 5000
CSV_COLUMNS = ("recorded_at", "trips", "run_seconds", "load_kg", "load_percent", "vibration", "temperature")
_NUMERIC = CSV_COLUMNS[1:]
_LIMITS = {
    "trips": (0, 200_000),
    "run_seconds": (0, 31 * 86_400),
    "load_kg": (0, 5_000),
    "load_percent": (0, 150),
    "vibration": (0, 50),
    "temperature": (-40, 200),
}


class TelemetryError(ValueError):
    """A batch that cannot be accepted at all."""


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _validate_row(row: Dict[str, Any], installed: Optional[date], now: datetime) -> Optional[str]:
    """Return a rejection reason, or None if the row is acceptable."""
    when = row["recorded_at"]
    if when > now + timedelta(days=1):
        return "recorded_at is in the future"
    if installed and when.date() < installed:
        return "recorded_at is before the component was installed"
    for name, (low, high) in _LIMITS.items():
        value = row.get(name)
        if value is not None and not low <= value <= high:
            return f"{name}={value} outside {low}-{high}"
    if all(row.get(name) is None for name in _NUMERIC):
        return "no values"
    return None


def _equivalent_load(component_type: str, car_load_kg: float) -> Optional[float]:
    """Car load -> the component's equivalent load on its own rating scale."""
    if component_type not in engine.COMPONENTS:
        return None
    values = ref.reference_values()
    ratio = engine.equivalent_ratio(
        component_type, car_load_kg, values["reference_load_kg"], values["load_spread_cv"]
    )
    return life_model.reference_utilisation(component_type) * ratio * reference_for(component_type)["rated_load"]


def ingest(
    db: Session,
    component: Component,
    rows: Iterable[Dict[str, Any]],
    source: str,
    actor: str,
    rated_load_kg: float = ref.RATED_LOAD_KG,
) -> Dict[str, Any]:
    """Store a batch of readings and fold them into the component record."""
    rows = list(rows)
    if not rows:
        raise TelemetryError("The batch is empty.")
    if len(rows) > MAX_BATCH:
        raise TelemetryError(f"At most {MAX_BATCH} readings per batch.")
    source = (source or "").strip()[:48]
    if not source:
        raise TelemetryError("A source is required (e.g. 'iot-retrofit', 'controller-export').")

    now = utcnow()
    for row in rows:
        row["recorded_at"] = _naive_utc(row["recorded_at"])

    existing = set(
        db.execute(
            select(TelemetryReading.recorded_at).where(
                TelemetryReading.component_id == component.id,
                TelemetryReading.source == source,
                TelemetryReading.recorded_at >= min(r["recorded_at"] for r in rows),
                TelemetryReading.recorded_at <= max(r["recorded_at"] for r in rows),
            )
        ).scalars()
    )

    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    duplicates = 0
    seen = set()
    for index, row in enumerate(rows):
        if row["recorded_at"] in existing or row["recorded_at"] in seen:
            duplicates += 1
            continue
        reason = _validate_row(row, component.installation_date, now)
        if reason:
            rejected.append({"row": index + 1, "reason": reason})
            continue
        seen.add(row["recorded_at"])
        accepted.append(row)

    share = APPORTIONMENT.get(component.component_type, {"hours": 1.0, "cycles": 1.0})
    trips = sum(int(r.get("trips") or 0) for r in accepted)
    run_seconds = sum(float(r.get("run_seconds") or 0.0) for r in accepted)
    cycles_added = trips * float(share["cycles"])
    hours_added = run_seconds / 3600.0 * float(share["hours"])

    # Trip-weighted equivalent load for the batch.
    weighted, weight = 0.0, 0.0
    for r in accepted:
        car_kg = r.get("load_kg")
        if car_kg is None and r.get("load_percent") is not None:
            car_kg = float(r["load_percent"]) / 100.0 * rated_load_kg
        if car_kg is None:
            continue
        equivalent = _equivalent_load(component.component_type, float(car_kg))
        if equivalent is None:
            continue
        w = float(r.get("trips") or 1)
        weighted += equivalent * w
        weight += w

    updates: Dict[str, Any] = {}
    previous_cycles = float(component.load_cycles or 0)
    if cycles_added:
        component.load_cycles = int(round(previous_cycles + cycles_added))
        updates["load_cycles"] = component.load_cycles
    if hours_added:
        component.operating_hours = round(float(component.operating_hours or 0.0) + hours_added, 1)
        updates["operating_hours"] = component.operating_hours
    if weight:
        batch_load = weighted / weight
        batch_cycles = cycles_added or weight
        if previous_cycles > 0 and component.average_load:
            blended = (component.average_load * previous_cycles + batch_load * batch_cycles) / (
                previous_cycles + batch_cycles
            )
        else:
            blended = batch_load
        component.average_load = round(blended, 1)
        updates["average_load"] = component.average_load

    by_time = sorted(accepted, key=lambda r: r["recorded_at"])
    for field in ("vibration", "temperature"):
        latest = next((r[field] for r in reversed(by_time) if r.get(field) is not None), None)
        if latest is not None:
            setattr(component, field, float(latest))
            updates[field] = float(latest)

    for r in accepted:
        db.add(
            TelemetryReading(
                component_id=component.id,
                recorded_at=r["recorded_at"],
                source=source,
                trips=r.get("trips"),
                run_seconds=r.get("run_seconds"),
                load_kg=r.get("load_kg"),
                load_percent=r.get("load_percent"),
                vibration=r.get("vibration"),
                temperature=r.get("temperature"),
                received_by=actor,
            )
        )
    db.flush()

    summary = {
        "component_id": component.component_id,
        "source": source,
        "received": len(rows),
        "accepted": len(accepted),
        "duplicates_ignored": duplicates,
        "rejected": rejected[:50],
        "rejected_count": len(rejected),
        "trips_added": trips,
        "run_hours_added": round(run_seconds / 3600.0, 2),
        "component_updates": updates,
        "rated_load_kg_assumed": rated_load_kg,
        "load_applied": bool(weight),
        "load_note": (
            None if weight or component.component_type in engine.COMPONENTS
            else "Load readings stored but not applied: load physics covers motor, rope, sheave and brake."
        ),
    }
    if accepted:
        audit_service.record(
            db,
            entity_type="component",
            entity_id=component.component_id,
            action=AuditAction.TELEMETRY_INGESTED.value,
            data_snapshot={k: v for k, v in summary.items() if k != "rejected"},
            actor=actor,
        )
    db.commit()
    return summary


def parse_csv(text: str) -> Dict[str, Any]:
    """Parse a CSV export into rows; returns rows plus per-line errors."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "recorded_at" not in [f.strip() for f in reader.fieldnames]:
        raise TelemetryError(f"CSV needs a header row with recorded_at. Columns understood: {', '.join(CSV_COLUMNS)}.")
    rows, errors = [], []
    for line, raw in enumerate(reader, start=2):
        raw = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        try:
            when = datetime.fromisoformat(raw["recorded_at"].replace("Z", "+00:00"))
            row: Dict[str, Any] = {"recorded_at": when}
            for name in _NUMERIC:
                value = raw.get(name, "")
                if value != "":
                    row[name] = int(float(value)) if name == "trips" else float(value)
            rows.append(row)
        except (ValueError, KeyError) as exc:
            errors.append({"line": line, "reason": str(exc)[:120]})
        if len(rows) > MAX_BATCH:
            raise TelemetryError(f"At most {MAX_BATCH} rows per upload.")
    return {"rows": rows, "errors": errors[:50], "error_count": len(errors)}


def monthly(db: Session, component: Component, months: int = 24) -> List[Dict[str, Any]]:
    """Monthly aggregates - what the trend charts and forecasts consume."""
    since = utcnow() - timedelta(days=int(months * 30.44))
    rows = db.execute(
        select(TelemetryReading)
        .where(TelemetryReading.component_id == component.id, TelemetryReading.recorded_at >= since)
        .order_by(TelemetryReading.recorded_at)
    ).scalars().all()
    buckets: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = row.recorded_at.strftime("%Y-%m")
        for field in ("vibration", "temperature", "load_kg", "load_percent"):
            value = getattr(row, field)
            if value is not None:
                buckets[key][field].append(float(value))
        buckets[key]["trips"].append(float(row.trips or 0))
        buckets[key]["run_seconds"].append(float(row.run_seconds or 0))
    out = []
    for key in sorted(buckets):
        bucket = buckets[key]
        mean = lambda name: round(sum(bucket[name]) / len(bucket[name]), 3) if bucket.get(name) else None  # noqa: E731
        out.append(
            {
                "month": key,
                "date": f"{key}-15",
                "readings": len(bucket["trips"]),
                "trips": int(sum(bucket["trips"])),
                "run_hours": round(sum(bucket["run_seconds"]) / 3600.0, 2),
                "vibration": mean("vibration"),
                "temperature": mean("temperature"),
                "load_kg": mean("load_kg"),
                "load_percent": mean("load_percent"),
            }
        )
    return out


def forecast_points(db: Session, component: Component) -> List[Dict[str, Any]]:
    """Monthly means shaped like service-event readings, for the early-warning trends."""
    return [
        {
            "event_date": date.fromisoformat(point["date"]),
            "vibration": point["vibration"],
            "temperature": point["temperature"],
            "inspection_score": None,
        }
        for point in monthly(db, component)
        if point["vibration"] is not None or point["temperature"] is not None
    ]


def summary(db: Session, component: Component) -> Dict[str, Any]:
    """Sources, totals and monthly aggregates for the component page."""
    rows = db.execute(
        select(TelemetryReading).where(TelemetryReading.component_id == component.id)
    ).scalars().all()
    sources: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        entry = sources.setdefault(row.source, {"source": row.source, "readings": 0, "first": row.recorded_at, "last": row.recorded_at, "trips": 0})
        entry["readings"] += 1
        entry["trips"] += int(row.trips or 0)
        entry["first"] = min(entry["first"], row.recorded_at)
        entry["last"] = max(entry["last"], row.recorded_at)
    return {
        "component_id": component.component_id,
        "total_readings": len(rows),
        "sources": sorted(sources.values(), key=lambda s: s["last"], reverse=True),
        "monthly": monthly(db, component),
        "csv_columns": list(CSV_COLUMNS),
    }
