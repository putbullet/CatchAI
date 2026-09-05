"""Tests for Ollama response parsing and Catch routing."""

import pytest

from brain.llm import CatchLLM, NormalResponse, ToolCallResponse, parse_response
from brain.router import route_response
from tools.registry import build_default_registry


def test_parse_normal_response() -> None:
    response = parse_response('{"type":"response","message":"Hello"}')

    assert isinstance(response, NormalResponse)
    assert response.message == "Hello"


def test_parse_tool_call_response() -> None:
    response = parse_response('{"type":"tool_call","tool":"search_files","arguments":{"query":"report"}}')

    assert isinstance(response, ToolCallResponse)
    assert response.arguments == {"query": "report"}


@pytest.mark.parametrize("raw", ["not json", "[]", '{"tool":"delete_everything"}', '{"type":"response","message":""}'])
def test_malformed_response_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_response(raw)


def test_markdown_fenced_json_is_accepted() -> None:
    response = parse_response('```json\n{"type":"response","message":"Hello"}\n```')

    assert isinstance(response, NormalResponse)


def test_router_rejects_unknown_tool() -> None:
    result = route_response('{"type":"tool_call","tool":"delete_everything","arguments":{}}', build_default_registry())

    assert result["success"] is True
    assert result["result"]["success"] is False
    assert "Unknown tool" in result["result"]["error"]


def test_ollama_adapter_uses_configured_model(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, host: str, timeout: float):
            captured["host"] = host
            captured["timeout"] = timeout

        def chat(self, **kwargs):
            captured.update(kwargs)
            return {"message": {"content": '{"type":"response","message":"Hello"}'}}

    monkeypatch.setattr("brain.llm.Client", FakeClient)
    llm = CatchLLM("http://test-host", "test-model", 0.2)

    raw = llm.complete("hello")

    assert raw == '{"type":"response","message":"Hello"}'
    assert captured["host"] == "http://test-host"
    assert captured["timeout"] == 30.0
    assert captured["model"] == "test-model"
    assert captured["format"] == "json"
    assert captured["think"] is False
    assert captured["options"] == {"temperature": 0.2, "num_predict": 128}
