"""KONE ELEVATE - FastAPI application entry point.

Component Passport: AI-powered circular-economy platform for elevator
component lifecycle management.

PROTOTYPE NOTICE
----------------
This application is a decision-support prototype built for a hackathon by
Team CodeFather (SRM Institute of Science and Technology, Ramapuram). It is
trained on synthetic degradation data, it is not affiliated with or endorsed
by KONE Corporation, and no AI output in this system constitutes a
certification, approval or authorisation to operate an elevator.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api import (
    audit,
    auth,
    compliance,
    components,
    dashboard,
    field_data,
    forecast,
    health,
    integrations,
    metrics,
    passports,
    pilot,
    predictions,
    simulation,
)
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import create_all, engine
from app.core.logging_config import configure_logging, get_logger
from app.core.middleware import RequestIDMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.telemetry import configure_telemetry
from app.ml.model_registry import registry
from app.utils.enums import RECOMMENDATION_DISCLAIMER, SYNTHETIC_DATA_NOTICE

configure_logging()
logger = get_logger("app.main")

_DEFAULT_SECRET_KEY = "dev-only-insecure-key-change-me"


def _guard_against_default_secret() -> None:
    """Refuse to start in production with the shipped placeholder secret.

    ``SECRET_KEY`` signs every audit-chain-adjacent access token this
    prototype issues. Booting with the checked-in default and ``DEBUG=false``
    is exactly the "documented happy path deploys with insecure defaults"
    failure the build audit flagged - so it is a hard startup error, not a
    warning that scrolls past in the logs.
    """
    if settings.DEBUG:
        return
    if settings.SECRET_KEY == _DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "Refusing to start: SECRET_KEY is still the default placeholder "
            "('dev-only-insecure-key-change-me') and DEBUG is false. Set a "
            "unique SECRET_KEY (e.g. python -c \"import secrets; "
            "print(secrets.token_urlsafe(48))\") or set DEBUG=true for local "
            "development only."
        )


_guard_against_default_secret()

DESCRIPTION = f"""
### Component Passport - AI-Powered Circular Economy Platform

Every replaceable elevator component receives a **digital passport** addressable
by QR code. The passport carries identity, operating history, service history
and every AI assessment ever made, all anchored in a SHA-256 audit chain.

**Key capabilities**

* Component registry with QR-addressable digital passports
* Random Forest recommender and decision flow: `CONTINUE_USING` (Continue Using – No Changes Required) /
  `COMPONENT_RECOVERY` (Component Recovery) / `MATERIAL_RECOVERY` (Material Recovery) / `DISPOSE` (Dispose)
* Transparent 0-100 health score with a full weighted breakdown
* Explainability: model feature importance blended with design-envelope deviation
* **Safety gate**: steel ropes, brakes and governors always require human inspection
* Prototype economic impact estimates
* Append-only, tamper-evident SHA-256 audit chain with a verification endpoint

---

**Data disclosure.** {SYNTHETIC_DATA_NOTICE}

**Safety disclosure.** {RECOMMENDATION_DISCLAIMER}

**Trademark.** KONE is a trademark of KONE Corporation. This independent student
prototype is not affiliated with, endorsed by, or connected to KONE Corporation.
"""

TAGS_METADATA = [
    {"name": "Health", "description": "Service, database and model availability."},
    {
        "name": "Authentication",
        "description": (
            "Sign-in and account provisioning. Local credentials against the "
            "platform's own user table - not single sign-on. Every endpoint "
            "outside Health and Passport requires a bearer token, and the "
            "audit chain's actor is the verified subject of that token."
        ),
    },
    {"name": "Metadata", "description": "Controlled vocabularies used by the UI."},
    {"name": "Components", "description": "Component registry, service history and assessments."},
    {"name": "Prediction", "description": "AI-assisted end-of-use recommendations (four categories) and model metadata."},
    {"name": "Passport", "description": "Digital component passports and QR codes."},
    {"name": "Dashboard", "description": "Portfolio command centre and analytics."},
    {
        "name": "Forecast",
        "description": (
            "End-of-life forecasting and component-recovery capacity planning "
            "(Weibull AFT survival model, synthetic data)."
        ),
    },
    {"name": "Audit", "description": "Tamper-evident SHA-256 audit chain."},
    {
        "name": "KONE Integration",
        "description": (
            "Equipment identity, service records and spare-parts availability "
            "behind an anti-corruption layer. Fixture-backed today - no KONE "
            "API Portal sandbox credentials exist for this build."
        ),
    },
    {
        "name": "Pilot",
        "description": (
            "P6 pilot metrics: diversion rate, recovered-parts yield, "
            "decision-reversal rate, technician trust score, value recovered, "
            "mass diverted. See docs/pilot-protocol.md."
        ),
    },
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create tables and warm the model cache on startup."""
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    try:
        create_all()
        logger.info("Database schema ensured (%s)", settings.DATABASE_URL.split("://")[0])
    except SQLAlchemyError:  # pragma: no cover - surfaced by /health
        logger.exception("Could not create database schema - the API will start degraded")

    # Load the model once so the first prediction is not slowed by disk IO.
    if registry.load() is not None:
        logger.info("Model ready: %s", registry.model_version)
    else:
        logger.warning(
            "No trained model found at %s. Predictions will use the transparent "
            "health-score fallback until you run: python scripts/train_model.py",
            registry.model_path,
        )
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description=DESCRIPTION,
    version=settings.APP_VERSION,
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    contact={"name": "Team CodeFather - SRM Institute of Science and Technology, Ramapuram"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list({*settings.CORS_ORIGINS, settings.FRONTEND_URL}),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
configure_telemetry(app, engine)


# --------------------------------------------------------------------------
# Error handling - never leak a stack trace to a client
# --------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    """Return readable, field-level validation errors."""
    issues = [
        {
            "field": ".".join(str(part) for part in error.get("loc", []) if part != "body"),
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": "validation_error",
            "message": "The request payload failed validation.",
            "issues": issues,
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, exc: IntegrityError):
    logger.warning("Database integrity error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "conflict",
            "message": "The request conflicts with existing data (duplicate or missing reference).",
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, exc: SQLAlchemyError):
    logger.exception("Database error")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "database_unavailable",
            "message": "The database is currently unavailable. Please try again shortly.",
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled application error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred. The incident has been logged.",
        },
    )


