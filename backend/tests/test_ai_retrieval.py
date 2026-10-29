import pytest

from app.features.ai.routes import ChatRequest, chat_stream
from app.services.ai_retrieval import grounded_prompt, retrieve


def test_retrieval_cites_relevant_operational_document():
    sources = retrieve("maker checker duyệt phiếu trạng thái")
    assert sources
    assert any(source["source"] == "docs/05-workflows.md" for source in sources)
    prompt = grounded_prompt("Ai được duyệt?", sources)
    assert "[1]" in prompt
    assert "docs/" in prompt


def test_retrieval_abstains_without_matching_evidence():
    assert retrieve("xyzzy quux blorb") == []


@pytest.mark.asyncio
async def test_chat_stream_returns_sse_without_inventing_an_answer():
    user = type('UserStub', (), {'id': 'retrieval-test-user', 'status': 'active'})()
    response = await chat_stream(ChatRequest(message='xyzzy quux blorb'), user)
    frames = [frame async for frame in response.body_iterator]
    assert response.media_type == 'text/event-stream'
    assert 'event: sources' in frames[0]
    assert 'Chưa tìm thấy thông tin' in ''.join(frames)
    assert 'event: done' in frames[-1]


def test_retrieval_finds_dual_control_and_500_million_rule():
    sources = retrieve("Quy định duyệt phiếu trên 500 triệu?")
    assert sources
    assert sources[0]["source"] == "docs/05-workflows.md"
    assert "Dual Control & Limits" in sources[0]["section"]
    assert "500" in sources[0]["content"]


def test_retrieval_finds_reconciliation_discrepancy():
    sources = retrieve("Khi đối soát có chênh lệch cần làm gì?")
    assert sources
    assert any("Đối soát" in s["section"] for s in sources)


@pytest.mark.asyncio
async def test_chat_grounded_fallback_when_provider_fails():
    from app.features.ai.routes import chat
    user = type('UserStub', (), {'id': 'retrieval-test-user', 'status': 'active'})()
    res = await chat(ChatRequest(message="Quy định duyệt phiếu trên 500 triệu?"), user)
    assert "answer" in res
    assert "500" in res["answer"] or "tài liệu nghiệp vụ" in res["answer"]
    assert res["sources"]
    assert any("05-workflows.md" in s["source"] for s in res["sources"])
