"""AO-03: AgentOps dashboard (offline tests)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.agentops_dashboard import (
    build_dashboard,
    dashboard_html,
    write_dashboard,
)


def _write_trace(tmp_path: Path, trace_id: str, app: str, status: str, latency_ms: float) -> Path:
    env = {
        "trace_id": trace_id,
        "app": app,
        "task_type": "order_draft_confirm" if app == "retailops" else "document_qa",
        "status": status,
        "latency_ms": latency_ms,
        "started_at": "2026-11-21T00:00:00+00:00",
        "ended_at": "2026-11-21T00:00:01+00:00",
        "spans": [],
        "result": None,
        "scoring": {
            "task_completion": status == "ok",
            "authorization_violations": 1 if status == "blocked" else 0,
            "cost_usd": 0.02,
        },
        "redacted_fields": [],
    }
    p = tmp_path / f"agentops_staging_trace_{trace_id}.json"
    p.write_text(json.dumps(env, ensure_ascii=False), encoding="utf-8")
    return p


def test_build_dashboard_summary(tmp_path):
    _write_trace(tmp_path, "tr-1", "retailops", "ok", 120.0)
    _write_trace(tmp_path, "tr-2", "knowledge", "blocked", 340.0)
    dash = build_dashboard(tmp_path)
    s = dash["summary"]
    assert s["total_traces"] == 2
    assert s["error_traces"] == 1
    assert s["authorization_violations"] == 1
    assert s["by_app"]["retailops"]["count"] == 1
    assert s["by_app"]["knowledge"]["count"] == 1


def test_build_dashboard_traces_have_drilldown_link(tmp_path):
    _write_trace(tmp_path, "tr-abc", "retailops", "ok", 50.0)
    dash = build_dashboard(tmp_path)
    t = dash["traces"][0]
    assert t["trace_id"] == "tr-abc"
    assert t["artifact"] == "agentops_staging_trace_tr-abc.json"


def test_dashboard_html_contains_trace_links(tmp_path):
    _write_trace(tmp_path, "tr-xyz", "knowledge", "ok", 10.0)
    dash = build_dashboard(tmp_path)
    html = dashboard_html(dash)
    assert "tr-xyz" in html
    assert "agentops_staging_trace_tr-xyz.json" in html
    assert "AgentOps Dashboard" in html


def test_write_dashboard_creates_file(tmp_path):
    _write_trace(tmp_path, "tr-1", "retailops", "ok", 5.0)
    dash = build_dashboard(tmp_path)
    out = tmp_path / "out" / "dashboard.json"
    write_dashboard(dash, out)
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"]["total_traces"] == 1
