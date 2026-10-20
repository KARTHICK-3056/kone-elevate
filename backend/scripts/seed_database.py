#!/usr/bin/env python
"""Seed the database with a realistic demo portfolio.

Creates:

* five deterministic demo scenarios (healthy / moderate / heavy
  degradation, a safety-critical steel rope and a safety-critical brake with
  a worn lining),
* a further ~55 randomised but plausible components covering every type,
* service, inspection and repair history for most components,
* an AI assessment for every component,
* a complete SHA-256 audit chain covering all of the above.

Usage
-----
    python scripts/seed_database.py
    python scripts/seed_database.py --reset --components 80 --seed 7
    python scripts/seed_database.py --align-life   # adjust an existing database

Load cycles and average load are raised where needed so that no component's
projected total life exceeds its expected life (``align_life_to_design``), and
sheave usage is then scaled so projected life sits near 90% of expected
(``align_sheave_life``).
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal, create_all, drop_all  # noqa: E402
from app.ml import life_model  # noqa: E402
from app.ml.features import reference_for  # noqa: E402
from app.models.component import Component  # noqa: E402
from app.models.service_event import ServiceEvent  # noqa: E402
from app.services import (  # noqa: E402
    audit_service,
    material_flow_service,
    prediction_service,
)
from app.utils.enums import (  # noqa: E402
    AuditAction,
    ComponentType,
    LifecycleStatus,
    Recommendation,
    ServiceEventType,
)
from app.utils.helpers import new_qr_token, serialise, utcnow  # noqa: E402
from app.utils.validators import MAX_LOAD_CYCLES, MAX_OPERATING_HOURS  # noqa: E402

SEED_ACTOR = "seed-script"

LOCATIONS = [
    "Chennai, India",
    "Bengaluru, India",
    "Mumbai, India",
    "Hyderabad, India",
    "Pune, India",
    "Delhi, India",
    "Kochi, India",
    "Coimbatore, India",
    # A deliberate minority of non-India sites, so the demo data actually
    # exercises cross-country tenant scoping (app.core.tenancy) instead of
    # having every component sit in one country by accident.
    "Berlin, Germany",
    "Dubai, UAE",
]


def _location_tenant(location: str) -> tuple[str, str]:
    """Split a seeded ``"City, Country"`` string into (frontline_unit, country).

    Demo data has no separate tenant-assignment step - the location string
    already encodes both, so this keeps the two in sync by construction
    instead of maintaining a second mapping that could drift from it.
    """
    parts = [part.strip() for part in str(location).split(",")]
    city = parts[0] if parts else location
    country = parts[-1] if len(parts) > 1 else "India"
    return city, country

MANUFACTURERS = [
    "KONE MonoSpace",
    "KONE MiniSpace",
    "KONE TranSys",
    "KONE EcoDisc",
    "KONE NanoSpace",
]

ORIGINS = [
    "Chennai Plant",
    "Kunshan Plant",
    "Hyvinkaa Plant",
    "Pero Plant",
    "Giessen Plant",
]

TECHNICIANS = [
    "R. Karthik",
    "S. Meenakshi",
    "A. Ramesh",
    "P. Lakshmi",
    "V. Anand",
    "D. Fernandes",
    "J. Thomas",
]

TYPE_MATERIALS: Dict[str, List[str]] = {
    "Motor": ["Steel", "Copper"],
    "Steel Rope": ["Steel"],
    "Brake": ["Cast Iron", "Steel"],
    "Governor": ["Cast Iron", "Steel"],
    "Door Operator": ["Aluminum", "Steel", "Composite"],
    "Sheave": ["Cast Iron", "Steel"],
}


# --------------------------------------------------------------------------
# Demo scenarios (deterministic, used in the evaluator walkthrough)
# --------------------------------------------------------------------------
DEMO_SCENARIOS: List[Dict[str, Any]] = [
    {
        "label": "1. HEALTHY MOTOR",
        "expected": Recommendation.CONTINUE_USING.value,
        "component_type": "Motor",
        "material": "Steel",
        "manufacturer": "KONE EcoDisc",
        "origin": "Chennai Plant",
        "location": "Chennai, India",
        "age_years": 3.0,
        "operating_hours": 9_600,
        "load_cycles": 190_000,
        "average_load": 520,
        "vibration": 1.6,
        "temperature": 42,
        "service_count": 7,
        "repair_count": 0,
        "failure_history": 0,
        "inspection_score": 94,
        "days_since_service": 45,
        "notes": "Recently modernised shaft. Component in excellent operating condition.",
    },
    {
        "label": "2. MODERATELY DEGRADED MOTOR",
        "expected": Recommendation.COMPONENT_RECOVERY.value,
        "component_type": "Motor",
        "material": "Steel",
        "manufacturer": "KONE MonoSpace",
        "origin": "Kunshan Plant",
        "location": "Bengaluru, India",
        "age_years": 12.5,
        "operating_hours": 47_000,
        "load_cycles": 980_000,
        "average_load": 810,
        "vibration": 4.6,
        "temperature": 63,
        "service_count": 18,
        "repair_count": 2,
        "failure_history": 0,
        "inspection_score": 63,
        "days_since_service": 210,
        "notes": "Bearing noise reported. Windings sound. Candidate for component recovery at the workshop.",
    },
    {
        "label": "3. HEAVILY DEGRADED SHEAVE",
        "expected": Recommendation.MATERIAL_RECOVERY.value,
        "component_type": "Sheave",
        "material": "Cast Iron",
        "manufacturer": "KONE MiniSpace",
        "origin": "Pero Plant",
        "location": "Mumbai, India",
        "age_years": 22.0,
        "operating_hours": 78_000,
        "load_cycles": 1_500_000,
        "average_load": 1_450,
        "vibration": 5.4,
        "temperature": 68,
        "service_count": 24,
        "repair_count": 4,
        "failure_history": 1,
        "inspection_score": 42,
        "days_since_service": 420,
        "notes": "Severe groove wear beyond re-machining limits. Material recovery route.",
    },
    {
        "label": "4. SAFETY-CRITICAL STEEL ROPE",
        "expected": "SAFETY GATE (any AI output requires human inspection)",
        "component_type": "Steel Rope",
        "material": "Steel",
        "manufacturer": "KONE MonoSpace",
        "origin": "Hyvinkaa Plant",
        "location": "Chennai, India",
        "age_years": 2.2,
        "operating_hours": 8_400,
        "load_cycles": 240_000,
        "average_load": 880,
        "vibration": 1.2,
        "temperature": 33,
        "service_count": 5,
        "repair_count": 0,
        "failure_history": 0,
        "inspection_score": 95,
        "days_since_service": 28,
        "notes": "Low-hour rope in apparently excellent condition - SAFETY-CRITICAL component.",
    },
    {
        "label": "5. SAFETY-CRITICAL BRAKE, WORN LINING",
        "expected": "SAFETY GATE (any AI output requires human inspection)",
        "component_type": "Brake",
        "material": "Cast Iron",
        "manufacturer": "KONE EcoDisc",
        "origin": "Chennai Plant",
        "location": "Bengaluru, India",
        "age_years": 8.0,
        "operating_hours": 33_000,
        "load_cycles": 820_000,
        "average_load": 980,
        "vibration": 2.2,
        "temperature": 62,
        "service_count": 18,
        "repair_count": 1,
        "failure_history": 0,
        "inspection_score": 66,
        "days_since_service": 150,
        "notes": "Lining wear noted at the last visit; running warm. SAFETY-CRITICAL component.",
    },
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _component_id(component_type: str, sequence: int) -> str:
    prefix = "".join(ch for ch in component_type.upper() if ch.isalpha())[:3] or "CMP"
    return f"KE-{prefix}-{sequence:06d}"


def _serial(component_type: str, rng: random.Random) -> str:
    prefix = "".join(ch for ch in component_type.upper() if ch.isalpha())[:2]
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
    return f"{prefix}{rng.randint(10, 99)}-{''.join(rng.choices(alphabet, k=8))}"


def _build_component(
    db,
    rng: random.Random,
    sequence: int,
    spec: Dict[str, Any],
) -> Component:
    """Create one component row plus its CREATE audit entry."""
    component_type = spec["component_type"]
    install_date = date.today() - timedelta(days=int(spec["age_years"] * 365.25))
    last_service = date.today() - timedelta(days=int(spec["days_since_service"]))
    if last_service < install_date:
        last_service = install_date

    location = spec.get("location") or rng.choice(LOCATIONS)
    frontline_unit, country = _location_tenant(location)

    component = Component(
        component_id=_component_id(component_type, sequence),
        serial_number=_serial(component_type, rng),
        component_type=component_type,
        material=spec["material"],
        # A grade is recorded only when the spec supplies a real one. None
        # otherwise: the passport then shows "Not Determined" rather than a
        # grade nobody recorded.
        material_grade=spec.get("material_grade"),
        manufacturer=spec.get("manufacturer") or rng.choice(MANUFACTURERS),
        origin=spec.get("origin") or rng.choice(ORIGINS),
        installation_date=install_date,
        location=location,
        country=country,
        frontline_unit=frontline_unit,
        operating_hours=float(spec["operating_hours"]),
        load_cycles=int(spec["load_cycles"]),
        average_load=float(spec["average_load"]),
        vibration=float(spec["vibration"]),
        temperature=float(spec["temperature"]),
        service_count=int(spec["service_count"]),
        repair_count=int(spec["repair_count"]),
        failure_history=int(spec["failure_history"]),
        inspection_score=float(spec["inspection_score"]),
        last_service_date=last_service,
        current_status=spec.get("current_status", LifecycleStatus.ACTIVE.value),
        notes=spec.get("notes"),
        qr_token=new_qr_token(),
    )
    db.add(component)
    db.flush()

    seeded_status = component.current_status
    # The ledger records transitions, so a component seeded straight into a
    # non-ACTIVE state has to enter service first and then move - otherwise
    # the E5 report sees an outflow with no matching inflow.
    component.current_status = LifecycleStatus.ACTIVE.value
    audit_service.record(
        db,
        entity_type="component",
        entity_id=component.component_id,
        action=AuditAction.CREATE.value,
        data_snapshot=serialise(component),
        actor=SEED_ACTOR,
    )
    material_flow_service.record_transition(
        db,
        component,
        from_state=None,
        to_state=LifecycleStatus.ACTIVE.value,
        actor=SEED_ACTOR,
        source="seed.install",
        flow_date=install_date,
    )

    if seeded_status != LifecycleStatus.ACTIVE.value:
        component.current_status = seeded_status
        db.flush()
        material_flow_service.record_transition(
            db,
            component,
            from_state=LifecycleStatus.ACTIVE.value,
            to_state=seeded_status,
            actor=SEED_ACTOR,
            source="seed.status",
            flow_date=last_service,
        )
    return component


def _build_service_history(db, rng: random.Random, component: Component) -> int:
    """Create a plausible dated service history for a component."""
    install_date = component.installation_date
    events: List[ServiceEvent] = [
        ServiceEvent(
            component_id=component.id,
            event_type=ServiceEventType.INSTALLATION.value,
            event_date=install_date,
            technician=rng.choice(TECHNICIANS),
            description="Component installed and commissioned.",
            operating_hours=0.0,
            vibration=round(component.vibration * rng.uniform(0.25, 0.45), 2),
            temperature=round(component.temperature * rng.uniform(0.7, 0.85), 1),
            inspection_score=round(rng.uniform(96, 100), 1),
        )
    ]

    total_days = max((date.today() - install_date).days, 1)
    visits = min(component.service_count, 12)
    repairs_left = component.repair_count

    for index in range(visits):
        fraction = (index + 1) / (visits + 1)
        event_date = install_date + timedelta(days=int(total_days * fraction))
        progress = fraction

        if repairs_left > 0 and rng.random() < 0.35:
            event_type = ServiceEventType.REPAIR.value
            repairs_left -= 1
            description = rng.choice(
                [
                    "Corrective repair carried out following a fault report.",
                    "Component repaired in place; worn parts replaced.",
                    "Repair after abnormal noise/vibration was reported by the site.",
                ]
            )
        elif index == visits - 1 and rng.random() < 0.5:
            event_type = ServiceEventType.INSPECTION.value
            description = "Statutory periodic inspection completed."
        else:
            event_type = rng.choice(
                [ServiceEventType.MAINTENANCE.value, ServiceEventType.INSPECTION.value]
            )
            description = rng.choice(
                [
                    "Scheduled preventive maintenance: cleaning, lubrication, torque check.",
                    "Condition monitoring visit; readings recorded.",
                    "Routine inspection, no critical findings.",
                    "Adjustment and alignment check performed.",
                ]
            )

        events.append(
            ServiceEvent(
                component_id=component.id,
                event_type=event_type,
                event_date=event_date,
                technician=rng.choice(TECHNICIANS),
                description=description,
                operating_hours=round(component.operating_hours * progress, 1),
                vibration=round(
                    component.vibration * (0.35 + 0.7 * progress) * rng.uniform(0.9, 1.1), 2
                ),
                temperature=round(
                    component.temperature * (0.8 + 0.22 * progress) * rng.uniform(0.95, 1.05), 1
                ),
                inspection_score=round(
                    min(100.0, max(0.0, 100 - (100 - component.inspection_score) * progress
                                   + rng.uniform(-4, 4))),
                    1,
                ),
            )
        )

    if component.current_status in (
        LifecycleStatus.REMOVED.value,
        LifecycleStatus.RECOVERED.value,
    ):
        events.append(
            ServiceEvent(
                component_id=component.id,
                event_type=ServiceEventType.REMOVAL.value,
                event_date=component.last_service_date or date.today(),
                technician=rng.choice(TECHNICIANS),
                description="Component removed during modernisation and sent for assessment.",
                operating_hours=component.operating_hours,
                vibration=component.vibration,
                temperature=component.temperature,
                inspection_score=component.inspection_score,
            )
        )

    for event in events:
        db.add(event)
    db.flush()

    audit_service.record(
        db,
        entity_type="component",
        entity_id=component.component_id,
        action=AuditAction.SERVICE_EVENT.value,
        data_snapshot={
            "seeded_events": len(events),
            "first_event": events[0].event_date.isoformat(),
            "last_event": events[-1].event_date.isoformat(),
        },
        actor=SEED_ACTOR,
    )
    return len(events)


def _random_spec(rng: random.Random, component_type: Optional[str] = None) -> Dict[str, Any]:
    """Generate a plausible component specification with correlated wear."""
    component_type = component_type or rng.choice(ComponentType.values())
    ref = reference_for(component_type)
    material = rng.choice(TYPE_MATERIALS[component_type])

    design_life = ref["design_life_years"]
    age = round(rng.uniform(0.5, design_life * 1.35), 1)
    duty = rng.uniform(0.5, 1.7)

    annual_hours = ref["design_hours"] / design_life
    annual_cycles = ref["design_cycles"] / design_life
    operating_hours = round(age * annual_hours * duty * rng.uniform(0.85, 1.15), 0)
    load_cycles = int(age * annual_cycles * duty * rng.uniform(0.8, 1.2))

    wear = min(1.25, (operating_hours / ref["design_hours"]) * 0.65 + (age / design_life) * 0.35)
    wear = min(1.25, max(0.0, wear + rng.uniform(-0.12, 0.12)))

    maintenance_quality = rng.uniform(0.35, 1.0)

    return {
        "component_type": component_type,
        "material": material,
        "manufacturer": rng.choice(MANUFACTURERS),
        "origin": rng.choice(ORIGINS),
        "location": rng.choice(LOCATIONS),
        "age_years": age,
        "operating_hours": max(operating_hours, 10),
        "load_cycles": max(load_cycles, 100),
        "average_load": round(ref["rated_load"] * rng.uniform(0.35, 0.85), 1),
        "vibration": round(
            max(0.1, ref["vibration_limit"] * (0.22 + 0.95 * wear) * rng.uniform(0.85, 1.15)), 2
        ),
        "temperature": round(26 + (ref["temp_limit"] - 28) * (0.2 + 0.6 * wear), 1),
        "service_count": int(max(0, age * 2 * maintenance_quality)),
        "repair_count": int(max(0, age * 0.10 * (0.4 + 2.0 * wear))),
        "failure_history": int(max(0, wear * 2.0 * rng.random())),
        "inspection_score": round(min(100, max(2, 100 - 78 * wear + rng.uniform(-7, 7))), 1),
        "days_since_service": int(max(5, rng.expovariate(1 / (190 / maintenance_quality)))),
        "notes": None,
    }


# --------------------------------------------------------------------------
# Life alignment - projected total life never above expected life
# --------------------------------------------------------------------------
#: Load cycles and average load are scaled up together in steps of this size.
_ALIGN_STEP = 1.05
_ALIGN_MAX_SCALE = 40.0
#: Sheaves are traction-critical cast/forged parts with long design lives; a
#: demo sheave projecting far short of its grade's life reads as a low-grade
#: part. Their usage is scaled so projected total life lands near this share
#: of expected life (never above it).
SHEAVE_LIFE_TARGET = 0.90


def _life_fits(component: Component, today: date) -> bool:
    """Projected total life within expected life, today and a year from now.

    The year-ahead check keeps it true as the demo data ages: the counters are
    static, so the annual duty they imply falls as calendar age grows.
    """
    for when in (today, today + timedelta(days=365)):
        result = life_model.assess(component, today=when)
        if not result.get("available"):
            return True
        if result["projection"]["projected_total_life_years"] > result["design_life_years"]:
            return False
    return True


def align_life_to_design(db, component: Component, actor: str = SEED_ACTOR) -> Optional[Dict[str, Any]]:
    """Raise load cycles and average load until projected total life <= expected life.

    Both are scaled by the same factor from their stored values (average load
    capped at the type's rated load). Operating hours are left alone. Returns
    the audited changes, or None when the component already fits.
    """
    # Service history may have been added after the relationship was loaded.
    db.expire(component, ["service_events"])
    today = utcnow().date()
    if _life_fits(component, today):
        return None
    cycles, load = component.load_cycles, component.average_load
    rated = reference_for(component.component_type)["rated_load"]
    scale = 1.0
    while scale < _ALIGN_MAX_SCALE:
        scale *= _ALIGN_STEP
        component.load_cycles = min(int(round(cycles * scale)), MAX_LOAD_CYCLES)
        component.average_load = round(min(load * scale, rated), 1)
        if _life_fits(component, today):
            break
    changes = {
        "load_cycles": {"from": cycles, "to": component.load_cycles},
        "average_load": {"from": load, "to": component.average_load},
    }
    audit_service.record(
        db,
        entity_type="component",
        entity_id=component.component_id,
        action=AuditAction.UPDATE.value,
        data_snapshot={"changes": changes, "state": serialise(component)},
        actor=actor,
    )
    return {**changes, "fits": _life_fits(component, today)}


def align_sheave_life(db, component: Component, actor: str = SEED_ACTOR) -> Optional[Dict[str, Any]]:
    """Scale a sheave's load cycles and operating hours so its projected total
    life sits near ``SHEAVE_LIFE_TARGET`` of its expected life, never above it.

    Both counters are scaled by one factor from their stored values, searched
    on a 0.01 grid. Returns the audited changes, or None for other types or
    when the stored values are already the closest fit.
    """
    if component.component_type != ComponentType.SHEAVE.value:
        return None
    db.expire(component, ["service_events"])
    today = utcnow().date()
    cycles, hours = component.load_cycles, component.operating_hours

    def projected() -> Optional[tuple[float, float]]:
        result = life_model.assess(component, today=today)
        if not result.get("available"):
            return None
        return result["projection"]["projected_total_life_years"], result["design_life_years"]

    best: Optional[tuple[float, float]] = None
    for step in range(30, 201):
        scale = step / 100
        component.load_cycles = min(int(round(cycles * scale)), MAX_LOAD_CYCLES)
        component.operating_hours = min(round(hours * scale), MAX_OPERATING_HOURS)
        fit = projected()
        if fit is None:
            break
        total, expected = fit
        if total > expected:
            continue
        miss = abs(total / expected - SHEAVE_LIFE_TARGET)
        if best is None or miss < best[0]:
            best = (miss, scale)
    if best is None or best[1] == 1.0:
        component.load_cycles, component.operating_hours = cycles, hours
        return None
    scale = best[1]
    component.load_cycles = min(int(round(cycles * scale)), MAX_LOAD_CYCLES)
    component.operating_hours = min(round(hours * scale), MAX_OPERATING_HOURS)
    changes = {
        "load_cycles": {"from": cycles, "to": component.load_cycles},
        "operating_hours": {"from": hours, "to": component.operating_hours},
    }
    audit_service.record(
        db,
        entity_type="component",
        entity_id=component.component_id,
        action=AuditAction.UPDATE.value,
        data_snapshot={"changes": changes, "state": serialise(component)},
        actor=actor,
    )
    total, expected = projected()
    return {**changes, "projected_total_life_years": total, "design_life_years": expected}


def align_existing(quiet: bool = False) -> List[Dict[str, Any]]:
    """Apply :func:`align_life_to_design`, then :func:`align_sheave_life`, to an
    already-seeded database.

    Each changed component is re-assessed so its AI assessment reflects the
    new usage figures.
    """
    db = SessionLocal()
    report: List[Dict[str, Any]] = []
    sheave_report: List[Dict[str, Any]] = []
    try:
        for component in db.execute(select(Component)).scalars().all():
            changes = align_life_to_design(db, component)
            sheave = align_sheave_life(db, component)
            if changes is None and sheave is None:
                continue
            prediction_service.assess_component(db, component, actor=SEED_ACTOR, commit=False)
            if changes is not None:
                report.append({"component_id": component.component_id, **changes})
            if sheave is not None:
                sheave_report.append({"component_id": component.component_id, **sheave})
        db.commit()
        if not quiet:
            for row in report:
                print(
                    f"{row['component_id']:<14} load_cycles {row['load_cycles']['from']:>9,} -> "
                    f"{row['load_cycles']['to']:>9,}  average_load {row['average_load']['from']:>7,.1f} -> "
                    f"{row['average_load']['to']:>7,.1f}{'' if row['fits'] else '  (still above expected)'}"
                )
            for row in sheave_report:
                print(
                    f"{row['component_id']:<14} load_cycles {row['load_cycles']['from']:>9,} -> "
                    f"{row['load_cycles']['to']:>9,}  operating_hours {row['operating_hours']['from']:>8,.0f} -> "
                    f"{row['operating_hours']['to']:>8,.0f}  projected {row['projected_total_life_years']:.1f} "
                    f"of {row['design_life_years']:.1f} yr"
                )
            print(
                f"{len(report)} components adjusted, {len(sheave_report)} sheaves aligned; "
                f"audit chain valid={audit_service.verify_chain(db)['valid']}"
            )
        return report
    finally:
        db.close()


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------
def seed(
    n_components: int = 60,
    seed_value: int = 42,
    reset: bool = False,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Populate the database and return a summary of what was created."""

    def say(message: str = "") -> None:
        if not quiet:
            print(message)

    rng = random.Random(seed_value)

    if reset:
        say("Dropping existing tables ...")
        drop_all()
    create_all()

    db = SessionLocal()
    summary: Dict[str, Any] = {
        "components": 0,
        "service_events": 0,
        "predictions": 0,
        "demo": [],
    }

    try:
        existing = db.execute(select(Component.id).limit(1)).first()
        if existing and not reset:
            say("Database already contains components. Use --reset to rebuild.")
            return summary

        say("=" * 70)
        say("KONE ELEVATE - seeding demo portfolio")
        say("=" * 70)

        sequence: Dict[str, int] = {}
        components: List[Component] = []

        # -- 1. deterministic demo scenarios -----------------------------
        say("\n[1/3] Creating demo scenarios ...")
        demo_components: List[tuple[Dict[str, Any], Component]] = []
        for scenario in DEMO_SCENARIOS:
            component_type = scenario["component_type"]
            sequence[component_type] = sequence.get(component_type, 0) + 1
            component = _build_component(db, rng, sequence[component_type], scenario)
            components.append(component)
            demo_components.append((scenario, component))
            summary["service_events"] += _build_service_history(db, rng, component)
            align_life_to_design(db, component)
            align_sheave_life(db, component)
        say(f"      {len(demo_components)} demo components created.")

        # -- 2. randomised portfolio -------------------------------------
        remaining = max(n_components - len(DEMO_SCENARIOS), 0)
        say(f"\n[2/3] Creating {remaining} portfolio components ...")
        all_types = ComponentType.values()
        for index in range(remaining):
            # Guarantee full type coverage before going random.
            component_type = all_types[index] if index < len(all_types) else None
            spec = _random_spec(rng, component_type)

            roll = rng.random()
            if roll < 0.18:
                spec["current_status"] = LifecycleStatus.REMOVED.value
            elif roll < 0.24:
                spec["current_status"] = LifecycleStatus.UNDER_INSPECTION.value
            elif roll < 0.28:
                spec["current_status"] = LifecycleStatus.PART_RECOVERY.value

            sequence[spec["component_type"]] = sequence.get(spec["component_type"], 0) + 1
            component = _build_component(db, rng, sequence[spec["component_type"]], spec)
            components.append(component)
            summary["service_events"] += _build_service_history(db, rng, component)
            align_life_to_design(db, component)
            align_sheave_life(db, component)

        summary["components"] = len(components)
        db.commit()
        say(f"      {len(components)} components total, {summary['service_events']} service events.")

        # -- 3. AI assessments -------------------------------------------
        say("\n[3/3] Running AI assessments ...")
        outcomes: Dict[str, int] = {}
        for component in components:
            _, result = prediction_service.assess_component(
                db, component, actor=SEED_ACTOR, commit=False
            )
            outcomes[result["recommendation"]] = outcomes.get(result["recommendation"], 0) + 1
            summary["predictions"] += 1
        db.commit()
        for label in Recommendation.values():
            say(f"      {label:<10} {outcomes.get(label, 0):>3}")

        # -- demo scenario report -----------------------------------------
        for scenario, component in demo_components:
            latest = prediction_service.latest(db, component)
            summary["demo"].append(
                {
                    "label": scenario["label"],
                    "component_id": component.component_id,
                    "component_type": component.component_type,
                    "expected": scenario["expected"],
                    "actual": latest.recommendation if latest else None,
                    "confidence": latest.confidence if latest else None,
                    "health_score": latest.health_score if latest else None,
                    "safety_flag": bool(latest.safety_flag) if latest else False,
                }
            )

        verification = audit_service.verify_chain(db)
        summary["audit"] = verification

        say("\n" + "=" * 70)
        say("DEMO SCENARIOS")
        say("=" * 70)
        for entry in summary["demo"]:
            say(f"{entry['label']}")
            say(f"    Component     : {entry['component_id']} ({entry['component_type']})")
            say(f"    Expected      : {entry['expected']}")
            say(
                f"    AI assessment : {entry['actual']} "
                f"(confidence {entry['confidence']:.2f}, health {entry['health_score']})"
            )
            if entry["safety_flag"]:
                say("    SAFETY GATE   : MANDATORY HUMAN INSPECTION")
            say("")

        say("=" * 70)
        say("SEED SUMMARY")
        say("=" * 70)
        say(f"Components      : {summary['components']}")
        say(f"Service events  : {summary['service_events']}")
        say(f"AI assessments  : {summary['predictions']}")
        say(
            f"Audit chain     : {verification['records_checked']} records, "
            f"valid={verification['valid']}"
        )
        say("=" * 70)
        say("Data disclosure: all component data above is SYNTHETIC demo data.")
        say("=" * 70)

        return summary
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the KONE ELEVATE demo database.")
    parser.add_argument("--components", type=int, default=60, help="Total components to create")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables first")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--align-life",
        action="store_true",
        help="Adjust an existing database so no projected total life exceeds its expected life",
    )
    args = parser.parse_args()

    if args.align_life:
        align_existing(quiet=args.quiet)
        return

    seed(
        n_components=args.components,
        seed_value=args.seed,
        reset=args.reset,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()
