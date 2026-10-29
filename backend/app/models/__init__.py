"""Model package — registry of every SQLAlchemy model.

Why this file exists
--------------------
Alembic's autogenerate compares ``Base.metadata`` against the live database.
A model that is never imported is invisible to that comparison, so its table
looks like a table that exists in the database but is *unknown* to the
application — autogenerate then reports it as "removed" and wants to DROP it
(e.g. ``sync_requests``).

Importing every model module from the package ``__init__`` guarantees that
``Base.metadata`` is complete regardless of the entry point that loads the
models (uvicorn, alembic, pytest, scripts). ``app.models.<module>`` imports
keep working exactly as before — importing a submodule always executes this
package first.
"""

from app.db.base import Base
from app.models import (
    activity,  # noqa: F401
    approval,  # noqa: F401
    cash_sim,  # noqa: F401
    etl,  # noqa: F401
    expense,  # noqa: F401
    iam,  # noqa: F401
    idempotency,  # noqa: F401
    integration,  # noqa: F401
    inventory,  # noqa: F401
    otp,  # noqa: F401
    reconciliation,  # noqa: F401
    schema_parity,  # noqa: F401
    stock_level,  # noqa: F401
    sync_request,  # noqa: F401
)


def _drop_duplicate_indexes() -> None:
    """Keep only one index object per index name.

    ``app/models/expense.py`` declares ``ix_expenses_expense_date`` twice
    (once through ``index=True`` on the column and once through
    ``__table_args__``). SQLAlchemy accepts both objects, but
    ``Base.metadata.create_all`` then emits two ``CREATE INDEX`` statements
    with the same name and creating the schema from scratch fails with
    ``relation "ix_expenses_expense_date" already exists``.

    The duplicate is dropped here instead of in the model module because that
    module belongs to another change stream. Both objects describe the same
    columns, so keeping one is enough.
    """
    for table in Base.metadata.tables.values():
        seen: set[str] = set()
        for index in list(table.indexes):
            if index.name in seen:
                table.indexes.discard(index)
            else:
                seen.add(index.name)


_drop_duplicate_indexes()

__all__ = [
    "activity",
    "approval",
    "cash_sim",
    "etl",
    "expense",
    "iam",
    "idempotency",
    "integration",
    "inventory",
    "otp",
    "reconciliation",
    "schema_parity",
    "stock_level",
    "sync_request",
]
