"""Manufacturer quality certificate on the passport."""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

import pytest

from app.services import quality_certificate_service as certificates


def _component(component_type: str, material: str, component_id: str = "KE-TST-000001"):
    return SimpleNamespace(
        component_id=component_id,
        component_type=component_type,
        material=material,
        material_grade=None,
        serial_number="SN-TEST-1",
        manufacturer="Test Manufacturer",
        origin="Chennai Plant",
        installation_date=date(2021, 6, 1),
    )


MAIN = [("Motor", "Steel"), ("Steel Rope", "Steel"), ("Sheave", "Cast Iron"), ("Governor", "Cast Iron")]


@pytest.mark.parametrize(("component_type", "material"), MAIN)
def test_every_main_type_gets_a_certificate_that_says_it_is_a_sample(component_type, material):
    certificate = certificates.build(_component(component_type, material))
    assert certificate["certificate_type"].startswith("Inspection certificate type 3.1")
    assert certificate["notice"] == certificates.SAMPLE_NOTICE
    assert certificate["tests"] and all(test["verdict"] == "Pass" for test in certificate["tests"])
    assert certificate["materials"], "per-part material certification comes from the grade specification"
    # Issued before dispatch, i.e. before the installation date.
    assert date.fromisoformat(certificate["date_of_issue"]) < date(2021, 6, 1)


def test_the_same_component_always_gets_the_same_certificate():
    first = certificates.build(_component("Governor", "Cast Iron", "KE-GOV-000123"))
    again = certificates.build(_component("Governor", "Cast Iron", "KE-GOV-000123"))
    other = certificates.build(_component("Governor", "Cast Iron", "KE-GOV-000124"))
    assert first == again
    assert first["certificate_no"] != other["certificate_no"]


@pytest.mark.parametrize("n", range(20))
def test_governor_trips_inside_the_en_81_20_window(n):
    certificate = certificates.build(_component("Governor", "Steel", f"KE-GOV-{n:06d}"))
    trip = certificate["tests"][0]
    low, high = (float(x) for x in re.findall(r"(\d+\.\d+) - (\d+\.\d+)", trip["requirement"])[0])
    measured = float(trip["result"].split()[0])
    assert low <= measured <= high
    switch = float(re.search(r"(\d+\.\d+)", certificate["tests"][1]["result"]).group(1))
    assert switch < measured


def test_sheave_results_follow_the_recorded_grade():
    component = _component("Sheave", "Steel")
    component.material_grade = "hardened_steel"
    hardness = certificates.build(component)["tests"][0]
    assert "HRC" in hardness["result"] and 40 <= int(hardness["result"].split()[0]) <= 50


def test_types_outside_the_four_main_parts_have_no_certificate():
    assert certificates.build(_component("Brake", "Steel")) is None


def test_passport_api_carries_the_certificate(client, created_component):
    body = client.get(f"/api/v1/passports/{created_component['component_id']}").json()
    assert body["quality_certificate"]["product"]["component_id"] == created_component["component_id"]
