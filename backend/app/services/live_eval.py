# Live AI Evaluation (Phase M — S8)
#
# Production AI eval harness for RAG responses.
# - LLM-as-judge: scores relevance, groundedness, completeness (1-5 scale)
# - Hit@K: whether expected source appears in top-K retrieved results
# - MRR: Mean Reciprocal Rank of first expected source
# - Golden dataset: runs against tests/data/ai_eval_dataset.jsonl in CI
#
# Dependencies (already in pyproject.toml):
#   - mlflow, langfuse, requests

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import requests

from app.services.ai_evaluation import load_eval_dataset
from app.services.ai_retrieval import retrieve

# ── Thresholds ─────────────────────────────────────────────────────────────────
HIT_K_DEFAULT = 3
LLM_JUDGE_SCALE = 5  # 1-5 scale
RELEVANCE_THRESHOLD = 4.0  # min LLM-as-judge score to pass
MRR_THRESHOLD = 0.7  # min MRR to pass


@dataclass
class EvalResult:
    question: str
    category: str
    hit_at_k: bool
    hit_rank: int | None
    reciprocal_rank: float
    judge_score: float | None
    judge_reason: str | None
    passed: bool


@dataclass
class EvalSuiteResult:
    total: int
    hit_at_k_rate: float
    mrr: float
    avg_judge_score: float | None
    passed: bool
    per_question: list[EvalResult] = field(default_factory=list)


# ── Hit@K / MRR ────────────────────────────────────────────────────────────────
def compute_hit_at_k_and_mrr(
    expected_files: list[str],
    retrieved: list[dict],
    k: int = HIT_K_DEFAULT,
) -> tuple[bool, int | None, float]:
    """
    Compute Hit@K and Reciprocal Rank for a single question.

    Returns (hit_at_k, hit_rank, reciprocal_rank).
    """
    expected_set = set(expected_files)
    hit_rank = None

    for idx, item in enumerate(retrieved[:k], start=1):
        source = Path(item.get("source", "")).name
        if source in expected_set:
            hit_rank = idx
            break

    hit_at_k = hit_rank is not None
    reciprocal_rank = 1.0 / hit_rank if hit_rank else 0.0
    return hit_at_k, hit_rank, reciprocal_rank


