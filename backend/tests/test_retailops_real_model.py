"""RO-04 real-model golden evaluation against Ollama (replaces simulation).

Scores the golden RetailOps dataset with a real LLM (qwen2.5:1.5b on Ollama)
and writes an evidence report. LLM output is non-deterministic, so tests assert
report structure and Ollama connectivity, not a fixed success rate.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.services.retail_agent.real_agent import run_real_agent
from app.services.retailops_eval import (
    evaluate_retailops,
    load_golden_dataset,
    write_report,
)

DATASET = Path(__file__).resolve().parents[1] / "tests" / "data" / "golden_retailops.jsonl"
REPORT = Path(__file__).resolve().parents[1] / "tests" / "data" / "retailops_real_model_report.json"
OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen2.5:1.5b"


def _ollama_available() -> bool:
    try:
        resp = httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        if resp.status_code != 200:
            return False
        return any(m.get("model") == OLLAMA_MODEL for m in resp.json().get("models", []))
    except httpx.RequestError:
        return False


@pytest.mark.skipif(not _ollama_available(), reason="Ollama model qwen2.5:1.5b not available")
def test_ollama_model_available():
    assert _ollama_available()


@pytest.mark.skipif(not _ollama_available(), reason="Ollama model qwen2.5:1.5b not available")
def test_real_agent_returns_expected_schema():
    result = run_real_agent("Mua 2 ly tra sua den tai chi nhanh Q1")
    assert set(result.keys()) >= {"outcome", "tools", "args", "latency_ms"}
    assert isinstance(result["tools"], list)
    assert isinstance(result["args"], dict)


@pytest.mark.skipif(not _ollama_available(), reason="Ollama model qwen2.5:1.5b not available")
def test_real_model_golden_eval_writes_report():
    cases = load_golden_dataset(DATASET)
    assert len(cases) >= 30
    report = evaluate_retailops(run_real_agent, cases)
    assert report["total_cases"] == len(cases)
    assert "task_success_rate" in report
    assert "tool_selection_accuracy" in report
    assert "authorization_violations" in report
    assert len(report["per_case"]) == len(cases)
    write_report(report, REPORT)
    assert REPORT.exists()
    data = json.loads(REPORT.read_text())
    assert data["total_cases"] == len(cases)
