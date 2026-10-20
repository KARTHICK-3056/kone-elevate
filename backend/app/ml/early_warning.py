"""Pre-emptive issue forecast: predict a problem before it arrives.

The question this answers
-------------------------
Everything else in the assessment describes the component **as it is**: its
disposition, its health score, how much life it has used. The mentor review
asked for the opposite direction - *pre*-analysis rather than post-analysis:

    Which specific problem is this component heading towards, roughly when
    will it arrive, what should a technician do before then, and why do we
    believe it?

How a prediction is made
------------------------
Two kinds of forward-looking signal, each tied to a named failure mode of the
component type (:data:`FAILURE_MODES`):

1. **Condition trends (leading indicators).** Vibration, temperature and
   inspection score are recorded at every service visit. A least-squares line
   through the recent readings is extrapolated to the indicator's limit; the
   crossing date is the predicted arrival of the issue. This is the classic
   P-F interval idea from reliability-centred maintenance: a defect becomes
   detectable (P) well before it becomes a functional failure (F), and the
   trend is what makes it detectable.
2. **Usage-adjusted life** from :mod:`app.ml.life_model` - the date the part
   enters the replace band at its current rate of use.

Why we believe it - justification
---------------------------------
A single extrapolated line is weak evidence. Each issue is therefore checked
against signals that were produced **independently** of the trend:

* the usage-based life model (physics-of-failure, no condition data),
* the survival model's probability of no longer being suitable for its
  current application within a year (statistical, fitted on the fleet),
* the AI classifier's own verdict on the current snapshot,
* the component's recorded repairs and failures.

Confidence rises with the quality of the trend fit and with how many of those
independent signals agree. Every signal is returned with its reading and
whether it agreed, so a technician can see exactly why a warning was raised -
and argue with it.

Measures are timed by lead time: a warning is only useful if the part and the
visit can be arranged before the predicted date, so every issue carries an
``act_by`` date = predicted date minus the type's planning/procurement lead
time.

PROTOTYPE VALUES
----------------
Limits, lead times and confidence weights are documented prototype choices,
not KONE specifications. The service history the trends are fitted on is
synthetic in this build. See ``docs/early-warning.md``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

from app.ml import life_model
from app.ml.features import reference_for
from app.utils.enums import ComponentType, Recommendation, is_safety_critical, recommendation_label
from app.utils.helpers import utcnow

#: How far ahead issues are reported. Beyond this an extrapolated line says
#: very little, and a warning three years out is not actionable.
HORIZON_YEARS = 3.0

#: Trend fitting needs enough history to be more than a line through noise.
MIN_TREND_POINTS = 3
MIN_TREND_SPAN_DAYS = 180
MAX_TREND_POINTS = 8
#: A trend must move at least this share of the indicator's limit per year.
MIN_SLOPE_FRACTION = 0.01

#: Inspection score at which a component enters the replace band - the same
#: mapping the life model uses (100 - 0.8 x 65).
INSPECTION_LIMIT = 100.0 - life_model.REPLACE_LIMIT * 65.0

#: Days needed to plan the visit and source the part, per type. PROTOTYPE.
LEAD_TIME_DAYS: Dict[str, int] = {
    ComponentType.MOTOR.value: 90,
    ComponentType.STEEL_ROPE.value: 60,
    ComponentType.SHEAVE.value: 75,
    ComponentType.BRAKE.value: 45,
    ComponentType.GOVERNOR.value: 60,
    ComponentType.DOOR_OPERATOR.value: 30,
}

#: Probability within 12 months above which the survival model is counted as
#: agreeing that a problem is coming.
SURVIVAL_AGREES_AT = 0.3

#: AI verdicts that corroborate an approaching issue.
_CONCERNED_RECOMMENDATIONS = {
    Recommendation.COMPONENT_RECOVERY.value,
    Recommendation.MATERIAL_RECOVERY.value,
    Recommendation.DISPOSE.value,
    Recommendation.DEFER_TO_INSPECTION.value,
}

#: The condition indicators tracked at each service visit.
INDICATORS: Dict[str, Dict[str, Any]] = {
    "vibration": {"label": "Vibration", "unit": "mm/s", "worsens": "rising"},
    "temperature": {"label": "Operating temperature", "unit": "C", "worsens": "rising"},
    "inspection_score": {"label": "Inspection score", "unit": "/100", "worsens": "falling"},
}


def _mode(code: str, title: str, mechanism: str, measures: List[str]) -> Dict[str, Any]:
    return {"code": code, "title": title, "mechanism": mechanism, "measures": measures}


#: Which issue each indicator foreshadows, per component type, and what to do
#: about it before it arrives. ``life`` is the usage-adjusted life milestone.
FAILURE_MODES: Dict[str, Dict[str, Dict[str, Any]]] = {
    ComponentType.MOTOR.value: {
        "vibration": _mode(
            "MOTOR_BEARING_WEAR",
            "Bearing wear / shaft misalignment",
            "Rising vibration is the earliest detectable sign of bearing distress or misalignment.",
            [
                "Take a vibration spectrum reading at the next visit to confirm a bearing defect frequency",
                "Check shaft alignment and machine mounting bolts",
                "Re-grease or replace bearings; order the bearing set now",
            ],
        ),
        "temperature": _mode(
            "MOTOR_INSULATION_OVERHEAT",
            "Winding insulation over-temperature",
            "Insulation life halves for every ~10 K of extra heat; a rising trend eats life fast.",
            [
                "Run an insulation-resistance (megger) test",
                "Clean cooling paths / fan and check machine-room ventilation",
                "Compare motor current against rated to rule out overload",
            ],
        ),
        "inspection_score": _mode(
            "MOTOR_CONDITION_DECLINE",
            "General condition decline",
            "Inspection scores have been falling visit on visit.",
            [
                "Schedule a full machine inspection (bearings, encoder, brake interface)",
                "Plan in-service maintenance: bearing replacement / re-varnish",
            ],
        ),
        "life": _mode(
            "MOTOR_END_OF_LIFE",
            "Motor reaching end of usage-adjusted life",
            "At the current rate of use the machine enters the replace band.",
            [
                "Budget a rewind or replacement and order the spare",
                "Book the modernisation window with the building owner",
            ],
        ),
    },
    ComponentType.STEEL_ROPE.value: {
        "inspection_score": _mode(
            "ROPE_DISCARD_CRITERIA",
            "Rope approaching discard criteria",
            "Falling inspection scores precede broken-wire counts and diameter loss reaching ISO 4344 discard limits.",
            [
                "Measure rope diameter at the most-used section against nominal",
                "Count visible broken wires per reference length (ISO 4344)",
                "Lubricate; order a replacement rope set now (ropes are replaced as a set)",
            ],
        ),
        "vibration": _mode(
            "ROPE_TENSION_IMBALANCE",
            "Uneven rope tension / traction irregularity",
            "Rising ride vibration often means ropes are sharing load unequally.",
            [
                "Measure and equalise rope tensions",
                "Check for rope slip marks on the traction sheave",
            ],
        ),
        "life": _mode(
            "ROPE_END_OF_LIFE",
            "Rope set reaching end of usage-adjusted life",
            "At the current rate of use the ropes enter the replace band.",
            ["Order the replacement rope set", "Schedule the rope change with the building owner"],
        ),
    },
    ComponentType.SHEAVE.value: {
        "vibration": _mode(
            "SHEAVE_GROOVE_WEAR",
            "Groove wear / sheave misalignment",
            "Rising vibration indicates uneven groove wear or a misaligned sheave.",
            [
                "Gauge the groove profile on every groove",
                "Check sheave alignment and rope slip",
                "Plan re-grooving before undercut reduces traction",
            ],
        ),
        "inspection_score": _mode(
            "SHEAVE_GROOVE_PROFILE",
            "Groove profile worn beyond gauge",
            "Falling inspection scores track groove profile loss.",
            ["Gauge groove depth differences between grooves", "Plan re-machining or replacement"],
        ),
        "life": _mode(
            "SHEAVE_END_OF_LIFE",
            "Sheave reaching end of usage-adjusted life",
            "At the current rate of use the sheave enters the replace band.",
            ["Order a replacement sheave; replace ropes at the same visit if they are also due"],
        ),
    },
    ComponentType.BRAKE.value: {
        "temperature": _mode(
            "BRAKE_LINING_OVERHEAT",
            "Lining overheating / brake fade",
            "A rising brake temperature means more energy per stop or a dragging brake - both wear the lining fast.",
            [
                "Measure lining thickness and air gap",
                "Check that the brake fully releases (no drag)",
                "Order a lining / pad set",
            ],
        ),
        "inspection_score": _mode(
            "BRAKE_LINING_WEAR",
            "Lining wear approaching minimum thickness",
            "Falling inspection scores precede lining thickness reaching its minimum.",
            [
                "Measure lining thickness and reset the air gap",
                "Test brake torque",
                "Order a lining set",
            ],
        ),
        "life": _mode(
            "BRAKE_END_OF_LIFE",
            "Brake reaching end of usage-adjusted life",
            "At the current rate of use the brake enters the replace band.",
            ["Plan re-lining or brake replacement", "Replace the spring set at the same visit"],
        ),
    },
    ComponentType.GOVERNOR.value: {
        "vibration": _mode(
            "GOVERNOR_BEARING_WEAR",
            "Governor bearing or pivot wear",
            "Rising vibration at the governor points to bearing wear or a worn groove letting the "
            "rope run unevenly - both shift the tripping speed.",
            [
                "Check governor bearings and sheave run-out",
                "Measure groove wear against the rope",
                "Bring the periodic tripping-speed test forward",
            ],
        ),
        "inspection_score": _mode(
            "GOVERNOR_TRIP_DRIFT",
            "Tripping mechanism drifting out of tolerance",
            "Falling inspection scores - sticky pivots, relaxed springs, groove wear - precede a "
            "tripping speed outside tolerance at the periodic test.",
            [
                "Run the tripping-speed test and the rope-pull test",
                "Clean and lubricate pivots; replace relaxed springs",
                "Order a governor overhaul kit or spare governor",
            ],
        ),
        "life": _mode(
            "GOVERNOR_END_OF_LIFE",
            "Governor reaching end of usage-adjusted life",
            "At the current rate of use the governor enters the replace band.",
            ["Plan governor replacement", "Replace the governor rope at the same visit if it is also due"],
        ),
    },
    ComponentType.DOOR_OPERATOR.value: {
        "vibration": _mode(
            "DOOR_ROLLER_WEAR",
            "Hanger roller and track wear",
            "Rising vibration on the door operator means flat-spotted rollers, a worn track or a "
            "loose belt - the usual cause of noisy, slow or re-opening doors.",
            [
                "Inspect hanger rollers and the track surface",
                "Check belt tension and pulley alignment",
                "Order a roller and belt kit",
            ],
        ),
        "inspection_score": _mode(
            "DOOR_FAULT_TREND",
            "Rising door fault trend",
            "Falling inspection scores - reversals, lock contact wear, closing force drift - "
            "precede door faults, the most common cause of lift call-outs.",
            [
                "Download the door controller fault log",
                "Measure closing force and kinetic energy (EN 81-20)",
                "Clean and adjust the door lock and contacts",
            ],
        ),
        "life": _mode(
            "DOOR_OPERATOR_END_OF_LIFE",
            "Door operator reaching end of usage-adjusted life",
            "At the current number of door cycles the operator enters the replace band.",
            ["Order a replacement door operator", "Book the replacement with the building owner"],
        ),
    },
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _limit(indicator: str, component_type: str) -> float:
    ref = reference_for(component_type)
    if indicator == "vibration":
        return float(ref["vibration_limit"])
    if indicator == "temperature":
        return float(ref["temp_limit"])
    return INSPECTION_LIMIT


def _series(component: Any, events: Iterable[Any], indicator: str) -> List[tuple]:
    """Dated readings of one indicator: service events plus the current reading."""
    points: Dict[date, float] = {}
    for event in events:
        value = _get(event, indicator)
        when = _get(event, "event_date")
        if value is not None and when is not None:
            points[when] = float(value)
    current = _get(component, indicator)
    stamped = _get(component, "last_service_date")
    if current is not None and stamped is not None and stamped not in points:
        points[stamped] = float(current)
    return sorted(points.items())[-MAX_TREND_POINTS:]


def _fit(points: Sequence[tuple], today: date) -> Optional[Dict[str, float]]:
    """Least-squares line through (years-ago, value); None if too little history."""
    if len(points) < MIN_TREND_POINTS:
        return None
    if (points[-1][0] - points[0][0]).days < MIN_TREND_SPAN_DAYS:
        return None
    x = np.array([(when - today).days / 365.25 for when, _ in points])
    y = np.array([value for _, value in points])
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    total = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - float(np.sum((y - predicted) ** 2)) / total if total > 0 else 0.0
    return {"slope": float(slope), "today_value": float(intercept), "r2": max(0.0, r2)}


def _confidence_label(score: float) -> str:
    if score >= 0.7:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM"
    return "LOW"


def _urgency(days_until: int, lead_time: int, present: bool = False) -> str:
    """PRESENT means the limit is already crossed - a current problem, not a
    prediction, and labelled that way so it is never passed off as foresight."""
    if present:
        return "PRESENT"
    if days_until <= lead_time:
        return "ACT_NOW"
    if days_until <= 365:
        return "WITHIN_A_YEAR"
    return "PLAN_AHEAD"


# --------------------------------------------------------------------------
# Corroborating signals
# --------------------------------------------------------------------------
def _corroboration(
    component: Any,
    life: Dict[str, Any],
    latest_recommendation: Optional[str],
    survival_probability_12m: Optional[float],
) -> List[Dict[str, Any]]:
    """Signals produced independently of the condition trends."""
    signals: List[Dict[str, Any]] = []

    if life.get("available"):
        years = life["projection"]["years_to_replace_band"]
        signals.append(
            {
                "signal": "Usage-based life model",
                "agrees": life["band"] != "green" or years <= HORIZON_YEARS,
                "detail": (
                    f"{life['life_consumed']['governing']:.0%} of adjusted life used, ageing at "
                    f"{life['ageing_rate']:.2f}x design; replace band "
                    + ("already reached" if years == 0 else f"in {years:.1f} years")
                    + "."
                ),
            }
        )

    if survival_probability_12m is not None:
        signals.append(
            {
                "signal": "Survival model (fleet statistics)",
                "agrees": survival_probability_12m >= SURVIVAL_AGREES_AT,
                "detail": (
                    f"{survival_probability_12m:.0%} probability of leaving the Continue Using "
                    f"band within 12 months (agrees at {SURVIVAL_AGREES_AT:.0%}+)."
                ),
            }
        )

    if latest_recommendation:
        signals.append(
            {
                "signal": "AI recommendation (classifier and decision flow)",
                "agrees": latest_recommendation in _CONCERNED_RECOMMENDATIONS,
                "detail": f"Current assessment: {recommendation_label(latest_recommendation)}.",
            }
        )

    repairs = int(_get(component, "repair_count", 0) or 0)
    failures = int(_get(component, "failure_history", 0) or 0)
    signals.append(
        {
            "signal": "Service record",
            "agrees": repairs + failures > 0,
            "detail": f"{repairs} repair(s) and {failures} recorded failure(s) on this component.",
        }
    )
    return signals


def _score(base: float, signals: List[Dict[str, Any]]) -> float:
    """Blend the primary evidence strength with independent agreement."""
    if not signals:
        return round(min(base, 0.6), 3)
    agreement = sum(1 for signal in signals if signal["agrees"]) / len(signals)
    return round(min(0.95, 0.4 * base + 0.6 * agreement), 3)


# --------------------------------------------------------------------------
# Forecast
# --------------------------------------------------------------------------
def forecast(
    component: Any,
    events: Iterable[Any] = (),
    latest_recommendation: Optional[str] = None,
    survival_probability_12m: Optional[float] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Issues this component is predicted to reach within :data:`HORIZON_YEARS`."""
    component_type = str(_get(component, "component_type"))
    if component_type not in FAILURE_MODES:
        return {
            "supported": False,
            "component_type": component_type,
            "reason": (
                "Pre-emptive issue forecasting currently covers "
                f"{', '.join(FAILURE_MODES)} only."
            ),
        }

    today = today or utcnow().date()
    events = list(events)
    modes = FAILURE_MODES[component_type]
    lead_time = LEAD_TIME_DAYS[component_type]
    life = life_model.assess(component, today=today)
    corroboration = _corroboration(component, life, latest_recommendation, survival_probability_12m)

    issues: List[Dict[str, Any]] = []
    indicators: List[Dict[str, Any]] = []

    for indicator, meta in INDICATORS.items():
        if indicator not in modes:
            continue
        mode = modes[indicator]
        limit = _limit(indicator, component_type)
        points = _series(component, events, indicator)
        fit = _fit(points, today)
        rising = meta["worsens"] == "rising"
        summary = {
            "indicator": indicator,
            "label": meta["label"],
            "unit": meta["unit"],
            "limit": limit,
            "points": len(points),
            "issue": mode["title"],
        }
        if fit is None:
            indicators.append({**summary, "status": "insufficient_history"})
            continue

        current = fit["today_value"]
        # Drift below 1% of the limit per year is noise, not a trend - without
        # this a flat series fits a slope of -1e-15 and reads as "worsening".
        meaningful = abs(fit["slope"]) >= MIN_SLOPE_FRACTION * abs(limit)
        worsening = meaningful and (fit["slope"] > 0 if rising else fit["slope"] < 0)
        beyond = current >= limit if rising else current <= limit
        summary.update(
            {
                "current": round(current, 2),
                "slope_per_year": round(fit["slope"], 3),
                "r2": round(fit["r2"], 3),
            }
        )

        if beyond:
            years_until = 0.0
        elif worsening:
            years_until = (limit - current) / fit["slope"]
        else:
            indicators.append({**summary, "status": "stable"})
            continue

        if years_until > HORIZON_YEARS:
            indicators.append({**summary, "status": "worsening_beyond_horizon", "years_until": round(years_until, 1)})
            continue

        indicators.append({**summary, "status": "exceeded" if beyond else "worsening", "years_until": round(years_until, 2)})
        predicted = today + timedelta(days=round(years_until * 365.25))
        slope_text = f"{abs(fit['slope']):.2f} {meta['unit']} per year"
        evidence = {
            "kind": "trend",
            "indicator": indicator,
            "label": meta["label"],
            "unit": meta["unit"],
            "limit": limit,
            "readings": [{"date": when.isoformat(), "value": round(value, 2)} for when, value in points],
            "fit": [
                {"date": points[0][0].isoformat(), "value": round(fit["slope"] * (points[0][0] - today).days / 365.25 + current, 2)},
                {"date": predicted.isoformat(), "value": round(limit if not beyond else current, 2)},
            ],
            "slope_per_year": round(fit["slope"], 3),
            "r2": round(fit["r2"], 3),
        }
        why = (
            f"{meta['label']} is {'already past' if beyond else ('rising' if rising else 'falling')} "
            + (f"its limit of {limit:g} {meta['unit']} (trend value today {current:.1f})." if beyond else
               f"at {slope_text} across {len(points)} readings (fit R² {fit['r2']:.2f}); "
               f"at this rate it reaches the {limit:g} {meta['unit']} limit in {years_until * 12:.0f} months.")
        )
        issues.append(
            _issue(mode, component_type, today, predicted, lead_time, why, evidence,
                   _score(fit["r2"] if not beyond else 1.0, corroboration), corroboration,
                   primary=f"Condition trend - {meta['label'].lower()}", present=beyond)
        )

    if life.get("available") and "life" in modes:
        years = life["projection"]["years_to_replace_band"]
        if years <= HORIZON_YEARS:
            predicted = today + timedelta(days=round(years * 365.25))
            others = [signal for signal in corroboration if signal["signal"] != "Usage-based life model"]
            evidence = {
                "kind": "life",
                "ageing_rate": life["ageing_rate"],
                "life_consumed": life["life_consumed"]["governing"],
                "design_life_years": life["design_life_years"],
                "factors": [
                    {"label": factor["label"], "multiplier": factor["multiplier"]}
                    for factor in life["factors"]
                ],
            }
            why = (
                f"Ageing at {life['ageing_rate']:.2f}x the design rate with "
                f"{life['life_consumed']['governing']:.0%} of its adjusted life used, it "
                + ("is already in the replace band." if years == 0 else f"enters the replace band in {years * 12:.0f} months.")
            )
            issues.append(
                _issue(modes["life"], component_type, today, predicted, lead_time, why, evidence,
                       _score(0.6, others), others, primary="Usage-adjusted life model",
                       present=years == 0)
            )

    issues.sort(key=lambda issue: (issue["days_until"], -issue["confidence"]))
    return {
        "supported": True,
        "component_type": component_type,
        "generated_on": today.isoformat(),
        "horizon_years": HORIZON_YEARS,
        "lead_time_days": lead_time,
        "headline": _headline(issues),
        "issues": issues,
        "indicators": indicators,
        "safety_critical": is_safety_critical(component_type),
        "method": (
            "Condition trends (least-squares over up to the last "
            f"{MAX_TREND_POINTS} service readings) extrapolated to each indicator's limit, plus "
            "the usage-adjusted life milestone. Confidence blends trend fit quality with "
            "agreement from independent signals. PROTOTYPE - synthetic service history; "
            "advisory only, it never replaces an inspection."
        ),
    }


