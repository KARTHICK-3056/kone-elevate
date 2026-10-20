"""The component lifecycle state machine.

Until this module existed, ``Component.current_status`` was a string that
five different call sites assigned to directly, with no notion of which
moves were legal.

A complete component never goes back into service once it is removed: its
route is recovery of its usable sub-components (``PART_RECOVERY``, for
technically suitable lower-demand applications), recovery of its material,
or disposal. There is no edge from any removal state back to ``ACTIVE``.

Deliberately permissive in two places
--------------------------------------
* **Initial state.** Creating a component is not a transition; a caller may
  register a part in any state (a REMOVED part being catalogued
  retrospectively is a real case). ``assert_transition`` is only called
  when a state actually changes.
* **Terminal states stay terminal.** ``MATERIAL_RECOVERED`` and ``DISPOSED`` have no
  outgoing edges. A component whose material has gone to a foundry or a
  landfill does not come back, and a system that let it would be lying in
  a disclosure that an assurance provider is expected to rely on.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Optional

from app.utils.enums import LifecycleStatus

#: Legal destination states for each origin state. Anything absent is
#: rejected by :func:`assert_transition`.
VALID_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    LifecycleStatus.ACTIVE.value: frozenset(
        {
            LifecycleStatus.UNDER_INSPECTION.value,
            LifecycleStatus.REMOVED.value,
        }
    ),
    LifecycleStatus.UNDER_INSPECTION.value: frozenset(
        {
            LifecycleStatus.ACTIVE.value,
            LifecycleStatus.REMOVED.value,
        }
    ),
    LifecycleStatus.REMOVED.value: frozenset(
        {
            LifecycleStatus.RECOVERED.value,
            LifecycleStatus.PART_RECOVERY.value,
            LifecycleStatus.MATERIAL_RECOVERED.value,
            LifecycleStatus.DISPOSED.value,
        }
    ),
    LifecycleStatus.RECOVERED.value: frozenset(
        {
            LifecycleStatus.PART_RECOVERY.value,
            LifecycleStatus.MATERIAL_RECOVERED.value,
            LifecycleStatus.DISPOSED.value,
        }
    ),
    LifecycleStatus.PART_RECOVERY.value: frozenset(
        {
            LifecycleStatus.MATERIAL_RECOVERED.value,
            LifecycleStatus.DISPOSED.value,
        }
    ),
    LifecycleStatus.MATERIAL_RECOVERED.value: frozenset(),
    LifecycleStatus.DISPOSED.value: frozenset(),
}


class InvalidTransitionError(ValueError):
    """A lifecycle move that the state machine does not permit."""

    def __init__(self, from_state: str, to_state: str) -> None:
        allowed = sorted(VALID_TRANSITIONS.get(str(from_state), frozenset()))
        self.from_state = from_state
        self.to_state = to_state
        self.allowed = allowed
        detail = ", ".join(allowed) if allowed else "nothing (terminal state)"
        super().__init__(
            f"Cannot move a component from {from_state} to {to_state}. "
            f"Allowed from {from_state}: {detail}."
        )


def can_transition(from_state: Optional[str], to_state: str) -> bool:
    """Whether ``from_state -> to_state`` is a legal lifecycle move.

    A ``None`` origin means the component is being created, which is an
    initial state rather than a transition, and is always allowed. A move
    to the same state is a no-op and is likewise allowed, so callers can
    invoke this unconditionally.
    """
    if from_state is None or from_state == to_state:
        return True
    return str(to_state) in VALID_TRANSITIONS.get(str(from_state), frozenset())


def assert_transition(from_state: Optional[str], to_state: str) -> None:
    """Raise :class:`InvalidTransitionError` if the move is not permitted."""
    if not can_transition(from_state, to_state):
        raise InvalidTransitionError(str(from_state), str(to_state))
