#!/usr/bin/env python3
"""LLM-Judge Evaluation cho QuanLyKho (Option B).

Dùng LLM làm judge để chấm đáp án RAG trên các tiêu chí:
- Faithfulness: đáp án có tuân theo ngữ cảnh không?
- Relevance: đáp án có trả lời câu hỏi không?
- Completeness: có bao quát tất cả khái niệm yêu cầu không?
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class JudgeScore:
    score: float
    explanation: str
    metric: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JudgeResult:
    question_id: str
    question: str
    answer: str
    scores: list[JudgeScore]
    overall: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "answer": self.answer,
            "scores": [s.to_dict() for s in self.scores],
            "overall": self.overall,
        }


def _call_llm(prompt: str, base_url: str, model: str = "llama-3") -> str:
    import urllib.request

    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("choices", [{}])[0].get("message", {}).get("content", "")


def judge_answer(question: str, answer: str, context: str, base_url: str) -> JudgeResult:
    prompt = (
        "Bạn là LLM-Judge. Chấm đáp án RAG thang 0-1 theo các tiêu chí: "
        "faithfulness (tuân theo ngữ cảnh), relevance (trả lời câu hỏi), "
        "completeness (bao quát khái niệm yêu cầu). Trả về JSON:\n"
        '{"faithfulness": {"score": 0.0, "explanation": ""}, ...}\n'
        f"Câu hỏi: {question}\nNgữ cảnh: {context}\nĐáp án: {answer}"
    )
    raw = _call_llm(prompt, base_url)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {"faithfulness": {"score": 0.5, "explanation": "parse failed"}}
    scores = [JudgeScore(m, v.get("score", 0.0), v.get("explanation", "")) for m, v in parsed.items()]
    overall = sum(s.score for s in scores) / len(scores) if scores else 0.0
    return JudgeResult(question_id="", question=question, answer=answer, scores=scores, overall=overall)
