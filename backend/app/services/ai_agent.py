"""SOP tra cứu kho — LangGraph-style agent orchestrator.

State graph (pure Python, no extra dependency):
    classify_write → (write? pend HITL : retrieve → tools → decide → generate → format)

- classify_write: deterministic keyword check — write actions (adjust_inventory,
  send_email, create_ticket) are NEVER auto-executed; they are pended for human
  approval (HITL) and the agent returns a pending-approval response.
- retrieve: BM25 keyword retrieval over业务 docs via ai_retrieval.retrieve()
- tools:    D4 — read-only GraphQL tools (agent_tools) cho câu hỏi cần dữ liệu
            sống (số dư, saga, outbox, audit, health). Fail-soft: lỗi tool được
            ghi lại, agent vẫn trả lời bằng tài liệu SOP. Mutation bị chặn.
- decide:   if no docs and no tool data → abstain (từ chối), skip generation
- generate: grounded answer (local, trích dẫn nguồn + dữ liệu tool)
- format:   attach source refs (without content) to the response

Security (ADR 0002): advisory only — never approves phiếu, never touches
số dư/sổ cái. Read-only docs + read-only LLM generate. Write actions require
consumer (PIN/maker-checker) approval before any mutation.
"""

from __future__ import annotations

import json
import time
import unicodedata
import uuid
from typing import Any

from app.services.agent_tools import run_tools
from app.services.ai_retrieval import retrieve


def _strip_diacritics(value: str) -> str:
    """Loại bỏ dấu tiếng Việt (NFD + xóa dấu) để matching khớp dù có/không dấu."""
    plain = unicodedata.normalize("NFD", value.lower())
    return "".join(ch for ch in plain if unicodedata.category(ch) != "Mn")


# ---------------------------------------------------------------------------
# HITL write-action gate
# ---------------------------------------------------------------------------

WRITE_ACTIONS = {"adjust_inventory", "send_email", "create_ticket"}

_WRITE_ACTION_KEYWORDS = {
    "adjust_inventory": {
        "điều chỉnh tồn", "điều chỉnh kho", "adjust_inventory", "adjust inventory",
        "sửa tồn", "cập nhật tồn", "thay đổi số lượng kho", "chỉnh tồn",
    },
    "send_email": {
        "gửi email", "send_email", "send email", "email", "thông báo qua email",
    },
    "create_ticket": {
        "tạo ticket", "create_ticket", "create ticket", "mở ticket", "ticket hỗ trợ",
    },
}

_NORMALIZED_KEYWORDS: dict[str, set[str]] = {
    action: {_strip_diacritics(kw) for kw in kws}
    for action, kws in _WRITE_ACTION_KEYWORDS.items()
}

_PENDING_WRITE_ACTIONS: dict[str, dict] = {}


def classify_write_action(query: str) -> dict[str, Any] | None:
    """Phân loại ý định ghi từ câu hỏi (deterministic, không gọi LLM).

    Trả về {"action_type": ..., "payload": {...}} nếu là hành động ghi,
    None nếu là truy vấn chỉ đọc / không rõ ý định.
    Matching khớp dấu tiếng Việt (có dấu và không dấu đều được).
    """
    plain = _strip_diacritics(query)
    for action_type, keywords in _NORMALIZED_KEYWORDS.items():
        for kw in keywords:
            if kw in plain:
                return {
                    "action_type": action_type,
                    "payload": {"raw_query": query},
                }
    return None


def pend_write_action(query: str, action_type: str, payload: dict) -> str:
    """Tạo yêu cầu duyệt HITL cho hành động ghi. Trả về request_id."""
    request_id = f"hitl-{uuid.uuid4().hex[:12]}"
    _PENDING_WRITE_ACTIONS[request_id] = {
        "request_id": request_id,
        "query": query,
        "action_type": action_type,
        "payload": payload,
        "status": "pending",  # pending | approved | rejected
        "approver": None,
        "note": None,
        "created_at": time.time(),
    }
    return request_id


def get_pending_write_action(request_id: str) -> dict | None:
    return _PENDING_WRITE_ACTIONS.get(request_id)


