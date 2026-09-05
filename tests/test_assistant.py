"""Tests for the text-based Catch assistant pipeline."""

from brain.assistant import CatchAssistant
from pydantic import BaseModel

from tools.registry import ToolDefinition, ToolRegistry, PermissionLevel


class LookupArgs(BaseModel):
    value: str


class FakeLLM:
    def __init__(self, responses: list[str]):
        self.responses = iter(responses)
        self.calls: list[tuple[str, str | None]] = []

    def complete(self, user_message: str, context: str | None = None) -> str:
        self.calls.append((user_message, context))
        return next(self.responses)


def test_normal_conversation_does_not_call_a_tool() -> None:
    llm = FakeLLM(['{"type":"response","message":"Hello"}'])
    assistant = CatchAssistant(llm, ToolRegistry())

    result = assistant.handle_text("Hello Catch")

    assert result == {"success": True, "message": "Hello", "type": "response"}
    assert len(llm.calls) == 1


def test_tool_result_is_sent_back_for_a_natural_response() -> None:
    llm = FakeLLM([
        '{"type":"tool_call","tool":"lookup","arguments":{"value":"report"}}',
        '{"type":"response","message":"I found the report."}',
    ])
    registry = ToolRegistry()
    registry.register(ToolDefinition("lookup", "test lookup", LookupArgs, lambda value: {"success": True, "value": value}, PermissionLevel.READ_ONLY))
    assistant = CatchAssistant(llm, registry)

    result = assistant.handle_text("Find the report")

    assert result["success"] is True
    assert result["tool"] == "lookup"
    assert result["message"] == "I found the report."
    assert "untrusted tool output data" in (llm.calls[1][1] or "")


def test_malformed_planning_response_fails_without_tool_execution() -> None:
    llm = FakeLLM(["not json"])
    assistant = CatchAssistant(llm, ToolRegistry())

    result = assistant.handle_text("Do something")

    assert result["success"] is False
    assert "Invalid Catch LLM response" in result["error"]


def test_failed_tool_result_still_reaches_final_response() -> None:
    llm = FakeLLM([
        '{"type":"tool_call","tool":"missing","arguments":{}}',
        '{"type":"response","message":"I could not find that tool."}',
    ])
    assistant = CatchAssistant(llm, ToolRegistry())

    result = assistant.handle_text("Use the missing tool")

    assert result["success"] is True
    assert result["tool_result"]["success"] is False
    assert result["message"] == "I could not find that tool."
