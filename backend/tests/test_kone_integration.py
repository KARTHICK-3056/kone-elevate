"""KONE-backed adapters (K-1) and the apportionment layer (K-2).

No KONE credentials exist in this build and no live call has ever been
made, so what these tests can and cannot establish needs stating plainly:

* **Covered.** The mapping from KONE's published response shapes onto this
  platform's domain types, driven through the same adapter code the HTTP
  client would feed. That is where a misreading of the published schema
  actually does damage, and the fixtures use KONE's real field names
  (``failedComponentCode``, ``equipmentConditionOnDeparture``, ...) rather
  than the generic shapes this build invented before seeing the API.
* **Not covered.** Anything only a live call can prove: a documented field
  the service omits, a pagination envelope the examples do not show, an
  auth scope that turns out to be insufficient, rate limits.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.integrations import kone_adapters, kone_client, kone_features, registry
from app.integrations.kone_client import RecordedKoneApiClient
from app.utils.enums import ComponentType

KEN = "ken:38999833"


def _client():
    return RecordedKoneApiClient()


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------
def test_ken_normalisation_accepts_both_spellings():
    assert kone_client.normalise_ken("38999833") == KEN
    assert kone_client.normalise_ken(KEN) == KEN


def test_scopes_are_per_equipment():
    """A token minted for one KEN is not valid for another, which is why the
    client caches per scope set rather than globally."""
    assert kone_client.equipment_scope("38999833", "serviceinfo") == f"serviceinfo/{KEN}"
    assert kone_client.equipment_scope(KEN, "rtm") == f"rtm/{KEN}"


def test_paths_match_the_published_reference_implementation():
    assert kone_client.service_orders_path(KEN) == f"/api/v2/equipment/{KEN}/serviceOrders"
    assert (
        kone_client.service_order_path(KEN, "SO-1")
        == f"/api/v2/equipment/{KEN}/serviceOrders/SO-1"
    )


# --------------------------------------------------------------------------
# K-1: the adapters, against KONE's real field names
# --------------------------------------------------------------------------
def test_equipment_identity_maps_from_kone_shapes():
    identity = kone_adapters.KoneEquipmentIdentityAdapter(_client()).get_equipment(KEN)
    assert identity is not None
    assert identity.equipment_id == KEN
    assert identity.equipment_type == "ELEVATOR"
    assert identity.site_address and "Chennai" in identity.site_address
    assert identity.status == "IN_SERVICE"


def test_installation_date_is_none_because_kone_publishes_none():
    """Back-deriving it from the first service order would be a guess wearing
    a date's clothes, and every downstream age calculation would inherit it."""
    identity = kone_adapters.KoneEquipmentIdentityAdapter(_client()).get_equipment(KEN)
    assert identity.installation_date is None


def test_equipment_for_a_different_ken_is_not_returned_as_this_one():
    adapter = kone_adapters.KoneEquipmentIdentityAdapter(
        RecordedKoneApiClient({"/api/v2/equipment/search/status": {"equipmentId": "ken:11111111"}})
    )
    assert adapter.get_equipment(KEN) is None


def test_unknown_equipment_returns_none_not_an_error():
    """'Unknown id' is an expected outcome, not an integration fault - the
    distinction base.AdapterError exists to preserve."""
    adapter = kone_adapters.KoneEquipmentIdentityAdapter(RecordedKoneApiClient({}))
    assert adapter.get_equipment(KEN) is None


def test_service_records_map_from_kone_service_orders():
    records = kone_adapters.KoneServiceRecordAdapter(_client()).list_service_records(KEN)
    assert len(records) == 4
    # Newest first.
    assert records[0].performed_at >= records[-1].performed_at
    assert {r.event_type for r in records} == {"MAINTENANCE", "REPAIR", "MODERNIZATION"}


def test_the_failed_component_code_survives_the_mapping():
    """It is the only component-level signal anywhere in KONE's public API.
    Dropping it in the mapping would throw away the most valuable field the
    Service Info API has."""
    records = kone_adapters.KoneServiceRecordAdapter(_client()).list_service_records(KEN)
    notes = " ".join(r.notes or "" for r in records)
    assert "DOOR_OPERATOR" in notes
    assert "Action: REPLACED" in notes


def test_since_filters_history():
    adapter = kone_adapters.KoneServiceRecordAdapter(_client())
    cutoff = datetime(2026, 6, 1, tzinfo=timezone.utc)
    recent = adapter.list_service_records(KEN, since=cutoff)
    assert recent and all(r.performed_at >= cutoff for r in recent)
    assert len(recent) < len(adapter.list_service_records(KEN))


