"""RAG evaluation harness for the BankOps AI retrieval index.

Provides:
- load_eval_dataset(path): load a JSONL eval set.
- evaluate_rag(retrieval_fn, eval_set, k=3): run retrieval over every question and
  report Recall@K plus citation accuracy, with per-question detail and aggregates.

Citation accuracy is measured against the *retrieved* sources that an answer would
be grounded on: a question is citation-accurate when every expected source file is
present among the retrieved results (so an answer can cite all expected sources
correctly). Recall@K is true when at least one expected source file appears in the
top-K retrieved documents.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path

RetrievalFn = Callable[[str, int], list[dict]]


def load_eval_dataset(path: str | Path) -> list[dict]:
    """Load an eval dataset from a JSONL file.

    Each line is a JSON object with keys:
    question, expected_answer, expected_source_files, expected_source_sections,
    category.
    """
    path = Path(path)
    entries: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def _source_files(results: Iterable[dict]) -> list[str]:
    # retrieval_fn returns source like "docs/05-workflows.md"; normalize to the
    # bare filename so it matches the dataset's expected_source_files.
    return [Path(item.get("source", "")).name for item in results]


def evaluate_rag(
    retrieval_fn: RetrievalFn,
    eval_set: list[dict],
    k: int = 3,
) -> dict:
    """Run retrieval over every eval question and score RAG quality.

    Returns a dict with ``k``, ``total_questions``, ``aggregate`` metrics and a
    ``per_question`` list of detailed results.
    """
    per_question: list[dict] = []
    recall_hits = 0
    citation_hits = 0

    for entry in eval_set:
        question = entry["question"]
        expected_files = set(entry.get("expected_source_files") or [])
        expected_sections = set(entry.get("expected_source_sections") or [])

        results = retrieval_fn(question, limit=k)
        retrieved_files = _source_files(results)
        retrieved_sections = [item.get("section", "") for item in results]
        retrieved_file_set = set(retrieved_files)

        # Recall@K: at least one expected source file in top-K results.
        recall_ok = bool(expected_files & retrieved_file_set)

        # Citation accuracy: every expected source file is present among the
        # retrieved sources, so an answer grounded on them can cite correctly.
        citation_ok = expected_files.issubset(retrieved_file_set) if expected_files else False

        if recall_ok:
            recall_hits += 1
        if citation_ok:
            citation_hits += 1

        per_question.append(
            {
                "question": question,
                "category": entry.get("category"),
                "expected_source_files": sorted(expected_files),
                "expected_source_sections": sorted(expected_sections),
                "retrieved_source_files": retrieved_files,
                "retrieved_source_sections": retrieved_sections,
                "retrieved_count": len(results),
                "recall_at_k": recall_ok,
                "citation_accuracy": citation_ok,
            }
        )

    total = len(eval_set)
    aggregate = {
        "recall_at_k": (recall_hits / total) if total else 0.0,
        "citation_accuracy": (citation_hits / total) if total else 0.0,
        "recall_hits": recall_hits,
        "citation_hits": citation_hits,
    }

    return {
        "k": k,
        "total_questions": total,
        "aggregate": aggregate,
        "per_question": per_question,
    }
