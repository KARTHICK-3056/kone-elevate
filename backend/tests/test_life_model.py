"""Usage-adjusted life model (app.ml.life_model) and its passport wiring."""

from __future__ import annotations

from datetime import date

import pytest

from app.ml import life_model
from app.ml.generate_dataset import TYPE_MATERIALS
from app.utils.enums import ComponentType

TODAY = date(2026, 9, 24)


def _nominal_services(years: float, component_type: str = "Sheave") -> int:
    """Service visits at the fleet's fitted nominal interval over ``years``."""
    return int(years * 365.25 / life_model.service_interval_days(component_type))


def _component(**overrides):
    """A mid-life sheave run at exactly design duty (the fitted nominal point)."""
    base = {
        "component_type": "Sheave",
        "material": "Cast Iron",
        "material_grade": None,
        "installation_date": date(2012, 9, 24),  # 14 years before TODAY
        # Sheave design: 28 years, 95,000 h, 1,900,000 cycles -> per year:
        "operating_hours": 95000 / 28 * 14,
        "load_cycles": int(1900000 / 28 * 14),
        "average_load": 1800 * life_model.reference_utilisation("Sheave"),
        "vibration": 1.0,
        "temperature": 30.0,
        "inspection_score": 100.0,
        "service_count": _nominal_services(14),
        "days_since_last_service": 90,
    }
    base.update(overrides)
    return base


def test_design_duty_ages_at_one_year_per_year():
    # Ductile iron is the sheave's reference grade (life factor 1.0).
    result = life_model.assess(_component(material_grade="ductile_iron"), today=TODAY)
    assert result["ageing_rate"] == pytest.approx(1.0, abs=0.01)
    assert result["effective_age_years"] == pytest.approx(result["calendar_age_years"], abs=0.1)
    assert result["life_consumed"]["governing"] == pytest.approx(14 / 28, abs=0.01)


def test_heavier_and_busier_use_speeds_ageing_up():
    nominal = life_model.assess(_component(), today=TODAY)
    hard = life_model.assess(
        _component(load_cycles=int(1900000 / 28 * 14 * 1.6), average_load=1800 * 0.8),
        today=TODAY,
    )
    assert hard["ageing_rate"] > 1.5
    assert hard["projection"]["projected_total_life_years"] < nominal["projection"]["projected_total_life_years"]
    assert hard["projection"]["life_change_years"] < 0


def test_light_use_extends_life():
    light = life_model.assess(
        _component(load_cycles=int(1900000 / 28 * 14 * 0.4), operating_hours=95000 / 28 * 14 * 0.4),
        today=TODAY,
    )
    assert light["ageing_rate"] < 1.0
    assert light["projection"]["life_change_years"] > 0


def test_material_grade_changes_life_for_the_same_use():
    """The mentor's example: same component, same duty, different material."""
    grey = life_model.assess(_component(material_grade="grey_iron"), today=TODAY)
    ductile = life_model.assess(_component(material_grade="ductile_iron"), today=TODAY)
    steel = life_model.assess(_component(material="Steel", material_grade="hardened_steel"), today=TODAY)

    assert grey["ageing_rate"] == ductile["ageing_rate"] == steel["ageing_rate"]
    assert grey["design_life_years"] < ductile["design_life_years"] < steel["design_life_years"]
    assert (
        grey["life_consumed"]["governing"]
        > ductile["life_consumed"]["governing"]
        > steel["life_consumed"]["governing"]
    )


def test_polymer_brake_lining_wears_out_before_a_sintered_one():
    common = {"component_type": "Brake", "average_load": 1400 * 0.6}
    polymer = life_model.assess(_component(material="Composite", **common), today=TODAY)
    sintered = life_model.assess(_component(material="Steel", **common), today=TODAY)
    assert polymer["design_life_years"] < sintered["design_life_years"]
    assert polymer["projection"]["years_to_end_of_life"] < sintered["projection"]["years_to_end_of_life"]