def test_a_naive_since_does_not_raise():
    """Callers inside this codebase pass naive UTC datetimes; KONE returns
    offsets. Comparing them used to be a TypeError waiting to happen."""
    adapter = kone_adapters.KoneServiceRecordAdapter(_client())
    assert adapter.list_service_records(KEN, since=datetime(2026, 6, 1)) is not None


def test_an_undated_order_is_dropped_rather_than_guessed():
    client = RecordedKoneApiClient(
        {
            f"/api/v2/equipment/{KEN}/serviceOrders": [{"serviceOrderNumber": "SO-X"}],
            f"/api/v2/equipment/{KEN}/serviceOrders/SO-X": {"activityType": "REPAIR"},
        }
    )
    assert kone_adapters.KoneServiceRecordAdapter(client).list_service_records(KEN) == []


def test_kone_adapters_satisfy_the_existing_contract_tests():
    """The contract functions written in P5 for *any* implementation, now run
    against the KONE-backed ones - which is what they were written for."""
    from tests.test_integrations import (  # noqa: PLC0415 - reuse, not duplication
        assert_equipment_identity_contract,
        assert_service_record_contract,
    )

    assert_equipment_identity_contract(
        kone_adapters.KoneEquipmentIdentityAdapter(_client()),
        known_id=KEN,
        unknown_id="ken:00000000",
    )
    assert_service_record_contract(
        kone_adapters.KoneServiceRecordAdapter(_client()),
        known_equipment_id=KEN,
        unknown_equipment_id="ken:00000000",
    )


def test_registry_reports_its_own_provenance():
    """Without credentials the fixtures answer, and the status says so
    rather than letting a caller assume a figure came from KONE."""
    status = registry.integration_status()
    assert status["kone_api_configured"] is False
    assert status["adapters"]["service_records"] == "fixture"
    assert status["live_call_ever_made"] is False
    # Spare parts can never be anything else - there is no KONE API for it.
    assert status["adapters"]["spare_parts"] == "fixture"


# --------------------------------------------------------------------------
# K-2: apportionment
# --------------------------------------------------------------------------
def test_failed_component_code_maps_onto_our_taxonomy():
    assert kone_features.map_failed_component("DOOR_OPERATOR") == ComponentType.DOOR_OPERATOR.value
    assert kone_features.map_failed_component("traction_sheave") == ComponentType.SHEAVE.value
    assert kone_features.map_failed_component("SOMETHING_ELSE") is None
    assert kone_features.map_failed_component(None) is None


def _derive(component_type):
    telemetry = kone_adapters.equipment_telemetry(KEN, _client())
    orders = kone_adapters.service_order_details(KEN, _client())
    return kone_features.derive_features(component_type, telemetry, orders)


def test_duty_is_apportioned_differently_per_component_type():
    """A door operator actuates twice per journey; a motor once. If both came
    out identical the apportionment would be decorative."""
    door = _derive(ComponentType.DOOR_OPERATOR.value)
    motor = _derive(ComponentType.MOTOR.value)
    assert door["features"]["load_cycles"] > motor["features"]["load_cycles"]
    # ...and the door operator is only under load while the doors move.
    assert door["features"]["operating_hours"] < motor["features"]["operating_hours"]


def test_every_feature_states_where_it_came_from():
    derived = _derive(ComponentType.MOTOR.value)
    for name, entry in derived["provenance"].items():
        assert entry["source"] in {"measured", "apportioned", "derived", "unavailable"}, name
        assert entry["note"], name


def test_apportioned_features_say_they_are_assumptions():
    derived = _derive(ComponentType.DOOR_OPERATOR.value)
    assert derived["provenance"]["load_cycles"]["source"] == "apportioned"
    assert derived["provenance"]["operating_hours"]["source"] == "apportioned"


def test_service_history_is_derived_from_real_orders():
    derived = _derive(ComponentType.MOTOR.value)
    features = derived["features"]
    assert features["service_count"] == 4
    assert features["repair_count"] == 2  # one CALLOUT + one REPAIR
    assert features["failure_history"] == 2  # two carry an equipmentFailureReason
    assert features["days_since_last_service"] >= 0