def decide_write_action(request_id: str, decision: str, approver: str) -> dict | None:
    """Duyệt/từ chối yêu cầu ghi (gọi bởi con người qua PIN/maker-checker)."""
    if decision not in {"approved", "rejected"}:
        return None
    record = _PENDING_WRITE_ACTIONS.get(request_id)
    if record is None or record["status"] != "pending":
        return None
    record["status"] = decision
    record["approver"] = approver
    return dict(record)


# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------


class AgentState(dict):
    """Mutable state carried between graph nodes."""

    def __init__(self, query: str, **kwargs):
        super().__init__(
            {
                "query": query,
                "sources": [],
                "answer": "",
                "abstained": False,
                "abstain_reason": "",
                "write_action": None,
                "hitl_pending": False,
                "hitl_request_id": None,
                "provider": None,
                "model": None,
                "simulation": True,
                "citations": [],
                "error": None,
                "tool_calls": [],
                "tool_results": [],
                "tool_errors": [],
            }
        )
        self.update(kwargs)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def classify_node(state: AgentState) -> AgentState:
    """Phân loại hành động ghi. Nếu là write → đánh dấu hitl_pending và dừng."""
    write = classify_write_action(state["query"])
    if write is None:
        return state
    state["write_action"] = write
    request_id = pend_write_action(state["query"], write["action_type"], write["payload"])
    state["hitl_pending"] = True
    state["hitl_request_id"] = request_id
    state["answer"] = (
        f"Yêu cầu '{write['action_type']}' là hành động ghi cần duyệt trước khi thực thi. "
        f"Vui lòng duyệt qua giao diện kiểm soát kép (maker-checker), request_id={request_id}. "
        "Agent không tự thực hiện hành động ghi."
    )
    return state


def retrieve_node(state: AgentState, settings, client, limit: int = 3) -> AgentState:
    """Retrieve relevant SOP docs for the user query."""
    query = state["query"]
    sources = retrieve(query, limit=limit)
    state["sources"] = sources
    return state


async def tools_node(
    state: AgentState,
    executor=None,
    enable_tools: bool = True,
) -> AgentState:
    """D4 — gọi các GraphQL tool chỉ-đọc phù hợp với câu hỏi.

    Fail-soft: lỗi tool được ghi vào `tool_errors`, không làm hỏng câu trả lời.
    Không chạy khi câu hỏi đã bị chặn bởi HITL (hành động ghi).
    """
    if not enable_tools or state["hitl_pending"]:
        return state
    outcome = await run_tools(state["query"], executor=executor)
    state["tool_calls"] = outcome["calls"]
    state["tool_results"] = outcome["results"]
    state["tool_errors"] = outcome["errors"]
    return state


def decide_node(state: AgentState) -> AgentState:
    """Decide whether to answer or abstain (no sufficient evidence)."""
    if state["hitl_pending"]:
        return state
    if not state["sources"] and not state["tool_results"]:
        state["abstained"] = True
        state["abstain_reason"] = "Không tìm thấy tài liệu nghiệp vụ liên quan đến câu hỏi."
        state["answer"] = (
            "Tôi chưa tìm thấy thông tin phù hợp trong tài liệu nghiệp vụ nội bộ. "
            "Vui lòng diễn giải rõ hơn hoặc liên hệ quản lý kho để được hỗ trợ."
        )
    return state


def _render_tool_results(tool_results: list[dict[str, Any]]) -> str:
    """Rút gọn dữ liệu tool thành khối văn bản có nhãn nguồn."""
    lines: list[str] = []
    for item in tool_results:
        tool = item.get("tool", "graphql")
        data = item.get("data")
        rendered = json.dumps(data, ensure_ascii=False, default=str)
        if len(rendered) > 900:
            rendered = rendered[:900] + "…"
        lines.append(f"- {tool}: {rendered}")
    return "\n".join(lines)


