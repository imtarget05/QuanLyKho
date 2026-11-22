"""Real-model RetailOps agent backed by Ollama (RO-04).

Wraps the Ollama LLM adapter into the same AgentFn schema used by
``app.services.retailops_eval.evaluate_retailops`` so the golden dataset can
be scored against a real model instead of the deterministic simulation.
"""

from __future__ import annotations

from app.services.retail_agent.llm import chat


def run_real_agent(query: str) -> dict:
    """Chạy agent thật với Ollama, trả về kết quả theo schema eval."""
    result = chat(query)
    return {
        "outcome": result.get("outcome", "unknown"),
        "tools": result.get("tools", []),
        "args": result.get("args", {}),
        "latency_ms": result.get("latency_ms"),
        "error": result.get("error"),
    }
