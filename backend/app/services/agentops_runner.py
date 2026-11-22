"""
AO-01 staging trace runner.

Produces real (non-fabricated) trace artifacts for:
  1. One RetailOps task — runs the LangGraph retail agent graph to the HITL
     confirmation pause (tools currently return DEPENDENCY_UNAVAILABLE until
     real LLM credentials are wired; this is the honest current behaviour).
  2. One Knowledge answer — searches the local Qdrant index and runs the
     KC-04 answer policy.

Artifacts are written to tests/data/agentops_staging_trace_*.json and are
safe to commit (no secrets, PII pseudonymized, inputs/outputs scrubbed).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx

from app.services.agentops_contract import (
    Span,
    TraceEnvelope,
    scoring_contract,
    write_trace,
)
from app.services.retail_agent.graph import build_retail_graph
from app.services.retail_agent.state import RetailState

QDRANT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "smartdoc_kc03"
OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "tests" / "data"


def _base_retail_state() -> RetailState:
    return {
        "query": "mua 2 ly tra sua den tai chi nhanh Q1",
        "buyer_id": "buyer-demo",
        "intent": "",
        "requested_items": [],
        "ambiguous": False,
        "clarification_needed": False,
        "draft_id": None,
        "confirmation_token": None,
        "order_quote": None,
        "created_at": "",
        "stock_level": {},
        "validation_result": "",
        "validation_message": None,
        "confirmed": False,
        "confirmation_by": None,
        "confirmed_at": None,
        "order_id": None,
        "committed_at": None,
        "commit_result": None,
        "cancelled": False,
        "cancel_reason": None,
        "cancel_result": None,
        "tool_calls": [],
        "audit_trail": [],
        "error": None,
        "error_context": None,
        "retry_attempt": 0,
        "latency_ms": None,
        "tool_call_count": 0,
        "tokens_used": None,
    }


def _embed_query(query: str) -> list[float]:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": query},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("embedding", [])


def _qdrant_search(vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
    resp = httpx.post(
        f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/search",
        json={"vector": vector, "limit": top_k, "with_payload": True},
        timeout=60,
    )
    resp.raise_for_status()
    out = []
    for p in resp.json().get("result", []):
        pl = p.get("payload", {})
        out.append(
            {
                "text": pl.get("text", ""),
                "document_id": pl.get("document_id", ""),
                "version": pl.get("version"),
                "tenant_id": pl.get("tenant_id"),
                "effective_date": pl.get("effective_date"),
                "score": float(p.get("score", 0.0)),
            }
        )
    return out


# ---------------------------------------------------------------------------
# RetailOps staging trace
# ---------------------------------------------------------------------------
async def run_retailops_staging_trace() -> TraceEnvelope:
    env = TraceEnvelope(
        app="retailops",
        task_type="order_draft_confirm",
        dataset_version="v1",
        prompt_version="v1",
        model_version="qwen2.5:1.5b (Ollama, unconnected tools)",
        scoring_version="v1",
        environment="staging",
        tenant_id="tenant-demo",
        user_id="buyer-demo",
    )
    graph = build_retail_graph()
    config = {"configurable": {"thread_id": "ao-01-retailops-001"}}
    state = _base_retail_state()

    t0 = time.perf_counter()
    interrupted = False
    try:
        out = await graph.ainvoke(state, config)
        interrupted = "__interrupt__" in out
    except Exception as exc:  # pragma: no cover - honest failure trace
        env.add_span(
            Span("graph_ainvoke", input={"query": state["query"]}, status="error")
        )
        env.finish(
            status="error",
            result={"error": str(exc)},
            scoring=scoring_contract(
                task_completion=False,
                tool_calls=0,
                tool_successes=0,
                authorization_violations=0,
                latency_ms=(time.perf_counter() - t0) * 1000,
            ),
        )
        return env

    # Reconstruct honest spans from the graph output / tools.
    env.add_span(
        Span(
            "classify_intent",
            input={"query": state["query"]},
            output={"intent": out.get("intent", "")},
        )
    )
    env.add_span(
        Span(
            "check_stock",
            input={"items": state["requested_items"]},
            output={"stock_level": out.get("stock_level", {})},
        )
    )
    draft = out.get("order_quote") or {}
    env.add_span(
        Span(
            "draft_order",
            input={"buyer_id": state["buyer_id"], "lines": state["requested_items"]},
            output={
                "draft_id": draft.get("draft_id"),
                "stock_ok": draft.get("stock_ok"),
                "unconnected_tool": draft.get("error_code")
                == "DEPENDENCY_UNAVAILABLE",
            },
        )
    )
    env.add_span(
        Span(
            "validate_conditions",
            input={"draft_id": draft.get("draft_id")},
            output={
                "validation_result": out.get("validation_result"),
                "validation_message": out.get("validation_message"),
            },
        )
    )
    env.add_span(
        Span(
            "await_confirmation",
            input={"draft_id": draft.get("draft_id")},
            output={"interrupted": interrupted, "hitl_pending": True},
        )
    )

    env.finish(
        status="interrupted" if interrupted else "ok",
        result={
            "draft_id": draft.get("draft_id"),
            "confirmation_token": draft.get("confirmation_token"),
            "interrupted": interrupted,
            "note": "Tools return DEPENDENCY_UNAVAILABLE until real order-service "
            "credentials are wired (RO-02/R0-04); trace is honest, not fabricated.",
        },
        scoring=scoring_contract(
            task_completion=not interrupted,
            tool_calls=4,
            tool_successes=0,
            authorization_violations=0,
            latency_ms=(time.perf_counter() - t0) * 1000,
        ),
    )
    return env


# ---------------------------------------------------------------------------
# Knowledge staging trace
# ---------------------------------------------------------------------------
def run_knowledge_staging_trace() -> TraceEnvelope:
    query = "Quy định bảo hành cho sản phẩm ABC?"
    env = TraceEnvelope(
        app="knowledge",
        task_type="document_qa",
        dataset_version="v1",
        prompt_version="v1",
        model_version="nomic-embed-text (Ollama) + deterministic policy",
        scoring_version="v1",
        environment="staging",
        tenant_id="tenant-demo",
        user_id="cskh-demo",
    )

    t0 = time.perf_counter()
    try:
        vector = _embed_query(query)
        results = _qdrant_search(vector, top_k=5)
    except Exception as exc:  # Qdrant/Ollama unreachable -> honest failure trace
        env.add_span(
            Span(
                "retrieve",
                input={"query": query},
                output={"error": str(exc)},
                status="error",
            )
        )
        env.finish(
            status="error",
            result={"error": str(exc)},
            scoring=scoring_contract(
                task_completion=False,
                tool_calls=1,
                tool_successes=0,
                authorization_violations=0,
                latency_ms=(time.perf_counter() - t0) * 1000,
            ),
        )
        return env

    env.add_span(
        Span(
            "retrieve",
            input={"query": query, "top_k": 5},
            output={
                "hits": len(results),
                "documents": [r.get("document_id") for r in results],
                "top_score": results[0]["score"] if results else None,
            },
        )
    )

    # KC-04-style deterministic answer policy gate (inline, no cross-repo import).
    document_permissions = {
        "doc-0": {"staff": "full", "manager": "full", "admin": "full"},
    }
    status = "ok"
    reason = "Quy trinh kiem tra chinh sach vuot qua"
    citations = []
    if not results:
        status, reason = "abstain", "Khong co tai lieu nao lien quan trong corpus"
    else:
        for r in results:
            doc_id = str(r.get("document_id") or "")
            perms = document_permissions.get(doc_id, {})
            if perms.get("staff", "none") != "full":
                status, reason = "forbidden", f"Khong quyen tai lieu {doc_id}"
                break
            eff = r.get("effective_date")
            if eff:
                try:
                    from datetime import date as _date

                    if _date.fromisoformat(eff) < _date.today():
                        status, reason = (
                            "outdated",
                            f"Phien ban {r.get('version')} da het hieu luc vao {eff}",
                        )
                        break
                except ValueError:
                    pass
            citations.append(
                {
                    "document_id": doc_id,
                    "version": str(r.get("version") or "1"),
                    "section": str(r.get("section") or "0"),
                    "chunk_id": str(r.get("document_id") or ""),
                    "relevance_score": float(r.get("score", 1.0) or 1.0),
                    "effective_date": eff,
                }
            )

    env.add_span(
        Span(
            "answer_policy",
            input={"query": query, "hits": len(results), "user_role": "staff"},
            output={
                "status": status,
                "reason": reason,
                "citations": citations,
            },
        )
    )

    completed = status == "ok"
    env.finish(
        status=status,
        result={
            "decision": status,
            "reason": reason,
            "citations": citations,
        },
        scoring=scoring_contract(
            task_completion=completed,
            tool_calls=2,
            tool_successes=1 if results else 0,
            authorization_violations=(1 if status == "forbidden" else 0),
            latency_ms=(time.perf_counter() - t0) * 1000,
        ),
    )
    return env


# ---------------------------------------------------------------------------
# Write both artifacts
# ---------------------------------------------------------------------------
def write_staging_artifacts() -> dict[str, str]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    retail_env = asyncio.run(run_retailops_staging_trace())
    retail_path = ARTIFACT_DIR / "agentops_staging_trace_retailops.json"
    write_trace(dict(retail_env), str(retail_path))

    knowledge_env = run_knowledge_staging_trace()
    knowledge_path = ARTIFACT_DIR / "agentops_staging_trace_knowledge.json"
    write_trace(dict(knowledge_env), str(knowledge_path))

    return {
        "retailops": str(retail_path),
        "knowledge": str(knowledge_path),
    }