def test_unrecorded_grade_uses_the_industry_standard_grade_labelled_as_assumed():
    profile = life_model.material_profile(_component())
    assert profile["grade"] == "grey_iron"
    assert profile["grade_provenance"] == "industry_default"
    assert profile["grade_label"].endswith(life_model.INDUSTRY_DEFAULT_SUFFIX)
    assert profile["constituents"]
    assert life_model.grade_label(_component()).endswith(life_model.INDUSTRY_DEFAULT_SUFFIX)
    # The assumed grade is the shortest-lived the material allows, so an
    # assumption never flatters the component's life.
    conservative, _ = life_model.undetermined_grade_factor("Sheave", "Cast Iron")
    assert profile["life_factor"] == conservative
    assert conservative == min(
        g["life_factor"]
        for g in life_model.grades_for("Sheave").values()
        if "Cast Iron" in g["materials"]
    )


def test_grade_that_does_not_fit_the_material_is_rejected_not_used():
    profile = life_model.material_profile(_component(material_grade="hardened_steel"))
    assert profile["grade"] == "grey_iron"
    assert profile["grade_label"].endswith(life_model.INDUSTRY_DEFAULT_SUFFIX)
    assert profile["grade_provenance"] == "recorded_grade_rejected"
    assert "hardened_steel" in profile["grade_note"]


def test_a_recorded_grade_is_shown_by_name():
    assert life_model.grade_label(_component(material_grade="ductile_iron")) == (
        life_model.display_label(life_model.MATERIAL_GRADES["Sheave"]["ductile_iron"])
    )


def test_every_grade_composition_sums_to_one_and_flags_separable_parts():
    for component_type, grades in life_model.MATERIAL_GRADES.items():
        for key, grade in grades.items():
            total = sum(item["mass_fraction"] for item in grade["constituents"])
            assert total == pytest.approx(1.0), (component_type, key)
            for item in grade["constituents"]:
                assert isinstance(item.get("separable"), bool), (component_type, key, item["name"])


def test_bad_inspection_governs_over_an_optimistic_usage_model():
    result = life_model.assess(
        _component(material_grade="ductile_iron", inspection_score=40.0), today=TODAY
    )
    consumed = result["life_consumed"]
    assert consumed["governed_by"] == "inspection"
    assert consumed["governing"] == consumed["inspection"] > consumed["usage_model"]
    assert consumed["divergence_note"] is not None
    assert result["band"] == "red"


def test_bands_status_and_implication_follow_life_consumed():
    fresh = life_model.assess(
        _component(
            material_grade="ductile_iron",
            installation_date=date(2022, 9, 24),
            operating_hours=95000 / 28 * 4,
            load_cycles=int(1900000 / 28 * 4),
            service_count=_nominal_services(4),
        ),
        today=TODAY,
    )
    assert fresh["band"] == "green"
    assert fresh["implication"]["recommendation"] == "CONTINUE_USING"

    mid = life_model.assess(
        _component(
            material_grade="ductile_iron",
            installation_date=date(2008, 9, 24),
            operating_hours=95000 / 28 * 18,
            load_cycles=int(1900000 / 28 * 18),
            service_count=_nominal_services(18),
        ),
        today=TODAY,
    )
    assert mid["band"] == "amber"
    assert mid["status"]["level"] == "PLAN"
    assert mid["implication"]["recommendation"] == "COMPONENT_RECOVERY"


def test_steel_rope_is_never_sent_to_component_recovery():
    """A wire rope has no separable sub-components: past Continue Using, the
    only recovery route left is its material."""
    # Seven years at rope design duty (12 y, 55,000 h, 1,400,000 cycles).
    rope = life_model.assess(
        _component(
            component_type="Steel Rope",
            material="Steel",
            installation_date=date(2019, 9, 24),
            operating_hours=55000 / 12 * 7,
            load_cycles=int(1400000 / 12 * 7),
            average_load=1600 * life_model.reference_utilisation("Steel Rope"),
            service_count=_nominal_services(7, "Steel Rope"),
        ),
        today=TODAY,
    )
    assert rope["band"] == "amber"
    assert rope["implication"]["recommendation"] == "MATERIAL_RECOVERY"
    assert rope["implication"]["safety_gate"] is True


