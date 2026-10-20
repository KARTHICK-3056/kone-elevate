"""Digital Product Passport identity and registry-shaped export.

Construction Products Regulation (EU) 2024/3110 embeds a construction-specific
Digital Product Passport aligned to ESPR. Lift components are construction
products, so the Component Passport is a DPP with a legal definition attached -
provided it carries the things a DPP is required to carry:

* a **persistent, unique identifier** that outlives any server,
* a **resolvable** data carrier (the QR payload),
* the **economic operator** a market-surveillance authority contacts,
* a declared **schema version**, so a passport read in 2031 can be interpreted.

Identifier design
-----------------
``urn:kone:dpp:{version}:{component_id}`` is the identity and never changes.
Resolution is deliberately a separate concern: the URN is printed on the label,
and ``DPP_RESOLVER_BASE_URL`` says where it currently resolves. Replacing the
resolver - or registering with the EU DPP Registry when access exists - does
not invalidate a single printed label.

Honest status
-------------
``registry_status`` reports NOT_REGISTERED. No economic operator is assigned,
and this build has no EU DPP Registry credentials, so the export is
*registry-shaped* rather than registry-accepted. It is structured to be
submittable; it has not been submitted.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml import life_model
from app.models.component import Component
from app.services import audit_service, impact_service, material_flow_service
from app.utils import standards
from app.utils.enums import (
    RECOMMENDATION_DISCLAIMER,
    SYNTHETIC_DATA_NOTICE,
    is_safety_critical,
)
from app.utils.helpers import utcnow

REGISTRY_NOT_REGISTERED = "NOT_REGISTERED"
REGISTRY_REGISTERED = "REGISTERED"


def default_identifier(component_id: str) -> str:
    """The identifier this platform issues for a component."""
    return f"{settings.DPP_ID_NAMESPACE}:{settings.DPP_SCHEMA_VERSION}:{component_id}"


def dpp_identifier(component: Component | str) -> str:
    """The persistent, versioned identifier printed on the component label.

    Accepts a component (preferring an identifier issued elsewhere and stored
    on the row) or a bare component id.
    """
    if isinstance(component, str):
        return default_identifier(component)
    return getattr(component, "dpp_id", None) or default_identifier(component.component_id)


def resolver_url(component: Component | str) -> str:
    """Where the identifier currently resolves.

    This is what the QR code encodes. It is a stable public host rather than a
    development server, because a label printed today must still resolve after
    the demo is switched off.
    """
    return f"{settings.DPP_RESOLVER_BASE_URL.rstrip('/')}/{dpp_identifier(component)}"


def parse_identifier(value: str) -> Optional[str]:
    """Recover a component id from a DPP URN or resolver URL.

    Returns ``None`` for anything that is not a DPP identifier, so the QR
    scanner can fall back to its older bare-id and passport-URL formats.
    """
    if not value:
        return None
    candidate = value.strip()
    namespace = f"{settings.DPP_ID_NAMESPACE}:"
    if namespace in candidate:
        tail = candidate.split(namespace, 1)[1]
        parts = tail.split(":")
        return parts[-1] or None
    return None


def identity_summary(component: Component) -> Dict[str, Any]:
    """The passport-header view: identifier, carrier and registry honesty."""
    registered = bool(settings.DPP_RESOLVER_REGISTERED)
    return {
        "dpp_id": dpp_identifier(component),
        "schema_version": settings.DPP_SCHEMA_VERSION,
        "resolver_url": resolver_url(component),
        "registry_status": REGISTRY_REGISTERED if registered else REGISTRY_NOT_REGISTERED,
        "economic_operator": economic_operator(component),
        "export_url": (
            f"{settings.API_V1_PREFIX}/passports/{component.component_id}/dpp"
        ),
        "regulation": "Regulation (EU) 2024/3110 (CPR), ESPR-aligned",
    }


def economic_operator(component: Component) -> Dict[str, Any]:
    """The CPR economic operator responsible for this product."""
    name = getattr(component, "economic_operator", None) or settings.DPP_ECONOMIC_OPERATOR
    identifier = (
        getattr(component, "economic_operator_id", None) or settings.DPP_ECONOMIC_OPERATOR_ID
    )
    return {
        "name": name,
        "identifier": identifier or None,
        "identifier_scheme": "EORI" if identifier else None,
        "role": settings.DPP_ECONOMIC_OPERATOR_ROLE,
        "address": settings.DPP_ECONOMIC_OPERATOR_ADDRESS or None,
        "assigned": bool(identifier),
        "note": (
            None
            if identifier
            else (
                "No economic operator is assigned. CPR (EU) 2024/3110 requires "
                "one before a passport may be placed on the market."
            )
        ),
    }


def material_composition(component: Component) -> Dict[str, Any]:
    """Declared material content, with the provenance of the mass figure."""
    mass_kg, mass_source = material_flow_service.resolve_mass(component)
    crm = settings.CRM_MASS_FRACTION.get(str(component.material), {})
    return {
        "primary_material": component.material,
        "mass_kg": round(mass_kg, 3),
        "mass_source": mass_source,
        "critical_raw_materials": [
            {
                "substance": substance,
                "mass_fraction": float(fraction),
                "mass_kg": round(mass_kg * float(fraction), 4),
            }
            for substance, fraction in sorted(
                crm.items(), key=lambda item: item[1], reverse=True
            )
        ],
        "crm_list_reference": settings.CRM_LIST_REFERENCE,
        "grade": life_model.material_profile(component),
        "basis": (
            "Per-material average fractions from configuration. PROTOTYPE "
            "ESTIMATES, not a supplier bill of materials."
        ),
    }


def lifecycle_record(db: Session, component: Component) -> List[Dict[str, Any]]:
    """The component's material-flow history, as passport lifecycle events."""
    return [
        {
            "date": flow.flow_date.isoformat(),
            "from_state": flow.from_state,
            "to_state": flow.to_state,
            "boundary_effect": flow.direction,
            "treatment_route": flow.outflow_route,
            "mass_kg": round(flow.mass_kg, 3),
            "audit_hash": flow.audit_hash,
        }
        for flow in material_flow_service.history_for_component(db, component.component_id)
    ]


