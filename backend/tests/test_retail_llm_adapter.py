"""The Ollama transport envelope must not be mistaken for model output."""

import httpx

from app.services.retail_agent import llm


def test_chat_parses_model_response_inside_ollama_envelope(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:1.5b",
                "response": '{"outcome":"clarify","tools":[],"args":{}}',
                "done": True,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://ollama")
    monkeypatch.setattr(llm, "_CLIENT", client)
    result = llm.chat("Mua hàng")
    assert result["outcome"] == "clarify"
    assert result["tools"] == []
    assert "response" not in result


def test_chat_fails_closed_on_missing_model_response(monkeypatch):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"done": True})),
        base_url="http://ollama",
    )
    monkeypatch.setattr(llm, "_CLIENT", client)
    result = llm.chat("Mua hàng")
    assert result["outcome"] == "unknown"