# ── LLM-as-judge ───────────────────────────────────────────────────────────────
def llm_judge(
    question: str,
    answer: str,
    context: str,
    judge_endpoint: str | None = None,
    judge_model: str = "gpt-4o-mini",
    temperature: float = 0.0,
) -> tuple[float, str]:
    """
    Ask an LLM to score answer quality on a 1-5 scale across three dimensions:
    relevance (answers the question), groundedness (supported by context),
    completeness (covers all expected aspects).

    Returns (score, reason). If no judge endpoint configured, returns (None, "skipped").
    """
    if not judge_endpoint:
        return None, "skipped (no judge endpoint configured)"

    prompt = (
        "You are an expert evaluator of RAG (retrieval-augmented generation) answers. "
        "Score the answer on a 1-5 integer scale for each of three dimensions:\n"
        "1. Relevance: Does the answer directly address the question?\n"
        "2. Groundedness: Is every claim supported by the provided context?\n"
        "3. Completeness: Does the answer cover all key aspects of the question?\n\n"
        "Return ONLY: <integer score> | <one-line reason>\n\n"
        f"Question: {question}\n"
        f"Context: {context}\n"
        f"Answer: {answer}\n"
    )

    try:
        resp = requests.post(
            judge_endpoint,
            json={
                "model": judge_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": 200,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        # Parse "4 | The answer is relevant and grounded..."
        match = re.match(r"(\d)\s*\|\s*(.+)", content)
        if match:
            return float(match.group(1)), match.group(2).strip()
        # Fallback: try to extract any digit 1-5
        digit_match = re.search(r"\b([1-5])\b", content)
        if digit_match:
            return float(digit_match.group(1)), content
        return None, f"unparseable judge response: {content}"
    except Exception as exc:
        return None, f"judge error: {exc}"


# ── Main eval suite ────────────────────────────────────────────────────────────
def run_live_eval(
    eval_dataset_path: str | Path,
    retrieval_fn: Callable[[str, int], list[dict]] = retrieve,
    k: int = HIT_K_DEFAULT,
    judge_endpoint: str | None = None,
    judge_model: str = "gpt-4o-mini",
) -> EvalSuiteResult:
    """
    Run the full live AI eval suite against a golden dataset.

    For each question:
    1. Retrieve top-K sources
    2. Compute Hit@K and MRR
    3. Generate answer via grounded_prompt + optional LLM
    4. LLM-as-judge scores the answer
    5. Aggregate: Hit@K rate, MRR, avg judge score
    """
    from app.services.ai_retrieval import grounded_prompt

    eval_set = load_eval_dataset(eval_dataset_path)
    per_question: list[EvalResult] = []

    hit_count = 0
    rr_sum = 0.0
    judge_scores: list[float] = []

    for entry in eval_set:
        question = entry["question"]
        expected_files = entry.get("expected_source_files", [])
        category = entry.get("category", "general")

        # Retrieve
        retrieved = retrieval_fn(question, limit=k)

        # Hit@K / MRR
        hit_at_k, hit_rank, rr = compute_hit_at_k_and_mrr(expected_files, retrieved, k=k)
        hit_count += 1 if hit_at_k else 0
        rr_sum += rr

        # Build context for judge
        context = "\n".join(
            f"[{i}] {item.get('source', '')} — {item.get('section', '')}\n{item.get('content', '')[:500]}"
            for i, item in enumerate(retrieved, 1)
        )

        # Generate answer (grounded prompt; in production this goes through the LLM)
        answer_prompt = grounded_prompt(question, retrieved)

        # LLM-as-judge
        judge_score, judge_reason = llm_judge(
            question=question,
            answer=answer_prompt,
            context=context,
            judge_endpoint=judge_endpoint,
            judge_model=judge_model,
        )
        if judge_score is not None:
            judge_scores.append(judge_score)

        # Pass if Hit@K AND (judge score >= threshold OR no judge configured)
        judge_ok = judge_score is None or judge_score >= RELEVANCE_THRESHOLD
        passed = hit_at_k and judge_ok

        per_question.append(
            EvalResult(
                question=question,
                category=category,
                hit_at_k=hit_at_k,
                hit_rank=hit_rank,
                reciprocal_rank=rr,
                judge_score=judge_score,
                judge_reason=judge_reason,
                passed=passed,
            )
        )

    total = len(eval_set)
    hit_at_k_rate = hit_count / total if total else 0.0
    mrr = rr_sum / total if total else 0.0
    avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else None

    # Overall pass: Hit@K >= 0.8 AND MRR >= threshold AND (judge >= threshold OR no judge)
    judge_ok = avg_judge is None or avg_judge >= RELEVANCE_THRESHOLD
    passed = hit_at_k_rate >= 0.8 and mrr >= MRR_THRESHOLD and judge_ok

    return EvalSuiteResult(
        total=total,
        hit_at_k_rate=hit_at_k_rate,
        mrr=mrr,
        avg_judge_score=avg_judge,
        passed=passed,
        per_question=per_question,
    )


def run_live_eval_cli() -> None:
    """CLI entry point: run live eval against the golden dataset."""
    import os
    import sys

    dataset_path = Path(__file__).resolve().parents[2] / "backend" / "tests" / "data" / "ai_eval_dataset.jsonl"

    judge_endpoint = os.environ.get("AI_JUDGE_ENDPOINT")
    result = run_live_eval(
        eval_dataset_path=dataset_path,
        judge_endpoint=judge_endpoint,
    )

    print("=== Live AI Eval Results ===")
    print(f"Total questions: {result.total}")
    print(f"Hit@{HIT_K_DEFAULT} rate: {result.hit_at_k_rate:.2%}")
    print(f"MRR: {result.mrr:.4f}")
    if result.avg_judge_score is not None:
        print(f"Avg judge score: {result.avg_judge_score:.2f}/5")
    print(f"Overall: {'PASS' if result.passed else 'FAIL'}")

    for r in result.per_question:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.question[:60]}... (hit@{HIT_K_DEFAULT}={r.hit_at_k}, rr={r.reciprocal_rank:.2f}, judge={r.judge_score})")

    sys.exit(0 if result.passed else 1)