"""The four recommendation categories, the decision flow, grades and age.

* The decision flow's gates run in order and each category is reachable only
  on its own evidence.
* API output carries the four category names and never the removed
  Reuse / Refurbish / Recycle categories.
* A material grade is shown only when one is recorded - never invented.
* The life model's effective age stays close to calendar age on held-out data
  (a regression guard for the calibration fix).
"""

from __future__ import annotations

import json
import re
import statistics
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from app.core.config import settings
from app.ml import decision_flow, life_model
from app.utils.enums import (
    RECOMMENDATION_LABELS,
    Recommendation,
    canonical_recommendation,
    recommendation_label,
)

CONTINUE = Recommendation.CONTINUE_USING.value
COMPONENT = Recommendation.COMPONENT_RECOVERY.value
MATERIAL = Recommendation.MATERIAL_RECOVERY.value
DISPOSE = Recommendation.DISPOSE.value

#: The removed categories, as words. "Reusable" is not a category name.
OLD_CATEGORY = re.compile(r"\b(reuse|refurbish\w*|recycl\w*)\b", re.IGNORECASE)


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------
def test_the_four_display_names_are_exact():
    assert RECOMMENDATION_LABELS[CONTINUE] == "Continue Using – No Changes Required"
    assert RECOMMENDATION_LABELS[COMPONENT] == "Component Recovery"
    assert RECOMMENDATION_LABELS[MATERIAL] == "Material Recovery"
    assert RECOMMENDATION_LABELS[DISPOSE] == "Dispose"


@pytest.mark.parametrize(
    "legacy, new",
    [("REUSE", CONTINUE), ("REFURBISH", COMPONENT), ("RECYCLE", MATERIAL), ("DISPOSE", DISPOSE)],
)
def test_legacy_codes_read_as_the_new_categories(legacy, new):
    assert canonical_recommendation(legacy) == new
    assert recommendation_label(legacy) == RECOMMENDATION_LABELS[new]


# --------------------------------------------------------------------------
# Decision flow gates
# --------------------------------------------------------------------------
def _p(continue_=0.0, component=0.0, material=0.0, dispose=0.0):
    return {CONTINUE: continue_, COMPONENT: component, MATERIAL: material, DISPOSE: dispose}


def test_gate_one_suitable_for_current_application_continues():
    result = decision_flow.decide(_p(0.8, 0.2), "Motor", "Steel", inspection_score=85)
    assert result["recommendation"] == CONTINUE
    assert len(result["steps"]) == 1 and result["steps"][0]["passed"] is True


def test_a_replace_band_inspection_vetoes_continued_use():
    result = decision_flow.decide(_p(0.8, 0.2), "Motor", "Steel", inspection_score=40)
    assert result["recommendation"] != CONTINUE
    assert result["steps"][0]["passed"] is False


def test_gate_two_recovers_sub_components_when_serviceable():
    result = decision_flow.decide(_p(0.2, 0.6, 0.2), "Motor", "Steel", inspection_score=60)
    assert result["recommendation"] == COMPONENT
    # No grade on record: the wording stays generic rather than naming parts.
    assert result["subcomponents"]["parts"] == []
    assert "complete component is not refurbished or supplied again" in result["text"]


def test_sub_components_are_named_only_from_a_recorded_grade():
    result = decision_flow.decide(
        _p(0.2, 0.6, 0.2), "Motor", "Steel", inspection_score=60, grade="pmsm_class_f"
    )
    constituents = life_model.MATERIAL_GRADES["Motor"]["pmsm_class_f"]["constituents"]
    expected = [c["name"] for c in constituents if c["separable"]]
    assert result["subcomponents"]["parts"] == expected
    assert expected, "premise: the recorded grade lists separable parts"


def test_a_type_without_separable_sub_components_skips_to_material():
    result = decision_flow.decide(_p(0.2, 0.7, 0.1), "Steel Rope", "Steel", inspection_score=60)
    assert result["recommendation"] == MATERIAL
    assert result["steps"][1]["passed"] is False


def test_gate_three_material_recovery_when_parts_are_not_serviceable():
    result = decision_flow.decide(_p(0.05, 0.15, 0.8), "Motor", "Steel", inspection_score=30)
    assert result["recommendation"] == MATERIAL


def test_dispose_only_when_nothing_else_is_technically_suitable():
    # Low serviceability probability: gate 2 fails even for an assembly.
    result = decision_flow.decide(_p(0.05, 0.1, 0.25, 0.6), "Door Operator", "Composite", inspection_score=30)
    assert result["recommendation"] == DISPOSE
    assert [step["passed"] for step in result["steps"]] == [False, False, False]
    # A recoverable material never falls through to Dispose.
    steel = decision_flow.decide(_p(0.05, 0.1, 0.25, 0.6), "Door Operator", "Steel", inspection_score=30)
    assert steel["recommendation"] == MATERIAL


