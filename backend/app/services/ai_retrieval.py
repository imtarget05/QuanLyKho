"""Backward-compat shim: code AI da chuyen sang `app/ai/retrieval` (P1.13)."""
from app.ai.retrieval import (  # noqa: F401
    BUILTIN_SOP_KNOWLEDGE,
    DOCS_ROOT,
    SOURCE_FILES,
    _terms,
    grounded_prompt,
    retrieve,
)