def _grounded_generate(
    query: str,
    sources: list[dict[str, str]],
    provider: str | None = None,
    tool_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Sinh câu trả lời trích dẫn nguồn từ tài liệu đã truy xuất (local-first).

    Không gọi mô hình ngôn ngữ ngoài: dùng nội dung nguồn đã có, gán nhãn nguồn
    và trả lời bằng văn bản kinh doanh chuẩn. Tuỳ dùng khi chưa cấu hình LLM/
    provider — khớp với chế độ local-first của Track D.

    `tool_results` (D4) là dữ liệu GraphQL chỉ-đọc; được gắn thành khối
    "Dữ liệu hệ thống" để người đọc phân biệt với tài liệu SOP.
    """
    provider_name = provider or "local_grounded"
    citations = [{k: v for k, v in s.items() if k != "content"} for s in sources]
    tool_results = tool_results or []
    tool_block = _render_tool_results(tool_results) if tool_results else ""

    parts: list[str] = []
    if sources:
        top = sources[0]
        source_refs = "\n".join(
            f"[{index}] {item['source']} — {item['section']}"
            for index, item in enumerate(sources, 1)
        )
        parts.append(
            "Dựa trên tài liệu nghiệp vụ đã truy xuất, câu trả lời cho "
            f"'{query}':\n\n{top['content'][:900]}\n\nNguồn tham khảo:\n{source_refs}"
        )
    elif not tool_results:
        parts.append("Không có tài liệu nghiệp vụ nào để làm căn cứ cho câu hỏi này.")

    if tool_block:
        parts.append(
            f"Dữ liệu hệ thống (GraphQL, chỉ đọc) cho '{query}':\n{tool_block}"
        )

    answer = "\n\n".join(parts)

    return {
        "answer": answer,
        "provider": provider_name if not tool_results else f"{provider_name}+graphql_readonly",
        "model": "docs_extract",
        "simulation": True,
        "citations": citations,
        "error": None,
    }


async def generate_node(
    state: AgentState,
    settings=None,
    client=None,
    provider: str | None = None,
) -> AgentState:
    """Generate a grounded answer from retrieved sources + read-only tool data."""
    if state["abstained"] or state["hitl_pending"]:
        return state
    query = state["query"]
    sources = state["sources"]
    result = _grounded_generate(
        query, sources, provider=provider, tool_results=state.get("tool_results")
    )
    state["answer"] = result["answer"]
    state["provider"] = result["provider"]
    state["model"] = result["model"]
    state["simulation"] = result["simulation"]
    state["citations"] = result["citations"]
    state["error"] = result["error"]
    return state


def format_node(state: AgentState) -> AgentState:
    """Finalize response shape (no mutation of answer)."""
    return state


# ---------------------------------------------------------------------------
# Graph runner
# ---------------------------------------------------------------------------


async def run_sop_agent(
    query: str,
    settings,
    client,
    provider: str | None = None,
    limit: int = 3,
    executor=None,
    enable_tools: bool = True,
) -> dict[str, Any]:
    """Run the SOP retrieval agent graph and return a serializable result.

    `executor` (D4) cho phép test inject GraphQL executor; mặc định chạy
    in-process trên schema Ariadne. `enable_tools=False` tắt hoàn toàn tool-use.
    """
    state = AgentState(query=query, provider=provider)

    classify_node(state)
    if state["hitl_pending"]:
        format_node(state)
        return {
            "answer": state["answer"],
            "abstained": state["abstained"],
            "abstain_reason": state["abstain_reason"],
            "write_action": state["write_action"],
            "hitl_pending": state["hitl_pending"],
            "hitl_request_id": state["hitl_request_id"],
            "sources": [],
            "provider": None,
            "model": None,
            "simulation": True,
            "error": None,
            "tool_calls": [],
            "tool_results": [],
            "tool_errors": [],
        }

    retrieve_node(state, settings, client, limit=limit)
    await tools_node(state, executor=executor, enable_tools=enable_tools)
    decide_node(state)
    if not state["abstained"]:
        await generate_node(state, settings, client, provider=provider)
    format_node(state)

    return {
        "answer": state["answer"],
        "abstained": state["abstained"],
        "abstain_reason": state["abstain_reason"],
        "write_action": state["write_action"],
        "hitl_pending": state["hitl_pending"],
        "hitl_request_id": state["hitl_request_id"],
        "sources": state["citations"],
        "provider": state["provider"],
        "model": state["model"],
        "simulation": state["simulation"],
        "error": state["error"],
        "tool_calls": state["tool_calls"],
        "tool_results": state["tool_results"],
        "tool_errors": state["tool_errors"],
    }