def test_vibration_and_temperature_are_never_invented():
    """No KONE feed carries either. Substituting a default would make a
    prediction built on an invented safety-relevant reading
    indistinguishable from one built on a measurement."""
    derived = _derive(ComponentType.MOTOR.value)
    for name in ("vibration", "temperature"):
        assert derived["features"][name] is None
        assert derived["provenance"][name]["source"] == "unavailable"
    assert set(kone_features.UNAVAILABLE_FEATURES) <= set(
        kone_features.missing_for_model(derived)
    )


def test_coverage_reports_how_much_of_the_vector_is_real():
    """The figure that could not exist while every feature came from the
    same synthetic generator."""
    coverage = _derive(ComponentType.MOTOR.value)["coverage"]
    assert coverage["fields"] > 0
    assert 0 < coverage["grounded_percent"] < 100, (
        "some features are real and some have no source - neither extreme is honest here"
    )


def test_average_load_is_labelled_a_percentage_not_kilograms():
    """KONE publishes loadPercentage and no rated-load field. The model's
    `average_load` is in kg, so this mismatch has to be stated or a 46%
    load silently becomes 46 kg."""
    derived = _derive(ComponentType.MOTOR.value)
    assert "PERCENTAGE" in derived["provenance"]["average_load"]["note"]


def test_inspection_score_admits_it_describes_the_lift():
    derived = _derive(ComponentType.SHEAVE.value)
    note = derived["provenance"]["inspection_score"]["note"]
    assert derived["features"]["inspection_score"] == 90.0  # newest order departed at code "1"
    assert "LIFT" in note


def test_every_component_type_has_an_apportionment_rationale():
    """A factor with no stated reasoning is a magic number, and this table is
    the assumption the honesty of the whole layer rests on."""
    for component_type in ComponentType.values():
        share = kone_features.APPORTIONMENT[component_type]
        assert share["rationale"]
        assert share["hours"] > 0 and share["cycles"] > 0


