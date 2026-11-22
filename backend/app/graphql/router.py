"""GraphQL router for QuanLyKho banking & inventory domain.

Loads schema from schema.graphql and wires resolvers.
Mounted on FastAPI at /graphql via ASGI app.
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from ariadne import (
    MutationType,
    ObjectType,
    QueryType,
    ScalarType,
    SubscriptionType,
    graphql,
    load_schema_from_path,
    make_executable_schema,
)
from ariadne.asgi import GraphQL
from fastapi import Request
from fastapi.responses import JSONResponse

from app.graphql.context import build_context
from app.graphql.resolvers import (
    account_type_resolvers,
    mutation_resolvers,
    query_resolvers,
    subscription_resolvers,
)

SCHEMA_PATH = Path(__file__).parent / "schema.graphql"

type_defs = load_schema_from_path(str(SCHEMA_PATH))

# ── Custom scalar resolvers ───────────────────────────────────────────────
decimal_scalar = ScalarType("Decimal")
uuid_scalar = ScalarType("UUID")
datetime_scalar = ScalarType("DateTime")


@decimal_scalar.serializer
def serialize_decimal(value):
    return str(value) if value is not None else None


@decimal_scalar.value_parser
def parse_decimal(value):
    return Decimal(str(value))


@decimal_scalar.literal_parser
def parse_decimal_literal(ast):
    return Decimal(ast.value)


@uuid_scalar.serializer
def serialize_uuid(value):
    return str(value) if value is not None else None


@uuid_scalar.value_parser
def parse_uuid(value):
    return str(UUID(str(value)))


@uuid_scalar.literal_parser
def parse_uuid_literal(ast):
    return str(UUID(ast.value))


@datetime_scalar.serializer
def serialize_datetime(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


@datetime_scalar.value_parser
def parse_datetime(value):
    return datetime.fromisoformat(str(value))


@datetime_scalar.literal_parser
def parse_datetime_literal(ast):
    return datetime.fromisoformat(ast.value)


# ── Type objects (Ariadne code-first, required for issubclass checks) ─────
query_type = QueryType()
for _field, _resolver in query_resolvers.items():
    query_type.set_field(_field, _resolver)

mutation_type = MutationType()
for _field, _resolver in mutation_resolvers.items():
    mutation_type.set_field(_field, _resolver)

subscription_type = SubscriptionType()
for _field, _resolver in subscription_resolvers.items():
    subscription_type.set_field(_field, _resolver)

account_type = ObjectType("Account")
for _field, _resolver in account_type_resolvers.items():
    account_type.set_field(_field, _resolver)


schema = make_executable_schema(
    type_defs,
    query_type,
    mutation_type,
    subscription_type,
    account_type,
    decimal_scalar,
    uuid_scalar,
    datetime_scalar,
)

# ASGI app for GraphQL (supports both sync execute and GraphQL POST)
graphql_app = GraphQL(
    schema,
    debug=os.getenv("APP_ENV", "dev") == "dev",
    context_value=lambda request: build_context(request),
)


async def graphql_endpoint(request: Request) -> JSONResponse:
    """HTTP POST endpoint for GraphQL queries/mutations.

    Reads Idempotency-Key header for idempotent mutation handling.
    Returns standard GraphQL JSON response.
    """
    body = await request.json()
    query = body.get("query")
    variables = body.get("variables")
    operation_name = body.get("operationName")

    # Extract idempotency key from header for mutation idempotency
    idempotency_key = request.headers.get("Idempotency-Key")

    # Inject context for resolvers (fresh DataLoaders per request — A6)
    context_value = build_context(request, idempotency_key)

    result = await graphql(
        schema,
        {
            "query": query,
            "variables": variables,
            "operationName": operation_name,
        },
        context_value=context_value,
    )

    success, data = result
    status_code = 200 if success else 400
    return JSONResponse(content=data, status_code=status_code)