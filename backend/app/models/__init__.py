"""ORM model registry.

Importing this package registers every mapper with the declarative Base, which
is required before ``Base.metadata.create_all()`` or an Alembic autogenerate
run can see the full schema.
"""

from app.models.audit import AuditChainLock, AuditLog, ChainAnchor
from app.models.component import Component
from app.models.material_flow import MaterialFlow
from app.models.prediction import Prediction
from app.models.service_event import ServiceEvent
from app.models.simulation import SimulationScenario
from app.models.telemetry import TelemetryReading
from app.models.user import User
from app.models.verification import EmailVerification

__all__ = [
    "AuditChainLock",
    "AuditLog",
    "ChainAnchor",
    "Component",
    "EmailVerification",
    "MaterialFlow",
    "Prediction",
    "ServiceEvent",
    "SimulationScenario",
    "TelemetryReading",
    "User",
]
