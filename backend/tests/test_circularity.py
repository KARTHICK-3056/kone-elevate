"""Material Circularity Indicator (CE-2).

The point of this metric is that it measures something money and carbon do
not. These tests therefore spend most of their effort on *ordering* - a
more circular component must score higher than a less circular one - rather
than on pinning exact decimals, which would only lock in the prototype's
own placeholder constants.
"""

from __future__ import annotations

from app.services import circularity_service


def _mci(client, component_id):
    response = client.get(f"/api/v1/reports/circularity/{component_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_mci_is_bounded(client, created_component):
    body = _mci(client, created_component["component_id"])
    assert 0.0 <= body["mci"] <= 1.0
    assert body["inputs"]["L_av_years"] > 0


def test_a_landfilled_part_scores_lower_than_a_reused_one(client, component_payload):
    """The ordering the whole indicator exists to express."""
    base = {**component_payload, "run_initial_prediction": False}

    reused = client.post(
        "/api/v1/components", json={**base, "current_status": "PART_RECOVERY"}
    ).json()
    binned = client.post(
        "/api/v1/components", json={**base, "current_status": "DISPOSED"}
    ).json()

    client.post(
        f"/api/v1/components/{reused['component_id']}/service-events",
        json={"event_type": "MAINTENANCE", "event_date": "2026-07-01"},
    )

    reused_mci = _mci(client, reused["component_id"])["mci"]
    binned_mci = _mci(client, binned["component_id"])["mci"]
    assert reused_mci > binned_mci, (
        f"a part prepared for reuse ({reused_mci}) must out-score one sent to "
        f"landfill ({binned_mci}) - otherwise this is not a circularity metric"
    )


def test_a_second_life_part_scores_higher_than_an_identical_first_life_one(
    client, component_payload, session_factory
):
    """Reused feedstock (F_U) is the input CE-1 made reachable: a refitted
    component was not made from virgin material, and the indicator has to
    reward that or closing the loop buys nothing measurable.

    The component is promoted to a second life directly rather than driven
    through the remove/list/match/accept/refit journey, which
    tests/test_circular_loop.py already covers - here the subject is the
    indicator, and the two components must differ in exactly one input.
    """
    from app.models.component import Component  # noqa: PLC0415 - test-local

    base = {**component_payload, "run_initial_prediction": False}
    created = client.post("/api/v1/components", json=base)
    assert created.status_code == 201, created.text
    component_id = created.json()["component_id"]

    with session_factory() as session:
        component = session.query(Component).filter_by(component_id=component_id).one()
        before = circularity_service.component_mci(session, component)
        component.life_cycle_number = 2
        after = circularity_service.component_mci(session, component)
        session.rollback()

    assert before["inputs"]["F_U_reused_feedstock"] == 0.0
    assert after["inputs"]["F_U_reused_feedstock"] == 1.0
    assert after["mci"] > before["mci"], (
        f"a refitted part ({after['mci']}) must out-score the same part made "
        f"from virgin stock ({before['mci']})"
    )


def test_fleet_report_separates_measured_from_projected(client, created_component):
    body = client.get("/api/v1/reports/circularity").json()
    assert body["components_scored"] >= 1
    assert 0.0 <= body["mci_mass_weighted"] <= 1.0
    split = body["basis_split"]
    assert split["actual"] + split["projected"] == body["components_scored"]


def test_narrow_is_reported_as_not_measured(client, created_component):
    """Inventing a figure for the one strategy this platform cannot see
    would undo the credibility the other two buy."""
    strategies = client.get("/api/v1/reports/circularity").json()["strategies"]
    assert strategies["narrow"]["measured"] is False
    assert "figure" in strategies["narrow"]["note"]
    assert strategies["slow"]["measured"] is True
    assert strategies["close"]["measured"] is True


def test_assumptions_travel_with_the_number(client, created_component):
    """An MCI over estimated mass and placeholder lifetimes is only honest if
    it says so, the same way every mass figure carries its mass_source."""
    body = client.get("/api/v1/reports/circularity").json()
    assert "F_R" in " ".join(body["assumptions"].keys())
    assert body["assumptions"]["recycled_feedstock_fraction_F_R"].startswith("Always 0")
    assert "Prototype estimate" in body["disclaimer"]


def test_unknown_component_is_a_404(client):
    assert client.get("/api/v1/reports/circularity/NOPE-000").status_code == 404


def test_the_circularity_report_cites_its_evidence(client, created_component):
    """Every other disclosure in this codebase names the audit range it was
    derived from. A circularity figure that cannot is a claim, not a
    disclosure."""
    body = client.get("/api/v1/reports/circularity").json()
    derivation = body["derivation"]
    assert "chain_head" in derivation or "audit_entries" in derivation
    assert derivation["re_derivation_note"]
