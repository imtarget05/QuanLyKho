"""OpenTelemetry setup with optional, non-blocking OTLP export."""

from __future__ import annotations

import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Tracer provider currently bound to the shared HTTPX client instrumentation.
_httpx_tracer_provider: TracerProvider | None = None


def _trace_exporter_endpoint() -> str | None:
    signal_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if signal_endpoint:
        return signal_endpoint

    base_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not base_endpoint:
        return None
    return f"{base_endpoint.rstrip('/')}/v1/traces"


def _metrics_exporter_endpoint() -> str | None:
    signal_endpoint = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
    if signal_endpoint:
        return signal_endpoint

    base_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not base_endpoint:
        return None
    return f"{base_endpoint.rstrip('/')}/v1/metrics"


def create_tracer_provider(
    *,
    service_name: str | None = None,
    endpoint: str | None = None,
) -> TracerProvider:
    resource = Resource.create(
        {
            "service.name": service_name
            or os.getenv("OTEL_SERVICE_NAME", "quanlykho-api"),
            "service.version": os.getenv("APP_VERSION", "dev"),
            "deployment.environment": os.getenv("APP_ENV", "demo"),
        }
    )
    provider = TracerProvider(resource=resource)
    exporter_endpoint = endpoint or _trace_exporter_endpoint()
    if exporter_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=exporter_endpoint))
        )
    return provider


def create_meter_provider(
    *,
    service_name: str,
    endpoint: str | None = None,
) -> MeterProvider:
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("APP_VERSION", "dev"),
            "deployment.environment": os.getenv("APP_ENV", "demo"),
        }
    )
    exporter_endpoint = endpoint or _metrics_exporter_endpoint()
    readers = []
    if exporter_endpoint:
        readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=exporter_endpoint),
                export_interval_millis=15000,
            )
        )
    return MeterProvider(resource=resource, metric_readers=readers)


def instrument_fastapi(
    app: FastAPI,
    *,
    tracer_provider: TracerProvider | None = None,
) -> TracerProvider:
    provider = tracer_provider or create_tracer_provider()
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="metrics",
    )
    if not LoggingInstrumentor().is_instrumented_by_opentelemetry:
        LoggingInstrumentor().instrument(
            tracer_provider=provider, set_logging_format=False
        )
    _instrument_httpx_client(provider)
    return provider


def _instrument_httpx_client(provider: TracerProvider) -> None:
    """Instrument HTTPX so outbound client spans honour ``provider``.

    The HTTPX instrumentor patches the shared ``httpx`` module, so it can
    only be bound to one tracer provider at a time. When a different
    provider is requested (a test provider, for example) the previous
    instrumentation is removed first; otherwise the first provider wins and
    later providers are silently ignored.
    """
    global _httpx_tracer_provider
    instrumentor = HTTPXClientInstrumentor()
    if instrumentor.is_instrumented_by_opentelemetry:
        if _httpx_tracer_provider is provider:
            return
        instrumentor.uninstrument()
    instrumentor.instrument(tracer_provider=provider)
    _httpx_tracer_provider = provider


def instrument_sqlalchemy(
    engine, *, tracer_provider: TracerProvider | None = None
) -> None:
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine,
        tracer_provider=tracer_provider or trace.get_tracer_provider(),
    )
