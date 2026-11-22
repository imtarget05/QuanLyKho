"""AO-01: AgentOps telemetry contract + staging trace artifacts.

Offline-safe except the knowledge trace which needs local Qdrant + Ollama.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.services.agentops_contract import (
    Span,
    TraceEnvelope,
    redact_trace_fields,
    scoring_contract,
    validate_trace,
    write_trace,
)
from app.services.agentops_runner import (
    OLLAMA_URL,
    QDRANT_URL,
    run_knowledge_staging_trace,
    run_retailops_staging_trace,
    write_staging_artifacts,
)

DATA_DIR = Path(__file__).resolve().parent / "data"


def _services_up() -> bool:
    try:
        httpx.get(f"{QDRANT_URL}/collections", timeout=3)
        httpx.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": "x"},
            timeout=3,
        )
        return True
    except httpx.RequestError:
        return False


# ---------------------------------------------------------------------------
# Contract tests (offline)
# ---------------------------------------------------------------------------
def test_contract_validate_trace_ok():
    env = TraceEnvelope(app="retailops", task_type="order_draft_confirm")
    env.add_span(Span("classify_intent", input={"q": "x"}, output={"i": "y"}))
    env.finish(status="ok", result={"ok": True})
    assert validate_trace(dict(env)) == []


def test_contract_validate_trace_missing_field():
    env = TraceEnvelope(app="retailops", task_type="order_draft_confirm")
    del env["dataset_version"]
    assert "missing field: dataset_version" in validate_trace(dict(env))


def test_contract_redact_sensitive():
    env = TraceEnvelope(app="knowledge", task_type="document_qa")
    env.add_span(
        Span(
            "retrieve",
            input={"query": "x", "password": "s3cret"},
            output={"token": "sk-abc123"},
        )
    )
    env.finish(
        status="ok",
        result={"notes": "card 4111222233334444 here"},
    )
    redacted = redact_trace_fields(dict(env))
    assert any("password" in p for p in redacted)
    assert any("token" in p for p in redacted)


def test_contract_scoring_contract():
    s = scoring_contract(
        task_completion=True,
        tool_calls=4,
        tool_successes=3,
        authorization_violations=0,
        latency_ms=125.456,
        cost_usd=0.02,
    )
    assert s["task_completion"] is True
    assert s["tool_selection_accuracy"] == 0.75
    assert s["authorization_violations"] == 0
    assert s["latency_ms"] == 125.46
    assert s["cost_usd"] == 0.02


def test_write_trace_artifact(tmp_path):
    env = TraceEnvelope(app="retailops", task_type="order_draft_confirm")
    env.add_span(Span("draft_order", input={"buyer": "b"}, output={"id": "d-1"}))
    env.finish(status="ok", result={"order_id": "o-1"})
    p = tmp_path / "trace.json"
    write_trace(dict(env), str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["trace_id"].startswith("tr-")
    assert data["status"] == "ok"
    assert len(data["spans"]) == 1
    assert data["result"]["order_id"] == "o-1"


# ---------------------------------------------------------------------------
# Runner tests (real, non-fabricated traces)
# ---------------------------------------------------------------------------
def test_runner_writes_retailops_trace():
    env = asyncio_run_retailops()
    assert env["app"] == "retailops"
    assert env["task_type"] == "order_draft_confirm"
    assert env["status"] in ("interrupted", "ok")
    span_names = [s["name"] for s in env["spans"]]
    assert span_names == [
        "classify_intent",
        "check_stock",
        "draft_order",
        "validate_conditions",
        "await_confirmation",
    ]
    # Tools are unconnected -> honest trace records that, no fabrication.
    assert env["result"].get("note", "").startswith("Tools return")


@pytest.mark.skipif(not _services_up(), reason="local Qdrant + Ollama not reachable")
def test_runner_writes_knowledge_trace():
    env = run_knowledge_staging_trace()
    assert env["app"] == "knowledge"
    assert env["task_type"] == "document_qa"
    assert env["status"] in (
        "ok", "abstain", "outdated", "forbidden", "out_of_domain", "error",
    )
    retrieve = env["spans"][0]
    assert retrieve["name"] == "retrieve"
    assert retrieve["output"]["hits"] >= 0


def test_write_staging_artifacts():
    paths = write_staging_artifacts()
    assert set(paths) == {"retailops", "knowledge"}
    for p in paths.values():
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        assert validate_trace(data) == []


def asyncio_run_retailops() -> dict:
    import asyncio

    return asyncio.run(run_retailops_staging_trace())