# --------------------------------------------------------------------------
# The HTTP transport, against a local stub speaking the documented protocol
# --------------------------------------------------------------------------
def test_http_client_speaks_the_documented_oauth_and_rest_protocol():
    """Exercises the one part a recorded client cannot: the wire format.

    This is NOT a live KONE call and proves nothing about KONE's real
    service. What it does prove is that this client sends what KONE's
    reference implementation documents - HTTP Basic client credentials, a
    form-encoded `grant_type`/`scope` body, then a Bearer GET - rather than
    something that would 400 on first contact. Without it the entire
    transport shipped with zero coverage.
    """
    import base64  # noqa: PLC0415 - test-local
    import json  # noqa: PLC0415
    import threading  # noqa: PLC0415
    import urllib.parse  # noqa: PLC0415
    from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: PLC0415

    seen = {"token_requests": 0, "auth_header": None, "scope": None, "bearer": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the suite's output clean
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            seen["token_requests"] += 1
            seen["auth_header"] = self.headers.get("Authorization")
            seen["scope"] = urllib.parse.parse_qs(body).get("scope", [None])[0]
            payload = json.dumps({"access_token": "tok-abc", "expires_in": 3600}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            seen["bearer"] = self.headers.get("Authorization")
            if self.path.endswith("/missing"):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            payload = json.dumps([{"serviceOrderNumber": "SO-1"}]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        client = kone_client.HttpKoneApiClient(
            "id-1", "secret-1", timeout=5, base_url=base
        )
        scopes = [kone_client.equipment_scope(KEN, "serviceinfo")]

        # The REAL get(), not a re-implementation of it.
        result = client.get(kone_client.service_orders_path(KEN), scopes)
        assert result == [{"serviceOrderNumber": "SO-1"}]

        # HTTP Basic client credentials, exactly as the reference sends them.
        expected = base64.b64encode(b"id-1:secret-1").decode()
        assert seen["auth_header"] == f"Basic {expected}"
        # A per-equipment scope, not a global one.
        assert seen["scope"] == f"serviceinfo/{KEN}"
        assert seen["bearer"] == "Bearer tok-abc"

        # A second call for the same scope must reuse the cached token.
        client.get(kone_client.service_orders_path(KEN), scopes)
        assert seen["token_requests"] == 1, "token was not cached per scope set"

        # A different KEN needs its own token - the scope is part of the key.
        client.get("/api/v2/equipment/ken:1/serviceOrders", ["serviceinfo/ken:1"])
        assert seen["token_requests"] == 2, "token cache ignored the scope set"

        # 404 is "not found", not an integration fault.
        assert client.get("/missing", scopes) is None
    finally:
        server.shutdown()
        server.server_close()


# --------------------------------------------------------------------------
# K-3: harvesting weak disposition labels
# --------------------------------------------------------------------------
def test_a_part_left_in_service_is_an_observed_label():
    """`ADJUSTED` with the equipment departing operational is a directly
    observed decision to keep the component - the one thing this source
    genuinely sees."""
    from app.integrations import kone_labels  # noqa: PLC0415
    from app.utils.enums import WorkshopOutcome  # noqa: PLC0415

    label = kone_labels.derive_label(
        {
            "serviceOrderNumber": "SO-1",
            "technicianActionCode": "ADJUSTED",
            "equipmentConditionOnDeparture": "2",
            "finishedDateTime": "2026-05-02T20:40:00Z",
        }
    )
    assert label["outcome"] == WorkshopOutcome.CONTINUED_IN_SERVICE.value
    assert label["confidence"] == "observed"
    assert label["weight"] == 1.0


def test_a_replacement_with_no_failure_is_censored_not_guessed():
    """The single most important behaviour in this module. KONE publishes
    nothing about where a removed part went, so refurbish / recycle /
    dispose are indistinguishable - and inventing one would poison the only
    real-label channel this platform has."""
    from app.integrations import kone_labels  # noqa: PLC0415

    label = kone_labels.derive_label(
        {
            "serviceOrderNumber": "SO-2",
            "technicianActionCode": "REPLACED",
            "equipmentConditionOnDeparture": "1",
            "finishedDateTime": "2026-06-20T12:10:00Z",
        }
    )
    assert label["outcome"] is None
    assert label["confidence"] == "unknown"
    assert label["weight"] == 0.0
    assert "not published" in label["reason"] or "no disposition" in label["reason"].lower()


def test_a_replacement_after_a_failure_is_inferred_and_down_weighted():
    from app.integrations import kone_labels  # noqa: PLC0415
    from app.utils.enums import WorkshopOutcome  # noqa: PLC0415

    label = kone_labels.derive_label(
        {
            "serviceOrderNumber": "SO-3",
            "technicianActionCode": "REPLACED",
            "equipmentFailureReason": "DOOR_OPERATOR_WEAR",
            "equipmentConditionOnArrivalDesc": "DEGRADED",
            "finishedDateTime": "2026-06-20T12:10:00Z",
        }
    )
    assert label["outcome"] == WorkshopOutcome.FAILED_INSPECTION.value
    assert label["confidence"] == "inferred"
    assert label["weight"] < 1.0
    # It labels the component's CONDITION, not its disposition - and says so.
    assert "disposition" in label["reason"]


def test_coverage_reports_the_censoring_rather_than_hiding_it():
    """Reporting only the labels that came out would make a source blind to
    every disposal route look like a usable training set."""
    from app.integrations import kone_labels  # noqa: PLC0415

    orders = kone_adapters.service_order_details(KEN, _client())
    coverage = kone_labels.label_coverage(kone_labels.harvest(orders))

    assert coverage["usable_for_training"] is False
    assert coverage["censored"] >= 1
    # The disposal classes are exactly what this source cannot see.
    assert "MATERIAL_RECOVERED" in coverage["classes_never_observed"]
    assert "DISPOSED" in coverage["classes_never_observed"]
    assert "optimistic" in coverage["structural_limitation"]


def test_censored_observations_are_excluded_from_agreement_not_scored_as_misses():
    """A removal whose destination nobody recorded is missing data. Scoring
    it as a disagreement would understate the model on precisely the cases
    this source cannot observe."""
    from app.integrations import kone_labels  # noqa: PLC0415

    orders = kone_adapters.service_order_details(KEN, _client())
    labels = kone_labels.harvest(orders)
    scoreable = kone_labels.agreement_input(labels)

    assert all(label["outcome"] and label["weight"] > 0 for label in scoreable)
    assert len(scoreable) < len(labels)


def test_harvested_labels_use_the_vocabulary_the_p6_report_already_consumes():
    """The point of matching WorkshopOutcome exactly: these feed the
    existing agreement machinery rather than a parallel invention."""
    from app.integrations import kone_labels  # noqa: PLC0415
    from app.services.agreement_service import COMPATIBLE_OUTCOMES  # noqa: PLC0415

    known = {outcome for outcomes in COMPATIBLE_OUTCOMES.values() for outcome in outcomes}
    known.add("FAILED_INSPECTION")
    orders = kone_adapters.service_order_details(KEN, _client())
    for label in kone_labels.agreement_input(kone_labels.harvest(orders)):
        assert label["outcome"] in known


def test_the_condition_code_direction_check_detects_an_inversion():
    """The riskiest assumption in the integration, and the only one whose
    failure mode is completely silent: if KONE's codes run the other way,
    every inspection score inverts with no error and no crash."""
    consistent = [
        {"equipmentConditionOnArrival": "4", "equipmentFailureReason": "X"},
        {"equipmentConditionOnArrival": "4", "equipmentFailureReason": "Y"},
        {"equipmentConditionOnArrival": "3", "equipmentFailureReason": "Z"},
        {"equipmentConditionOnArrival": "1"},
        {"equipmentConditionOnArrival": "1"},
        {"equipmentConditionOnArrival": "2"},
    ]
    assert kone_features.validate_condition_code_direction(consistent)["verdict"] == "consistent"

    inverted = [
        {"equipmentConditionOnArrival": "1", "equipmentFailureReason": "X"},
        {"equipmentConditionOnArrival": "1", "equipmentFailureReason": "Y"},
        {"equipmentConditionOnArrival": "2", "equipmentFailureReason": "Z"},
        {"equipmentConditionOnArrival": "4"},
        {"equipmentConditionOnArrival": "4"},
        {"equipmentConditionOnArrival": "3"},
    ]
    verdict = kone_features.validate_condition_code_direction(inverted)
    assert verdict["verdict"] == "SUSPECT_INVERTED"
    assert "inverted" in verdict["note"].lower()


def test_the_check_refuses_to_conclude_from_too_little_data():
    """A check that cried wolf on four fixture rows would get switched off."""
    orders = kone_adapters.service_order_details(KEN, _client())
    assert (
        kone_features.validate_condition_code_direction(orders)["verdict"]
        == "insufficient_data"
    )


def test_harvested_labels_score_through_the_p6_agreement_definitions():
    """Closes the K-3 bullet: 'feed it into the P6 agreement report'.

    The point is that "agreement" means one thing in this codebase -
    score_weak_labels reuses COMPATIBLE_OUTCOMES and
    OPTIMISTIC_RECOMMENDATIONS rather than defining its own.
    """
    from app.integrations import kone_labels  # noqa: PLC0415
    from app.services import agreement_service  # noqa: PLC0415

    orders = kone_adapters.service_order_details(KEN, _client())
    labels = kone_labels.harvest(orders)

    pairs = [{"recommendation": "CONTINUE_USING", "label": label} for label in labels]
    report = agreement_service.score_weak_labels(pairs)

    # The censored order is excluded, not scored as a miss.
    assert report["scored"] == 3
    assert report["censored_or_unusable"] == 1
    # CONTINUE_USING agrees with CONTINUED_IN_SERVICE (x2) and disagrees with FAILED_INSPECTION.
    assert report["unweighted_agreement_rate"] == round(2 / 3, 4)
    # Weighted: the disagreement is an `inferred` label worth 0.4, so the
    # weighted rate must be higher than the unweighted one.
    assert report["weighted_agreement_rate"] > report["unweighted_agreement_rate"]
    assert report["optimistic_misses"] == 1
    assert "censored on every disposal class" in report["caveat"]


def test_weak_label_scoring_never_masquerades_as_the_pilot_rate():
    """These are harvested, not recorded. Folding them into the workshop
    agreement rate would launder an inference into an observation."""
    from app.services import agreement_service  # noqa: PLC0415

    report = agreement_service.score_weak_labels([])
    assert report["label_source"] == "kone-service-orders"
    assert "not a substitute" in report["caveat"]


def test_an_abstention_is_not_scored_against_a_weak_label_either():
    from app.integrations import kone_labels  # noqa: PLC0415
    from app.services import agreement_service  # noqa: PLC0415

    label = kone_labels.derive_label(
        {
            "serviceOrderNumber": "SO-A",
            "technicianActionCode": "INSPECTED",
            "equipmentConditionOnDeparture": "1",
            "finishedDateTime": "2026-05-02T20:40:00Z",
        }
    )
    report = agreement_service.score_weak_labels(
        [{"recommendation": "DEFER_TO_INSPECTION", "label": label}]
    )
    assert report["scored"] == 0
    assert report["rows"][0]["verdict"] == "ABSTAINED"