def test_training_labels_follow_the_same_flow():
    limits = (0.35, 0.56)
    assert decision_flow.label_from_wear(0.2, "Motor", "Steel", limits) == CONTINUE
    assert decision_flow.label_from_wear(0.45, "Motor", "Steel", limits) == COMPONENT
    assert decision_flow.label_from_wear(0.45, "Steel Rope", "Steel", limits) == MATERIAL
    assert decision_flow.label_from_wear(0.9, "Motor", "Steel", limits) == MATERIAL
    assert decision_flow.label_from_wear(0.9, "Door Operator", "Composite", limits) == DISPOSE


# --------------------------------------------------------------------------
# API output
# --------------------------------------------------------------------------
def test_the_assessment_carries_the_flow_and_no_removed_category(client, parts_recovery_payload):
    created = client.post("/api/v1/components", json=parts_recovery_payload).json()
    body = client.post(f"/api/v1/components/{created['component_id']}/predict").json()
    assert body["recommendation"] == COMPONENT
    assert body["recommendation_label"] == "Component Recovery"
    assert body["decision_flow"]["steps"]
    assert "sub-components" in body["recommendation_text"]
    found = OLD_CATEGORY.findall(json.dumps(body))
    # The only permitted match is the negation "not refurbished".
    assert set(word.lower() for word in found) <= {"refurbished"}, found


def test_enum_metadata_lists_only_the_four_categories(client):
    body = client.get("/api/v1/meta/enums").json()
    decided = [code for code in body["recommendations"] if code != "DEFER_TO_INSPECTION"]
    assert decided == [CONTINUE, COMPONENT, MATERIAL, DISPOSE]


def test_lists_and_exports_carry_the_label(client, created_component):
    rows = client.get("/api/v1/components").json()["items"]
    row = next(r for r in rows if r["component_id"] == created_component["component_id"])
    assert row["recommendation_label"] == recommendation_label(row["recommendation"])

    csv_text = client.get("/api/v1/components/export").text
    header = csv_text.splitlines()[0]
    assert "material_grade" in header and "latest_recommendation_label" in header
    assert not OLD_CATEGORY.search(csv_text)


# --------------------------------------------------------------------------
# Grades: recorded, or an industry-standard grade labelled as assumed
# --------------------------------------------------------------------------
def test_an_unrecorded_grade_shows_the_assumed_industry_grade_everywhere(client, created_component):
    component_id = created_component["component_id"]
    assumed = (
        life_model.display_label(life_model.MATERIAL_GRADES["Motor"]["induction_cu_class_f"])
        + life_model.INDUSTRY_DEFAULT_SUFFIX
    )
    # Nothing is written to the record - the assumption is derived on read.
    assert created_component["material_grade"] is None
    assert created_component["material_grade_label"] == assumed

    rows = client.get("/api/v1/components").json()["items"]
    assert next(r for r in rows if r["component_id"] == component_id)["material_grade_label"] == assumed
    report = client.get(f"/api/v1/passports/{component_id}/report").json()
    assert report["material_grade"] == assumed
    dpp = client.get(f"/api/v1/passports/{component_id}/dpp").json()
    assert dpp["product"]["material_grade"] == assumed
    assert dpp["material_composition"]["grade"]["grade_provenance"] == "industry_default"


def test_a_recorded_grade_is_shown_as_recorded(client, component_payload):
    created = client.post(
        "/api/v1/components", json={**component_payload, "material_grade": "pmsm_class_h"}
    ).json()
    label = life_model.display_label(life_model.MATERIAL_GRADES["Motor"]["pmsm_class_h"])
    assert created["material_grade_label"] == label
    report = client.get(f"/api/v1/passports/{created['component_id']}/report").json()
    assert report["material_grade"] == label


def test_the_seed_script_does_not_invent_grades():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "seed_database.py").read_text(
        encoding="utf-8"
    )
    assert "_material_grade(" not in source
    assert "MATERIAL_GRADES" not in source


# --------------------------------------------------------------------------
# Predicted (effective) age vs calendar age
# --------------------------------------------------------------------------
def test_effective_age_tracks_calendar_age_on_held_out_data():
    """Regression guard for the calibration fix. Before it, the median
    effective/calendar ratio on test.csv was 1.41 with 33% of parts within
    25% of calendar age. The calibration is fitted on train.csv only."""
    path = Path(settings.dataset_file).with_name("test.csv")
    if not path.exists():
        pytest.skip("held-out split not generated")
    today = date(2026, 9, 24)
    frame = pd.read_csv(path)
    frame = frame[frame["component_type"].isin(life_model.FOCUS_TYPES) & (frame["component_age"] > 0.5)]
    ratios = []
    for _, row in frame.iterrows():
        record = row.to_dict()
        record["installation_date"] = today - timedelta(days=round(record["component_age"] * 365.25))
        record["material_grade"] = None
        result = life_model.assess(record, today=today)
        if result.get("available"):
            ratios.append(result["effective_age_years"] / result["calendar_age_years"])
    assert len(ratios) > 200
    assert 0.85 <= statistics.median(ratios) <= 1.2
    within = sum(1 for r in ratios if 0.75 <= r <= 1.25) / len(ratios)
    assert within >= 0.40
