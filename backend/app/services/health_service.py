"""Transparent, explainable component health scoring (0-100).

Methodology disclosure
----------------------
PROTOTYPE HEALTH SCORE. This is a synthetic/demo scoring methodology built for
the hackathon prototype. It is a weighted, normalised degradation model whose
every term is inspectable and reproducible - but it is NOT an official KONE
engineering formula and it requires engineering validation before production
use.

How it works
------------
1. Each degradation-related reading is converted into a *ratio* against a
   type-specific design envelope (see ``app.ml.features.TYPE_REFERENCE``).
2. Ratios are clamped to a maximum of 1.25 so a single extreme reading cannot
   dominate the whole score.
3. A weighted average of the ratios produces a degradation index in [0, 1].
4. Preventive-maintenance adequacy grants a small bounded credit back.
5. ``health_score = round(100 * (1 - degradation_index))``.

The per-factor contributions are returned alongside the score so the UI can
show exactly *why* a component scored the way it did.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.ml.features import normalise_payload, reference_for
from app.utils.helpers import clamp

#: Weight of each degradation factor. Weights sum to 1.0.
FACTOR_WEIGHTS: Dict[str, float] = {
    "component_age": 0.10,
    "operating_hours": 0.14,
    "load_cycles": 0.10,
    "average_load": 0.06,
    "vibration": 0.16,
    "temperature": 0.08,
    "repair_count": 0.09,
    "failure_history": 0.09,
    "inspection_score": 0.14,
    "days_since_last_service": 0.04,
}

#: Ratios above this are treated as fully degraded for that factor.
RATIO_CEILING = 1.25

#: Denominators for count-based factors.
REPAIR_TOLERANCE = 8.0
FAILURE_TOLERANCE = 5.0
SERVICE_INTERVAL_DAYS = 730.0

#: Maximum health credit for a well-maintained component.
MAX_MAINTENANCE_CREDIT = 0.08

#: Expected preventive-maintenance visits per year of service.
EXPECTED_SERVICES_PER_YEAR = 2.0

HEALTH_BANDS = [
    (85, "EXCELLENT"),
    (70, "GOOD"),
    (55, "FAIR"),
    (35, "POOR"),
    (0, "CRITICAL"),
]

METHODOLOGY_NOTE = (
    "Prototype health score is a synthetic/demo scoring methodology and "
    "requires engineering validation before production use."
)


def _factor_ratios(payload: Dict[str, Any]) -> Dict[str, float]:
    """Convert raw readings into normalised degradation ratios."""
    ref = reference_for(payload["component_type"])
    temp_threshold = 0.6 * ref["temp_limit"]
    temp_span = max(ref["temp_limit"] - temp_threshold, 1.0)

    return {
        "component_age": payload["component_age"] / ref["design_life_years"],
        "operating_hours": payload["operating_hours"] / ref["design_hours"],
        "load_cycles": payload["load_cycles"] / ref["design_cycles"],
        "average_load": payload["average_load"] / ref["rated_load"],
        "vibration": payload["vibration"] / ref["vibration_limit"],
        "temperature": max(0.0, payload["temperature"] - temp_threshold) / temp_span,
        "repair_count": payload["repair_count"] / REPAIR_TOLERANCE,
        "failure_history": payload["failure_history"] / FAILURE_TOLERANCE,
        # Inspection score is inverted: a low score means high degradation.
        "inspection_score": (100.0 - payload["inspection_score"]) / 100.0,
        "days_since_last_service": payload["days_since_last_service"] / SERVICE_INTERVAL_DAYS,
    }


def _maintenance_credit(payload: Dict[str, Any]) -> float:
    """Bounded credit rewarding an adequate preventive-maintenance record."""
    expected = max(payload["component_age"] * EXPECTED_SERVICES_PER_YEAR, 1.0)
    adequacy = clamp(payload["service_count"] / expected, 0.0, 1.0)
    return round(MAX_MAINTENANCE_CREDIT * adequacy, 4)


def health_band(score: float) -> str:
    """Map a numeric health score to a qualitative band label."""
    for threshold, label in HEALTH_BANDS:
        if score >= threshold:
            return label
    return "CRITICAL"


def compute_health(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the health score plus a full, inspectable breakdown.

    Parameters
    ----------
    payload:
        Any dict containing the model feature names; missing values are filled
        with the documented defaults.

    Returns
    -------
    dict with keys ``health_score``, ``band``, ``degradation_index``,
    ``maintenance_credit``, ``breakdown`` and ``methodology``.
    """
    features = normalise_payload(payload)
    ratios = _factor_ratios(features)

    breakdown: List[Dict[str, Any]] = []
    degradation = 0.0
    for name, weight in FACTOR_WEIGHTS.items():
        raw_ratio = ratios[name]
        capped = clamp(raw_ratio, 0.0, RATIO_CEILING)
        contribution = weight * (capped / RATIO_CEILING)
        degradation += contribution
        breakdown.append(
            {
                "factor": name,
                "weight": weight,
                "ratio": round(raw_ratio, 4),
                "capped_ratio": round(capped, 4),
                "contribution": round(contribution, 4),
                "penalty_points": round(contribution * 100.0, 2),
            }
        )

    credit = _maintenance_credit(features)
    degradation_index = clamp(degradation - credit, 0.0, 1.0)
    score = round(100.0 * (1.0 - degradation_index), 1)

    breakdown.sort(key=lambda item: item["contribution"], reverse=True)

    return {
        "health_score": score,
        "band": health_band(score),
        "degradation_index": round(degradation_index, 4),
        "maintenance_credit": credit,
        "breakdown": breakdown,
        "methodology": METHODOLOGY_NOTE,
    }


def health_score(payload: Dict[str, Any]) -> float:
    """Convenience wrapper returning only the numeric score."""
    return compute_health(payload)["health_score"]