def registry_export(db: Session, component: Component) -> Dict[str, Any]:
    """A registry-shaped DPP document for one component.

    Shaped for CPR (EU) 2024/3110 / ESPR: identity and data carrier, economic
    operator, product characteristics, material composition including critical
    raw materials, the standards the product is assessed against, its lifecycle
    record, and the tamper-evidence that backs all of it.
    """
    audit_entries = audit_service.list_for_entity(
        db, "component", component.component_id, limit=500
    )
    latest = component.latest_prediction
    registered = bool(settings.DPP_RESOLVER_REGISTERED)

    return {
        "schema": "kone-elevate/dpp",
        "schema_version": settings.DPP_SCHEMA_VERSION,
        "mapped_to": "Regulation (EU) 2024/3110 (CPR) Digital Product Passport, ESPR-aligned",
        "identification": {
            "dpp_id": dpp_identifier(component),
            "product_id": component.component_id,
            "serial_number": component.serial_number,
            "data_carrier": {
                "type": "QR",
                "payload": resolver_url(component),
                "persistent_identifier": dpp_identifier(component),
            },
            "registry_status": REGISTRY_REGISTERED if registered else REGISTRY_NOT_REGISTERED,
            "registry_note": (
                None
                if registered
                else (
                    "Not registered with the EU DPP Registry. This build has no "
                    "registry credentials, so the export is registry-shaped, not "
                    "registry-accepted, and the resolver host is a documented "
                    "placeholder."
                )
            ),
        },
        "economic_operator": economic_operator(component),
        "product": {
            "component_type": component.component_type,
            "material": component.material,
            "material_grade": life_model.grade_label(component),
            "manufacturer": component.manufacturer,
            "place_of_origin": component.origin,
            "placed_in_service": (
                component.installation_date.isoformat() if component.installation_date else None
            ),
            "installed_at": component.location,
            "age_years": component.component_age,
            "lifecycle_status": component.current_status,
            "safety_component": is_safety_critical(component.component_type),
        },
        "material_composition": material_composition(component),
        "standards_basis": standards.standards_summary(component.component_type),
        "condition_assessment": {
            "health_score": component.health_score,
            "inspection_score": component.inspection_score,
            "latest_recommendation": latest.recommendation if latest else None,
            "latest_confidence": latest.confidence if latest else None,
            "model_version": latest.model_version if latest else None,
            "assessed_at": latest.predicted_at.isoformat() if latest else None,
            "disclaimer": RECOMMENDATION_DISCLAIMER,
        },
        "life_projection": life_model.projection_summary(life_model.assess(component)),
        "lifecycle_record": lifecycle_record(db, component),
        "circularity": impact_service.component_impact(
            component.component_type,
            component.material,
            latest.recommendation if latest else None,
        ),
        "tamper_evidence": {
            "scheme": "SHA-256 hash chain",
            "audit_records": len(audit_entries),
            "head_hash": audit_entries[0].current_hash if audit_entries else None,
            "verify_endpoint": f"{settings.API_V1_PREFIX}/audit/verify",
        },
        "data_notice": SYNTHETIC_DATA_NOTICE,
        "generated_at": utcnow().isoformat(),
    }
