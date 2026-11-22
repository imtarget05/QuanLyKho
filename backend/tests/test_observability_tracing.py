import httpx
from fastapi import FastAPI
import opentelemetry.context as context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from app.api.telemetry import instrument_fastapi

_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))


async def test_fastapi_trace_honors_w3c_traceparent() -> None:
    _exporter.clear()

    app = FastAPI()
    instrument_fastapi(app, tracer_provider=_provider)
    app.get("/health/live")(lambda: {"status": "alive"})

    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    parent_span_id = "00f067aa0ba902b7"
    token = context.attach(context.set_value("suppress_instrumentation", True))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get(
                "/health/live",
                headers={"traceparent": f"00-{trace_id}-{parent_span_id}-01"},
            )
    finally:
        context.detach(token)

    span = next(span for span in _exporter.get_finished_spans() if span.name == "GET /health/live")
    assert response.status_code == 200
    assert f"{span.context.trace_id:032x}" == trace_id
    assert f"{span.parent.span_id:016x}" == parent_span_id


async def test_httpx_dependency_span_inherits_server_trace() -> None:
    _exporter.clear()

    app = FastAPI()
    instrument_fastapi(app, tracer_provider=_provider)

    @app.get("/sync")
    async def sync_external() -> dict[str, str]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": "true"}))
        ) as client:
            response = await client.get("https://sheets.example.test/health")
        return response.json()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/sync")

    spans = _exporter.get_finished_spans()
    server_span = next(span for span in spans if span.name == "GET /sync")
    dependency_span = next(span for span in spans if span.kind == SpanKind.CLIENT)
    assert response.status_code == 200
    assert dependency_span.context.trace_id == server_span.context.trace_id
    assert dependency_span.parent.span_id == server_span.context.span_id