def test_overdue_component_reports_the_life_it_actually_had():
    rope = life_model.assess(
        _component(component_type="Steel Rope", material="Steel", installation_date=date(2000, 9, 24)),
        today=TODAY,
    )
    assert rope["status"]["level"] == "OVERDUE"
    assert rope["projection"]["years_to_end_of_life"] == 0
    assert rope["projection"]["projected_total_life_years"] < rope["calendar_age_years"]


def test_trajectory_has_design_history_and_projection_that_meet_today():
    result = life_model.assess(_component(), today=TODAY)
    points = result["trajectory"]
    assert points[0]["design"] == 0
    meeting = [p for p in points if p["actual"] is not None and p["projected"] is not None]
    assert len(meeting) == 1
    assert meeting[0]["years_in_service"] == pytest.approx(result["calendar_age_years"], abs=0.01)
    assert any(p["actual"] is None for p in points)  # history stops at today


def test_every_factor_names_its_data_source():
    result = life_model.assess(_component(), today=TODAY)
    for factor in result["factors"]:
        assert factor["sources"], factor["key"]
        for source in factor["sources"]:
            assert source["availability"] in {"published_api", "not_published", "manual_record"}


def test_every_registry_type_has_an_expected_life():
    for component_type in ComponentType.values():
        assert life_model.is_supported(component_type), component_type
        assert component_type in life_model.MECHANISMS
    result = life_model.assess(_component(component_type="Door Operator", material="Aluminum"), today=TODAY)
    assert result["available"] is True
    assert result["design_life_years"] > 0


def test_every_plausible_material_has_an_industry_default_that_never_flatters_life():
    for component_type, materials in TYPE_MATERIALS.items():
        for material, _share in materials:
            key = life_model.INDUSTRY_DEFAULT_GRADES[(component_type, material)]
            grade = life_model.MATERIAL_GRADES[component_type][key]
            assert material in grade["materials"], (component_type, material)
            shortest, _ = life_model.undetermined_grade_factor(component_type, material)
            assert grade["life_factor"] == shortest, (component_type, material)


def test_types_outside_the_model_are_declined_not_guessed():
    result = life_model.assess(_component(component_type="Handrail", material="Steel"), today=TODAY)
    assert result["supported"] is False
    assert life_model.material_profile(_component(component_type="Handrail")) is None


def test_missing_installation_date_is_reported_not_projected():
    result = life_model.assess(_component(installation_date=None), today=TODAY)
    assert result["supported"] is True
    assert result["available"] is False


# --------------------------------------------------------------- API wiring
def test_passport_carries_material_profile_and_life_assessment(client, created_component):
    body = client.get(f"/api/v1/passports/{created_component['component_id']}").json()
    # No grade was recorded: the industry-standard grade is shown, marked as assumed.
    assert body["material_profile"]["grade"] == "induction_cu_class_f"
    assert body["material_profile"]["grade_provenance"] == "industry_default"
    assert body["component"]["material_grade_label"].endswith(life_model.INDUSTRY_DEFAULT_SUFFIX)
    life = body["life_assessment"]
    assert life["available"] is True
    assert life["band"] in {"green", "amber", "red"}
    assert "agrees_with_ai" in life["implication"]
    assert len(life["trajectory"]) > 10


def test_material_grade_is_recorded_and_validated(client, component_payload):
    created = client.post(
        "/api/v1/components", json={**component_payload, "material_grade": "pmsm_class_h"}
    )
    assert created.status_code == 201, created.text
    passport = client.get(f"/api/v1/passports/{created.json()['component_id']}").json()
    assert passport["material_profile"]["grade_provenance"] == "recorded"
    assert passport["material_profile"]["life_factor"] == 1.2
    assert passport["component"]["material_grade_label"] == (
        life_model.display_label(life_model.MATERIAL_GRADES["Motor"]["pmsm_class_h"])
    )

    rejected = client.post(
        "/api/v1/components", json={**component_payload, "material_grade": "unobtainium"}
    )
    assert rejected.status_code == 422


def test_dpp_export_includes_grade_and_life_projection(client, created_component):
    body = client.get(f"/api/v1/passports/{created_component['component_id']}/dpp").json()
    assert body["material_composition"]["grade"]["grade"] == "induction_cu_class_f"
    assert body["product"]["material_grade"].endswith(life_model.INDUSTRY_DEFAULT_SUFFIX)
    assert body["life_projection"]["band"] in {"green", "amber", "red"}
    assert "trajectory" not in body["life_projection"]


