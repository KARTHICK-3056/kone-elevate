"""Prometheus metrics: the four numbers the P4 build audit named by name.

    "you cannot answer 'why was that prediction slow' or 'how often do we
    abstain'"

``GET /metrics`` (see app.api.metrics) exposes:

* ``prediction_latency_seconds``   - histogram, inference wall-clock time
* ``predictions_total``            - counter, by final recommendation
* ``prediction_abstentions_total`` - counter, DEFER_TO_INSPECTION count
* ``audit_chain_verification_valid`` - gauge, 1/0, last verification run
  *by this process* (see the caveat on ``record_chain_verification``)

Left deliberately unauthenticated, matching standard Prometheus practice:
a scrape target is usually reached over a private network or a separate
port, not through application-level login, and forcing a bearer token onto
a scraper config is friction with no real security benefit here. A
production deployment should still restrict who can reach this route at
the network/ingress layer - see docs/threat-model.md.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry()

PREDICTION_LATENCY = Histogram(
    "prediction_latency_seconds",
    "Wall-clock time to score one component (feature build through safety gate).",
    registry=REGISTRY,
)

PREDICTIONS_TOTAL = Counter(
    "predictions_total",
    "Predictions served, by final recommendation (post-abstention).",
    ["recommendation"],
    registry=REGISTRY,
)

PREDICTION_ABSTENTIONS_TOTAL = Counter(
    "prediction_abstentions_total",
    "Predictions where the abstention rule overrode the model's argmax class.",
    registry=REGISTRY,
)

#: 1 = last verification (in THIS process) found the chain intact, 0 = broken.
#: A Gauge is a process-local snapshot, not a durable record - it reflects
#: whatever last called record_chain_verification in this worker, which for
#: a multi-worker deployment means "some worker's most recent check", not a
#: global truth. scripts/verify_chain.py's exit code and alert webhook are
#: the mechanism for the "alert on verification failure" requirement across
#: a scheduled/cron run outside any running API worker; this gauge is what
#: GET /api/v1/audit/verify updates for whichever worker answered it.
CHAIN_VERIFICATION_VALID = Gauge(
    "audit_chain_verification_valid",
    "1 if the audit chain's last verification (in this process) was valid, else 0.",
    registry=REGISTRY,
)


def record_prediction(recommendation: str, abstained: bool, duration_seconds: float) -> None:
    PREDICTION_LATENCY.observe(duration_seconds)
    PREDICTIONS_TOTAL.labels(recommendation=str(recommendation)).inc()
    if abstained:
        PREDICTION_ABSTENTIONS_TOTAL.inc()


def record_chain_verification(valid: bool) -> None:
    CHAIN_VERIFICATION_VALID.set(1.0 if valid else 0.0)
