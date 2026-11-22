"""Read-only GraphQL tools cho SOP agent (Track D — D4).

Agent chỉ được phép **ĐỌC** dữ liệu qua GraphQL. Mọi mutation/subscription bị
chặn ở hai lớp trước khi executor được gọi:

1. **Registry đóng gói** — agent chỉ chọn tool theo tên trong `TOOLS`; document
   của tool là hằng số, không do người dùng soạn.
2. **AST guard** (`assert_read_only`) — parse document bằng graphql-core, bắt
   buộc operation type là `query`, đúng một operation, root field nằm trong
   `ALLOWED_ROOT_FIELDS`, không introspection, giới hạn kích thước/độ sâu.

Đây là fail-closed: mọi lỗi parse/không nhận diện đều bị coi là vi phạm.

Ghi chú bảo mật (ADR 0002): tool chỉ đọc — không tạo phiếu, không sửa số dư.
Hành động ghi vẫn phải qua HITL gate trong `ai_agent.py`.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from graphql import GraphQLError, parse
from graphql.language import OperationType

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Root fields của `Query` trong `app/graphql/schema.graphql` — chỉ đọc.
ALLOWED_ROOT_FIELDS: frozenset[str] = frozenset(
    {
        "account",
        "accounts",
        "balance",
        "ledgerEntry",
        "ledgerEntries",
        "saga",
        "sagas",
        "auditEntry",
        "auditTrail",
        "outboxEvent",
        "outboxEvents",
        "verifyAuditChain",
        "health",
    }
)

_BLOCKED_INTROSPECTION_FIELDS = frozenset({"__schema", "__type"})
_MAX_DOCUMENT_CHARS = 4_000
_MAX_FIELDS = 40

Executor = Callable[[str, "dict[str, Any] | None"], Awaitable[dict[str, Any]]]


class ReadOnlyViolation(ValueError):
    """Document/tool không đạt kiểm tra chỉ-đọc (fail-closed)."""


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    document: str
    keywords: tuple[str, ...]
    variables: dict[str, Any] = field(default_factory=dict)


TOOLS: dict[str, ToolSpec] = {
    "service_health": ToolSpec(
        name="service_health",
        description="Trạng thái sống của dịch vụ GraphQL (không cần DB).",
        document="query AgentHealth { health { status service timestamp } }",
        keywords=("health", "sức khỏe hệ thống", "trạng thái hệ thống", "service status"),
    ),
    "account_balances": ToolSpec(
        name="account_balances",
        description="Danh sách tài khoản GL và số dư multi-tier (ledger/available/hold).",
        document=(
            "query AgentAccounts($limit: Int) {"
            " accounts(limit: $limit) {"
            " code ledgerBalance availableBalance holdBalance version"
            " } }"
        ),
        keywords=(
            "số dư",
            "so du",
            "balance",
            "tài khoản",
            "tai khoan",
            "ledger balance",
            "available balance",
            "hold balance",
        ),
        variables={"limit": 10},
    ),
    "saga_status": ToolSpec(
        name="saga_status",
        description="Trạng thái các saga chuyển tiền gần đây.",
        document=(
            "query AgentSagas($limit: Int) {"
            " sagas(limit: $limit) {"
            " id sagaName status currentStep errorMessage createdAt updatedAt"
            " } }"
        ),
        keywords=(
            "saga",
            "trạng thái giao dịch",
            "trang thai giao dich",
            "chuyển tiền",
            "chuyen tien",
            "transfer status",
        ),
        variables={"limit": 5},
    ),
    "outbox_events": ToolSpec(
        name="outbox_events",
        description="Sự kiện outbox và trạng thái phân phối.",
        document=(
            "query AgentOutbox($limit: Int) {"
            " outboxEvents(limit: $limit) {"
            " id topic eventType status attempts createdAt publishedAt"
            " } }"
        ),
        keywords=("outbox", "sự kiện", "su kien", "event", "hàng đợi", "hang doi"),
        variables={"limit": 10},
    ),
    "audit_trail": ToolSpec(
        name="audit_trail",
        description="Lịch sử kiểm toán (audit trail) gần nhất.",
        document=(
            "query AgentAudit($limit: Int) {"
            " auditTrail(limit: $limit) {"
            " totalCount hasMore"
            " entries { id action entityType entityId timestamp }"
            " } }"
        ),
        keywords=(
            "audit",
            "kiểm toán",
            "kiem toan",
            "lịch sử thao tác",
            "lich su thao tac",
            "truy vết",
            "truy vet",
        ),
        variables={"limit": 20},
    ),
}


# ---------------------------------------------------------------------------
# AST guard
# ---------------------------------------------------------------------------


def _strip_diacritics(value: str) -> str:
    plain = unicodedata.normalize("NFD", value.lower())
    return "".join(ch for ch in plain if unicodedata.category(ch) != "Mn")


def _iter_root_field_names(document_node) -> list[str]:
    """Lấy tên field ở cấp cao nhất của operation (bỏ qua fragment spreads)."""
    names: list[str] = []
    for definition in document_node.definitions:
        if not hasattr(definition, "selection_set") or definition.selection_set is None:
            continue
        for selection in definition.selection_set.selections:
            name = getattr(getattr(selection, "name", None), "value", None)
            if name:
                names.append(name)
    return names


def _count_fields(document_node) -> int:
    from graphql.language import FieldNode, SelectionSetNode

    total = 0
    stack: list[Any] = [document_node]
    while stack:
        node = stack.pop()
        if isinstance(node, FieldNode):
            total += 1
        if hasattr(node, "selection_set") and isinstance(node.selection_set, SelectionSetNode):
            stack.extend(node.selection_set.selections)
        for attr in ("definitions", "selections"):
            children = getattr(node, attr, None)
            if isinstance(children, (list, tuple)):
                stack.extend(children)
    return total


def assert_read_only(document: str) -> None:
    """Bảo đảm document chỉ là MỘT query chỉ-đọc hợp lệ.

    Raises:
        ReadOnlyViolation: khi document sai cú pháp, không phải query, có nhiều
            operation, dùng introspection, tham chiếu root field lạ, hoặc vượt
            giới hạn kích thước/độ phức tạp.
    """
    if not isinstance(document, str) or not document.strip():
        raise ReadOnlyViolation("GraphQL document rỗng.")
    if len(document) > _MAX_DOCUMENT_CHARS:
        raise ReadOnlyViolation("GraphQL document vượt giới hạn kích thước.")

    try:
        parsed = parse(document)
    except GraphQLError as exc:  # syntax error
        raise ReadOnlyViolation(f"GraphQL document không hợp lệ: {exc.message}") from exc

    operations = [d for d in parsed.definitions if hasattr(d, "operation")]
    if len(operations) != 1:
        raise ReadOnlyViolation("Chỉ cho phép đúng một GraphQL operation.")
    operation = operations[0]
    if operation.operation != OperationType.QUERY:
        raise ReadOnlyViolation(
            f"Chỉ cho phép GraphQL query read-only, nhận {operation.operation.value}."
        )

    root_fields = _iter_root_field_names(parsed)
    if not root_fields:
        raise ReadOnlyViolation("GraphQL query không có root field.")
    for field_name in root_fields:
        if field_name in _BLOCKED_INTROSPECTION_FIELDS:
            raise ReadOnlyViolation(f"Introspection bị chặn: {field_name}.")
        if field_name not in ALLOWED_ROOT_FIELDS:
            raise ReadOnlyViolation(f"Root field không nằm trong whitelist chỉ-đọc: {field_name}.")

    if _count_fields(parsed) > _MAX_FIELDS:
        raise ReadOnlyViolation("GraphQL query vượt giới hạn số field.")


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


def detect_tools(query: str, limit: int = 2) -> list[str]:
    """Chọn tool theo từ khóa (deterministic, theo thứ tự registry)."""
    plain = _strip_diacritics(query or "")
    matches: list[str] = []
    for name, spec in TOOLS.items():
        if len(matches) >= limit:
            break
        for keyword in spec.keywords:
            if _strip_diacritics(keyword) in plain:
                matches.append(name)
                break
    return matches


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


async def default_executor(document: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Thực thi query in-process trên schema Ariadne (không qua HTTP)."""
    from ariadne import graphql

    from app.graphql.router import schema

    success, payload = await graphql(
        schema,
        {"query": document, "variables": variables or {}},
    )
    if not success:
        errors = payload.get("errors") if isinstance(payload, dict) else payload
        raise RuntimeError(f"GraphQL execution failed: {errors}")
    data = payload.get("data") if isinstance(payload, dict) else None
    if data is None:
        raise RuntimeError("GraphQL execution trả về data rỗng.")
    return {"data": data}


