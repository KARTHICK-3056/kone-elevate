"""Pilot metrics (P6): the numbers a pre-registered pilot commits to before
it starts - see docs/pilot-protocol.md.

    diversion rate           - share of assessed components routed away from disposal
    technician trust score   - average 1-5 one-tap rating
    mass diverted            - kg of material diverted from disposal (the ledger)

The recovered-parts yield, decision-reversal rate and value-recovered
metrics were computed from the Recovery Exchange (workshop outcomes and
accepted matches recorded on exchange listings). The exchange was removed,
so they are no longer reported rather than reported as zero.

The technician trust score needed the one-tap rating capture on
``Prediction.technician_trust_rating`` (P6), because nothing else in this
system asks a person "do you trust this" - only what they decided as a
result.

Honest scope: every number this returns describes whatever fleet is in the
database - the synthetic demo fleet today, a real pilot's data tomorrow.
Nothing about the calculation changes when the data source does.
"""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.component import Component
from app.models.material_flow import MaterialFlow
from app.models.prediction import Prediction
from app.utils.enums import DIVERTED_FROM_DISPOSAL, Recommendation


def diversion_rate(db: Session) -> Dict[str, Any]:
    """Share of currently-assessed components whose recommendation diverts them from disposal."""
    total = int(
        db.execute(
            select(func.count(Component.id)).where(Component.latest_recommendation.isnot(None))
        ).scalar_one()
    )
    diverted = int(
        db.execute(
            select(func.count(Component.id)).where(
                Component.latest_recommendation.in_(
                    [Recommendation.CONTINUE_USING.value, Recommendation.COMPONENT_RECOVERY.value, Recommendation.MATERIAL_RECOVERY.value]
                )
            )
        ).scalar_one()
    )
    return {
        "assessed_components": total,
        "diverted_components": diverted,
        "rate": round(diverted / total, 4) if total else None,
    }


def technician_trust_score(db: Session) -> Dict[str, Any]:
    ratings = [
        rating
        for rating in db.execute(
            select(Prediction.technician_trust_rating).where(
                Prediction.technician_trust_rating.isnot(None)
            )
        ).scalars().all()
    ]
    return {
        "ratings_submitted": len(ratings),
        "average_rating_1_to_5": round(sum(ratings) / len(ratings), 2) if ratings else None,
    }


def mass_diverted(db: Session) -> Dict[str, Any]:
    """kg diverted from disposal, from the material-flow ledger (see docs/compliance.md)."""
    total_kg = db.execute(
        select(func.coalesce(func.sum(MaterialFlow.mass_kg), 0.0)).where(
            MaterialFlow.outflow_route.in_(DIVERTED_FROM_DISPOSAL)
        )
    ).scalar_one()
    return {
        "mass_diverted_kg": round(float(total_kg), 2),
        "mass_diverted_tonnes": round(float(total_kg) / 1000.0, 3),
    }


def pilot_metrics(db: Session) -> Dict[str, Any]:
    return {
        "diversion_rate": diversion_rate(db),
        "technician_trust_score": technician_trust_score(db),
        "mass_diverted": mass_diverted(db),
        "data_notice": (
            "Every figure above describes whatever fleet is currently in this "
            "database - the synthetic demo fleet, unless a real pilot's data has "
            "been loaded. See docs/pilot-protocol.md."
        ),
    }
