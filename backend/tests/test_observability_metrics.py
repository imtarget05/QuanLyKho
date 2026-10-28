from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.observability import (
    configure_metrics,
    record_approval_decision,
    record_external_dependency,
    record_reconciliation_result,
)


def test_http_metrics_use_route_templates_not_raw_paths() -> None:
    app = FastAPI()
    configure_metrics(app)

    @app.get("/orders/{order_id}")
    async def get_order(order_id: str) -> dict[str, str]:
        return {"status": "found"}

    with TestClient(app) as client:
        response = client.get("/orders/order-secret-8421")
        metrics = client.get("/metrics", follow_redirects=False)

    assert response.status_code == 200
    assert metrics.status_code == 200
    assert "quanlykho_http_requests_total" in metrics.text
    assert 'route="/orders/{order_id}"' in metrics.text
    assert "order-secret-8421" not in metrics.text
    assert "quanlykho_http_requests_in_flight 0.0" in metrics.text


def test_reconciliation_metric_uses_bounded_business_labels() -> None:
    app = FastAPI()
    configure_metrics(app)
    record_reconciliation_result("inventory", "exception")

    with TestClient(app) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    sample = next(line for line in response.text.splitlines() if line.startswith("quanlykho_reconciliation_runs_total{"))
    assert 'outcome="exception"' in sample
    assert 'scope="inventory"' in sample
    assert sample.endswith(" 1.0")


def test_approval_metrics_track_decision_and_pending_time() -> None:
    app = FastAPI()
    configure_metrics(app)
    submitted_at = datetime.now(UTC) - timedelta(seconds=30)
    record_approval_decision("cash", "approved", submitted_at)

    with TestClient(app) as client:
        metrics = client.get("/metrics").text

    decision = next(line for line in metrics.splitlines() if line.startswith("quanlykho_approval_decisions_total{"))
    pending = next(line for line in metrics.splitlines() if line.startswith("quanlykho_approval_pending_seconds_count{"))
    assert 'kind="cash"' in decision
    assert 'outcome="approved"' in decision
    assert decision.endswith(" 1.0")
    assert 'kind="cash"' in pending
    assert pending.endswith(" 1.0")


def test_external_dependency_metric_uses_bounded_result_categories() -> None:
    app = FastAPI()
    configure_metrics(app)
    record_external_dependency("google_sheets", "rate_limited")

    with TestClient(app) as client:
        metrics = client.get("/metrics").text

    sample = next(line for line in metrics.splitlines() if line.startswith("quanlykho_external_dependency_results_total{"))
    assert 'provider="google_sheets"' in sample
    assert 'outcome="rate_limited"' in sample
    assert sample.endswith(" 1.0")