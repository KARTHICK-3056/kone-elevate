"""Prometheus scrape endpoint. See app.core.metrics for what is exposed."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.metrics import REGISTRY

router = APIRouter(tags=["Health"])


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description=(
        "Prediction latency, predicted-class distribution, abstention count "
        "and the last audit-chain verification result. Deliberately "
        "unauthenticated - see app.core.metrics for why - so restrict "
        "network access to this route in any real deployment."
    ),
)
def metrics() -> Response:
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
