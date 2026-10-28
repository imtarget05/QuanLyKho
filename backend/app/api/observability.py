"""Bounded-cardinality HTTP metrics for Prometheus scraping."""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


@dataclass(frozen=True)
class MetricsBundle:
    """Owns one Prometheus registry plus the metric families it exposes.

    A bundle per configured app keeps counters isolated: rebuilding it on
    ``configure_metrics`` guarantees a freshly configured app starts from
    zero instead of inheriting counts recorded by a previously configured app.
    """

    registry: CollectorRegistry
    reconciliation_runs: Counter
    approval_decisions: Counter
    approval_pending: Histogram
    external_dependency_results: Counter
    http_requests: Counter
    http_duration: Histogram
    http_in_flight: Gauge


def _build_metrics_bundle() -> MetricsBundle:
    registry = CollectorRegistry(auto_describe=True)
    return MetricsBundle(
        registry=registry,
        reconciliation_runs=Counter(
            "quanlykho_reconciliation_runs_total",
            "Completed reconciliation runs by bounded scope and outcome.",
            labelnames=("scope", "outcome"),
            registry=registry,
        ),
        approval_decisions=Counter(
            "quanlykho_approval_decisions_total",
            "Committed maker-checker decisions by request kind and outcome.",
            labelnames=("kind", "outcome"),
            registry=registry,
        ),
        approval_pending=Histogram(
            "quanlykho_approval_pending_seconds",
            "Time spent awaiting a committed maker-checker decision.",
            labelnames=("kind", "outcome"),
            registry=registry,
        ),
        external_dependency_results=Counter(
            "quanlykho_external_dependency_results_total",
            "External integration outcomes by provider and bounded result category.",
            labelnames=("provider", "outcome"),
            registry=registry,
        ),
        http_requests=Counter(
            "quanlykho_http_requests_total",
            "HTTP requests completed by the API.",
            labelnames=("method", "route", "status_class"),
            registry=registry,
        ),
        http_duration=Histogram(
            "quanlykho_http_request_duration_seconds",
            "HTTP request duration in seconds by method and route template.",
            labelnames=("method", "route"),
            registry=registry,
        ),
        http_in_flight=Gauge(
            "quanlykho_http_requests_in_flight",
            "HTTP requests currently being handled by the API.",
            registry=registry,
        ),
    )


_metrics = _build_metrics_bundle()

# Request-scoped bundle. Each configured app binds its own bundle for the
# duration of a request, so business metrics recorded inside a route handler
# land on that app's registry instead of whichever app was configured last.
_request_metrics: ContextVar[MetricsBundle | None] = ContextVar(
    "quanlykho_request_metrics", default=None
)


def _active_metrics() -> MetricsBundle:
    """Return the bundle that should receive the next business metric sample."""
    return _request_metrics.get() or _metrics


def record_reconciliation_result(scope: str, outcome: str) -> None:
    if scope not in {"cash", "inventory"}:
        raise ValueError("reconciliation scope must be cash or inventory")
    if outcome not in {"matched", "exception"}:
        raise ValueError("reconciliation outcome must be matched or exception")
    _active_metrics().reconciliation_runs.labels(scope=scope, outcome=outcome).inc()


def record_approval_decision(
    kind: str,
    outcome: str,
    submitted_at: datetime | None = None,
) -> None:
    if kind not in {"cash", "inventory", "stocktake"}:
        raise ValueError("approval kind is not a supported bounded category")
    if outcome not in {"approved", "rejected"}:
        raise ValueError("approval outcome must be approved or rejected")
    bundle = _active_metrics()
    bundle.approval_decisions.labels(kind=kind, outcome=outcome).inc()
    if submitted_at is not None:
        if submitted_at.tzinfo is None:
            submitted_at = submitted_at.replace(tzinfo=UTC)
        elapsed = max(
            0.0, (datetime.now(UTC) - submitted_at.astimezone(UTC)).total_seconds()
        )
        bundle.approval_pending.labels(kind=kind, outcome=outcome).observe(elapsed)


def record_external_dependency(provider: str, outcome: str) -> None:
    if provider not in {"google_sheets", "apps_script"}:
        raise ValueError("external provider is not a supported bounded category")
    if outcome not in {
        "success",
        "rate_limited",
        "unavailable",
        "http_error",
        "configuration_error",
    }:
        raise ValueError("external outcome is not a supported bounded category")
    _active_metrics().external_dependency_results.labels(
        provider=provider, outcome=outcome
    ).inc()


class HttpMetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, bundle: MetricsBundle) -> None:
        super().__init__(app)
        self.bundle = bundle

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path.rstrip("/") == "/metrics":
            # Exclude both slash variants of the scrape endpoint so scraping
            # does not inflate the request metrics it reports.
            return await call_next(request)

        started = time.perf_counter()
        self.bundle.http_in_flight.inc()
        status_code = 500
        token = _request_metrics.set(self.bundle)
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            _request_metrics.reset(token)
            route = request.scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            labels = {
                "method": request.method,
                "route": route_template,
                "status_class": f"{status_code // 100}xx",
            }
            self.bundle.http_requests.labels(**labels).inc()
            self.bundle.http_duration.labels(
                method=request.method, route=route_template
            ).observe(time.perf_counter() - started)
            self.bundle.http_in_flight.dec()


def configure_metrics(app: FastAPI) -> CollectorRegistry:
    """Wire Prometheus metrics into ``app`` with an app-private registry.

    Each configured app owns a fresh registry, so counters and label sets
    recorded for one app never leak into another app's ``/metrics`` output.
    """
    global _metrics
    bundle = _build_metrics_bundle()
    _metrics = bundle
    app.add_middleware(HttpMetricsMiddleware, bundle=bundle)
    app.add_api_route(
        "/metrics",
        lambda: Response(
            generate_latest(bundle.registry), media_type=CONTENT_TYPE_LATEST
        ),
        methods=["GET"],
        include_in_schema=False,
        name="prometheus_metrics",
    )
    return bundle.registry
