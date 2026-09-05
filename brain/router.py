"""Route validated Catch LLM responses to the tool registry."""

from __future__ import annotations

from typing import Any

from brain.llm import NormalResponse, ToolCallResponse, parse_response
from tools.registry import ToolRegistry


def route_response(raw_response: str, registry: ToolRegistry) -> dict[str, Any]:
    """Parse an LLM response and execute only a validated registered tool."""
    try:
        response = parse_response(raw_response)
    except ValueError as error:
        return {"success": False, "error": str(error)}

    if isinstance(response, NormalResponse):
        return {"success": True, "type": "response", "message": response.message}

    if isinstance(response, ToolCallResponse):
        result = registry.execute(response.tool, response.arguments)
        return {"success": True, "type": "tool_result", "tool": response.tool, "result": result}

    return {"success": False, "error": "Unsupported Catch response"}
