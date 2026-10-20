"""OpenTelemetry tracing: one span per request, one child span per SQL statement.

Hand-rolled rather than ``opentelemetry-instrumentation-fastapi`` /
``-sqlalchemy``: those auto-instrumentation packages pin their supported
version ranges to specific FastAPI/Starlette/SQLAlchemy releases, and this
build's pinned versions (see requirements.lock) sit outside every range
published at the time this was written. A middleware plus a pair of
SQLAlchemy engine events gets the two spans that actually answer "why was
this request slow" - the request itself and the database calls inside it -
without a dependency that might refuse to install, or silently no-op,
against a version it does not recognise.
"""

from __future__ import annotations

import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.core.request_context import get_request_id

_TRACER_NAME = "kone-elevate"


def configure_telemetry(app: FastAPI, engine: Engine) -> None:
    """Wire a TracerProvider, request middleware and SQL span events.

    Safe to call with tracing disabled or with no exporter configured: in
    both cases spans are still created (so the code path is exercised and
    tested) but either never processed, or processed into a no-op/console
    sink - never sent anywhere unless OTEL_EXPORTER_OTLP_ENDPOINT is set.
    """
    if not settings.OTEL_ENABLED:
        return

    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: settings.OTEL_SERVICE_NAME})
    )

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT))
        )
    if settings.OTEL_CONSOLE_EXPORT:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(_TRACER_NAME)

    _instrument_requests(app, tracer)
    _instrument_sql(engine, tracer)


def _instrument_requests(app: FastAPI, tracer) -> None:
    @app.middleware("http")
    async def _tracing_middleware(request: Request, call_next: Callable) -> Response:
        with tracer.start_as_current_span(f"{request.method} {request.url.path}") as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.target", request.url.path)
            request_id = get_request_id()
            if request_id:
                span.set_attribute("request_id", request_id)
            try:
                response = await call_next(request)
            except Exception as exc:  # pragma: no cover - re-raised unchanged
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            span.set_attribute("http.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            return response


def _instrument_sql(engine: Engine, tracer) -> None:
    """One child span per SQL statement, timed via the connection's own info dict.

    ``conn.info`` is a per-connection scratch dict SQLAlchemy provides
    precisely so paired before/after events can hand data to each other -
    the same mechanism, at the connection rather than request scope, that
    ``app.core.request_context`` uses for the request id.
    """

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        span = tracer.start_span("db.query")
        span.set_attribute("db.statement", statement[:512])
        conn.info.setdefault("otel_spans", []).append((span, time.perf_counter()))

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        stack = conn.info.get("otel_spans")
        if not stack:
            return
        span, started = stack.pop()
        span.set_attribute("db.duration_seconds", time.perf_counter() - started)
        span.end()

    @event.listens_for(engine, "handle_error")
    def _on_error(exception_context):  # noqa: ANN001
        conn = exception_context.connection
        stack = conn.info.get("otel_spans") if conn is not None else None
        if not stack:
            return
        span, _ = stack.pop()
        span.record_exception(exception_context.original_exception)
        span.set_status(Status(StatusCode.ERROR))
        span.end()
