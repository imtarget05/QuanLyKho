"""LangGraph stateful agent for RetailOps workflow.

Architecture:
  - Single agent + tool calling is preferred over multi-agent
  - Intent -> check stock -> draft order -> validate -> confirm -> commit
  - HITL: pause at confirmation, resume with verified actor
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from typing_extensions import TypedDict

from app.services.retail_agent.graph_state import RetailState
from app.services.retail_agent.nodes import (
    await_confirmation_node,
    cancel_order_node,
    check_stock_node,
    classify_intent,
    commit_order_node,
    draft_order_node,
    get_order_node,
    report_result,
    validate_node,
)


class RetailContext(TypedDict, total=False):
    access_token: str
    actor_id: str
    use_llm: bool


def build_retail_graph(checkpointer=None):
    """Build the RetailOps agent state graph.

    Args:
        checkpointer: optional durable checkpointer (e.g. MemorySaver for MVP).
                      Defaults to MemorySaver so thread_id persists across
                      interrupt/resume within the same process.
    """
    builder = StateGraph(RetailState, context_schema=RetailContext)

    # Nodes
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("check_stock", check_stock_node)
    builder.add_node("draft_order", draft_order_node)
    builder.add_node("get_order", get_order_node)
    builder.add_node("validate_conditions", validate_node)
    builder.add_node("await_confirmation", await_confirmation_node)
    builder.add_node("commit_order", commit_order_node)
    builder.add_node("cancel_order", cancel_order_node)
    builder.add_node("report_result", report_result)

    builder.add_conditional_edges(
        "classify_intent",
        lambda state: (
            "cancel_order" if state.get("intent") == "cancel_request"
            else "draft_order" if state.get("intent") == "draft_order"
            else "get_order" if state.get("intent") == "order_status"
            else "report_result" if state.get("intent") == "clarify"
            else "check_stock"
        ),
    )
    builder.add_conditional_edges(
        "check_stock",
        lambda state: "report_result",
    )
    builder.add_edge("draft_order", "validate_conditions")
    builder.add_edge("get_order", "report_result")
    builder.add_conditional_edges(
        "validate_conditions",
        lambda state: "await_confirmation" if state.get("validation_result") == "ready_to_confirm" else "report_result",
    )
    builder.add_edge("await_confirmation", "commit_order")
    builder.add_edge("commit_order", "report_result")
    builder.add_edge("cancel_order", "report_result")

    builder.set_entry_point("classify_intent")

    cp = checkpointer or MemorySaver()
    return builder.compile(checkpointer=cp)