async def _execute_document(
    document: str,
    variables: dict[str, Any] | None,
    executor: Executor | None,
) -> dict[str, Any]:
    """Guard rồi mới execute. Executor chỉ được gọi khi document đã hợp lệ."""
    assert_read_only(document)
    run = executor or default_executor
    return await run(document, variables)


async def call_tool(
    name: str,
    variables: dict[str, Any] | None = None,
    executor: Executor | None = None,
) -> dict[str, Any]:
    """Chạy 1 tool theo tên. Trả về `data` của GraphQL response."""
    spec = TOOLS.get(name)
    if spec is None:
        raise ReadOnlyViolation(f"Tool không tồn tại hoặc không được phép: {name}")

    merged_variables: dict[str, Any] = dict(spec.variables)
    if variables:
        merged_variables.update(variables)

    payload = await _execute_document(spec.document, merged_variables or None, executor)
    data = payload.get("data") if isinstance(payload, dict) else None
    if data is None:
        raise RuntimeError(f"Tool {name} không trả về data.")
    return data


async def run_tools(
    query: str,
    executor: Executor | None = None,
    limit: int = 2,
) -> dict[str, Any]:
    """Chọn và chạy các tool phù hợp với câu hỏi.

    Fail-soft: lỗi của một tool được ghi vào `errors`, không ném ra ngoài để
    agent vẫn có thể trả lời bằng tài liệu SOP.
    """
    calls: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for name in detect_tools(query, limit=limit):
        spec = TOOLS[name]
        calls.append({"tool": name, "query": spec.document, "variables": dict(spec.variables)})
        try:
            data = await call_tool(name, executor=executor)
        except Exception as exc:  # noqa: BLE001 — fail-soft by design
            errors.append({"tool": name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        results.append({"tool": name, "data": data})

    return {"calls": calls, "results": results, "errors": errors}
