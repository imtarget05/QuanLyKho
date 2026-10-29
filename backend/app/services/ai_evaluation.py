"""Backward-compat shim: code AI da chuyen sang `app/ai/evaluation` (P1.13)."""
from app.ai.evaluation import (  # noqa: F401
    RetrievalFn,
    evaluate_rag,
    load_eval_dataset,
)