def test_life_endpoint_serves_the_projection_for_every_type(client, created_component, component_payload):
    body = client.get(f"/api/v1/passports/{created_component['component_id']}/life").json()
    assert body["material_profile"]["grade"] == "induction_cu_class_f"
    assert body["material_profile"]["grade_provenance"] == "industry_default"
    assert body["life_assessment"]["available"] is True

    door = client.post(
        "/api/v1/components",
        json={**component_payload, "component_type": "Door Operator", "material": "Aluminum"},
    ).json()
    body = client.get(f"/api/v1/passports/{door['component_id']}/life").json()
    assert body["material_profile"]["grade"] == "aluminium_belt_vvvf"
    assert body["life_assessment"]["supported"] is True
    assert body["life_assessment"]["design_life_years"] > 0


def _thermal(result):
    return next(f for f in result["factors"] if f["key"] == "thermal")


def test_zero_celsius_is_a_reading_not_a_missing_value():
    motor = _component(component_type="Motor", material="Steel", temperature=0.0)
    thermal = _thermal(life_model.assess(motor, today=TODAY))
    assert thermal["observed"] == "0 C"
    assert thermal["multiplier"] == pytest.approx(0.8)  # the thermal floor, not 25 C's value


def test_commissioning_reading_starts_the_history_instead_of_new_condition():
    # Motor nominal point is 75 C; 40 and 50 C both sit on the 0.8 thermal floor.
    install = date(2012, 9, 24)
    motor = _component(component_type="Motor", material="Steel", temperature=50.0, installation_date=install)
    commissioned = {**motor, "readings": [{"event_date": install, "temperature": 40.0, "vibration": None}]}
    assert _thermal(life_model.assess(motor, today=TODAY))["history_multiplier"] == pytest.approx(0.9)
    assert _thermal(life_model.assess(commissioned, today=TODAY))["history_multiplier"] == pytest.approx(0.8)


MAIN_TYPES = ("Motor", "Steel Rope", "Sheave", "Governor")


@pytest.mark.parametrize("component_type", MAIN_TYPES)
def test_every_grade_of_the_main_types_is_priced(component_type):
    comparison = life_model.grade_cost_comparison(component_type, None)
    priced = {option["grade"] for option in comparison["options"]}
    assert priced == set(life_model.grades_for(component_type))


@pytest.mark.parametrize("component_type", MAIN_TYPES)
def test_cost_comparison_ranks_by_cost_per_year_of_service(component_type):
    comparison = life_model.grade_cost_comparison(component_type, None)
    options = comparison["options"]
    per_year = [option["cost_per_year"] for option in options]
    assert per_year == sorted(per_year)
    assert options[0]["most_cost_effective"] and comparison["most_cost_effective_grade"] == options[0]["grade"]
    for option in options:
        expected = (option["part_price"] + option["fitting_cost"]) / option["expected_life_years"]
        assert option["cost_per_year"] == pytest.approx(expected, rel=0.01)


def test_heavier_duty_shortens_every_grade_but_keeps_the_ranking():
    design = life_model.grade_cost_comparison("Sheave", "grey_iron")
    heavy = life_model.grade_cost_comparison("Sheave", "grey_iron", ageing_rate=2.0)
    assert [o["grade"] for o in heavy["options"]] == [o["grade"] for o in design["options"]]
    for light, hard in zip(design["options"], heavy["options"], strict=True):
        assert hard["expected_life_years"] == pytest.approx(light["expected_life_years"] / 2, abs=0.1)
    assert heavy["duty_basis"] == "this component's own usage"


def test_saving_is_reported_against_the_current_grade():
    comparison = life_model.grade_cost_comparison("Sheave", "grey_iron")
    current = next(o for o in comparison["options"] if o["current"])
    best = comparison["options"][0]
    assert comparison["saving_per_year"] == pytest.approx(current["cost_per_year"] - best["cost_per_year"])


def test_types_without_grade_prices_have_no_comparison():
    assert life_model.grade_cost_comparison("Door Operator", None) is None