# --------------------------------------------------------------------------
# Routers
# --------------------------------------------------------------------------
prefix = settings.API_V1_PREFIX

#: Applied to every router that serves the internal application. Requiring a
#: verified identity here - rather than on ~40 individual endpoints - means a
#: new endpoint is protected by default, which is the failure mode worth
#: engineering for.
authenticated = [Depends(get_current_user)]

# Public by design.
#   health    - liveness must answer before anyone can sign in.
#   passports - a technician scans a label in a basement machine room and the
#               passport opens on their phone with no login. That is the
#               product, not an oversight; gating it would break the one
#               thing the QR code exists to do.
app.include_router(health.router, prefix=prefix)
app.include_router(metrics.router, prefix=prefix)
app.include_router(passports.router, prefix=prefix)
app.include_router(auth.router, prefix=prefix)

# Everything else requires a signed-in user.
app.include_router(components.router, prefix=prefix, dependencies=authenticated)
app.include_router(predictions.router, prefix=prefix, dependencies=authenticated)
app.include_router(dashboard.router, prefix=prefix, dependencies=authenticated)
app.include_router(forecast.router, prefix=prefix, dependencies=authenticated)
app.include_router(audit.router, prefix=prefix, dependencies=authenticated)
app.include_router(compliance.router, prefix=prefix, dependencies=authenticated)
app.include_router(integrations.router, prefix=prefix, dependencies=authenticated)
app.include_router(pilot.router, prefix=prefix, dependencies=authenticated)
app.include_router(simulation.router, prefix=prefix, dependencies=authenticated)
app.include_router(field_data.router, prefix=prefix, dependencies=authenticated)


@app.get("/", tags=["Health"], summary="API index")
def index() -> Dict[str, Any]:
    """Human-friendly entry point listing the important URLs."""
    return {
        "name": settings.APP_NAME,
        "tagline": "Component Passport - AI-Powered Circular Economy Platform",
        "version": settings.APP_VERSION,
        "team": "CodeFather - SRM Institute of Science and Technology, Ramapuram",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
        "api_prefix": prefix,
        "health": f"{prefix}/health",
        "model": registry.metadata(),
        "data_notice": SYNTHETIC_DATA_NOTICE,
        "safety_notice": RECOMMENDATION_DISCLAIMER,
    }


# --------------------------------------------------------------------------
# Future IoT ingestion hook (documented, deliberately not connected)
# --------------------------------------------------------------------------
@app.post(
    f"{prefix}/sensors/{{component_id}}",
    tags=["Metadata"],
    summary="Future sensor ingestion endpoint (NOT IMPLEMENTED)",
    description=(
        "Architecture hook for future IoT telemetry (vibration, load, "
        "temperature, operating hours). **No sensor hardware is connected to "
        "this prototype.** The endpoint intentionally returns 501 so that no "
        "part of the demo can imply live telemetry exists."
    ),
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def ingest_sensor_reading(component_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "error": "not_implemented",
            "component_id": component_id,
            "message": (
                "Sensor ingestion is a documented future capability. This "
                "prototype has no IoT integration; component readings are "
                "entered manually or through service events."
            ),
            "planned_payload": {
                "vibration": "mm/s RMS",
                "average_load": "kg",
                "temperature": "degrees Celsius",
                "operating_hours": "cumulative hours",
                "recorded_at": "ISO-8601 timestamp",
            },
        },
    )
