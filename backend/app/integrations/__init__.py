"""Anti-corruption layer for KONE's own systems (P5).

This package defines the *shape* this application needs from three external
capabilities - equipment identity, service-record history, and spare-parts
availability - as Python interfaces, plus one concrete implementation of
each that reads from recorded fixtures instead of a live system.

Why an anti-corruption layer at all
------------------------------------
The plan is explicit: "Build to the documented APIs; do not assume internals
you cannot see." Nothing in the rest of this codebase should import a KONE
SDK, a KONE-shaped response object, or a KONE endpoint URL directly - it
depends only on the interfaces in ``base.py``. Swapping the fixture-backed
adapters for ones that call KONE's real API Portal sandbox is meant to be a
change entirely inside this package.

What is, and is not, done here
--------------------------------
**Not done:** no KONE API Portal sandbox application was registered (that
needs a real developer account this build has no access to), so no live
call to a KONE system has ever been made, and the exact response shapes
below are this build's own reasonable, generic modelling of "equipment
identity" / "service record" / "spare part" - not a copy of KONE's actual
published schema, which was never seen. Treat the field names as
illustrative until validated against the real API Portal documentation.

**Done:** the interfaces, a fixture-backed implementation of each, and
contract tests (``tests/test_integrations.py``) that any future real
adapter must also pass. See ``docs/kone-integration.md``.
"""