def _issue(
    mode: Dict[str, Any],
    component_type: str,
    today: date,
    predicted: date,
    lead_time: int,
    why: str,
    evidence: Dict[str, Any],
    confidence: float,
    justification: List[Dict[str, Any]],
    primary: str,
    present: bool = False,
) -> Dict[str, Any]:
    days_until = max(0, (predicted - today).days)
    act_by = max(today, predicted - timedelta(days=lead_time))
    return {
        "code": mode["code"],
        "title": mode["title"],
        "mechanism": mode["mechanism"],
        "predicted_date": predicted.isoformat(),
        "days_until": days_until,
        "act_by": act_by.isoformat(),
        "urgency": _urgency(days_until, lead_time, present),
        "present": present,
        "confidence": confidence,
        "confidence_label": _confidence_label(confidence),
        "why": why,
        "primary_evidence": primary,
        "evidence": evidence,
        "justification": justification,
        "measures": mode["measures"],
        "safety_critical": is_safety_critical(component_type),
    }


def _headline(issues: List[Dict[str, Any]]) -> str:
    present = [issue for issue in issues if issue["present"]]
    ahead = [issue for issue in issues if not issue["present"]]
    parts = []
    if present:
        parts.append(
            f"{len(present)} limit{'s' if len(present) != 1 else ''} already crossed - "
            "a current problem, inspect now."
        )
    if ahead:
        first = ahead[0]
        months = max(1, round(first["days_until"] / 30.4))
        parts.append(
            f"{len(ahead)} issue{'s' if len(ahead) != 1 else ''} predicted ahead. Next: "
            f"{first['title'].lower()} in about {months} months - act by {first['act_by']}."
        )
    if not parts:
        return f"No issue predicted within the next {HORIZON_YEARS:g} years at current trends."
    return " ".join(parts)


def audit_summary(result: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """What goes into the audit chain: proof of what was predicted, and when."""
    if not result.get("supported"):
        return None
    return [
        {
            "code": issue["code"],
            "present": issue["present"],
            "predicted_date": issue["predicted_date"],
            "act_by": issue["act_by"],
            "confidence": issue["confidence"],
        }
        for issue in result["issues"]
    ]
