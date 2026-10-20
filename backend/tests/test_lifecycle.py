"""The component lifecycle state machine (app.utils.lifecycle).

Once a component is removed, its only routes are recovery of its usable
sub-components (PART_RECOVERY), recovery of its material, or disposal. A
complete component never returns to service, and nothing books it as a
secondary inflow.
"""

from __future__ import annotations

import pytest

from app.utils.enums import LifecycleStatus, ServiceEventType
from app.utils.lifecycle import InvalidTransitionError, assert_transition, can_transition

REMOVAL_STATES = (
    LifecycleStatus.REMOVED.value,
    LifecycleStatus.RECOVERED.value,
    LifecycleStatus.PART_RECOVERY.value,
    LifecycleStatus.MATERIAL_RECOVERED.value,
    LifecycleStatus.DISPOSED.value,
)


@pytest.mark.parametrize("state", REMOVAL_STATES)
def test_a_removed_component_never_returns_to_service(state):
    assert not can_transition(state, LifecycleStatus.ACTIVE.value)
    with pytest.raises(InvalidTransitionError):
        assert_transition(state, LifecycleStatus.ACTIVE.value)


def test_an_inspection_can_return_a_part_to_service():
    """Inspection is not removal: a part that passes stays in its lift."""
    assert can_transition(LifecycleStatus.UNDER_INSPECTION.value, LifecycleStatus.ACTIVE.value)


def test_part_recovery_ends_in_material_recovery_or_disposal():
    assert can_transition(LifecycleStatus.REMOVED.value, LifecycleStatus.PART_RECOVERY.value)
    assert can_transition(LifecycleStatus.PART_RECOVERY.value, LifecycleStatus.MATERIAL_RECOVERED.value)
    assert can_transition(LifecycleStatus.PART_RECOVERY.value, LifecycleStatus.DISPOSED.value)


def test_terminal_states_stay_terminal():
    for terminal in (LifecycleStatus.MATERIAL_RECOVERED.value, LifecycleStatus.DISPOSED.value):
        for target in LifecycleStatus.values():
            if target != terminal:
                assert not can_transition(terminal, target)


def test_creation_and_no_op_are_not_transitions():
    assert can_transition(None, LifecycleStatus.REMOVED.value)
    assert can_transition(LifecycleStatus.MATERIAL_RECOVERED.value, LifecycleStatus.MATERIAL_RECOVERED.value)


def test_the_exchange_states_and_event_are_gone():
    for removed in ("AVAILABLE", "ALLOCATED", "PARTS_FITTED"):
        assert removed not in LifecycleStatus.values()
    assert "PARTS_FITTED" not in ServiceEventType.values()


def test_a_removed_component_cannot_be_set_back_to_active_by_hand(client, created_component):
    component_id = created_component["component_id"]
    removed = client.put(
        f"/api/v1/components/{component_id}", json={"current_status": LifecycleStatus.REMOVED.value}
    )
    assert removed.status_code == 200
    refit = client.put(
        f"/api/v1/components/{component_id}", json={"current_status": LifecycleStatus.ACTIVE.value}
    )
    assert refit.status_code == 409


def test_the_recovery_exchange_api_is_gone(client):
    assert client.get("/api/v1/recovery/items").status_code == 404
    assert client.get("/api/v1/recovery/summary").status_code == 404
