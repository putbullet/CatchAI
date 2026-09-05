"""Ollama client and strict response parsing for Catch."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Literal

from ollama import Client
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from brain.prompts import build_system_prompt
from config import load_config

# If you later add per-user/session permission filtering (e.g. a
# settings toggle that hides destructive_action tools until the user
# opts in), do that filtering here before passing tools into
# build_system_prompt — format_tool_catalog just renders whatever list
# it's given, it doesn't do the gating itself.
try:
    from tools.registry import build_default_registry
except ImportError:  # registry not wired up yet, or different API
    build_default_registry = None


class ToolCallResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_call"]
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class NormalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["response"]
    message: str = Field(min_length=1)


class ClarifyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["clarify"]
    message: str = Field(min_length=1)


CatchResponse = ToolCallResponse | NormalResponse | ClarifyResponse


class CatchLLM:
    """Small Ollama adapter configured entirely from config.yaml."""

    def __init__(
        self,
        host: str,
        model: str,
        temperature: float = 0.1,
        timeout_seconds: float = 30.0,
        think: bool = False,
        max_tokens: int = 128,
        few_shot: bool = False,
        tools: Any = None,
        on_event: Callable[[str, float], None] | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.think = think
        self.max_tokens = max_tokens
        self.few_shot = few_shot
        self.on_event = on_event
        self.client = Client(host=host, timeout=timeout_seconds)
        self.system_prompt = build_system_prompt(tools=tools, few_shot=few_shot)

    @classmethod
    def from_config(cls) -> "CatchLLM":
        config = load_config().get("llm", {})
        if config.get("provider", "ollama") != "ollama":
            raise ValueError("Catch currently supports only the Ollama provider")
        tools = build_default_registry().definitions() if build_default_registry is not None else None
        return cls(
            host=str(config.get("host", "http://localhost:11434")),
            model=str(config.get("model", "")),
            temperature=float(config.get("temperature", 0.1)),
            timeout_seconds=float(config.get("timeout_seconds", 30.0)),
            think=bool(config.get("think", False)),
            max_tokens=int(config.get("max_tokens", 128)),
            few_shot=bool(config.get("few_shot", False)),
            tools=tools,
        )

    def refresh_system_prompt(self, tools: Any = None) -> None:
        """Rebuild the system prompt, e.g. after the user grants/revokes
        a folder or tool permission mid-session. Cheap to call — just
        string assembly, no network round trip."""
        self.system_prompt = build_system_prompt(tools=tools, few_shot=self.few_shot)

    def complete(self, user_message: str, context: str | None = None) -> str:
        """Ask Ollama for one JSON response."""
        if not user_message.strip():
            raise ValueError("User message cannot be empty")
        messages = [{"role": "system", "content": self.system_prompt}]
        if context:
            messages.append({"role": "user", "content": context})
        messages.append({"role": "user", "content": user_message})
        if self.on_event is not None:
            self.on_event("ollama_start", time.perf_counter())
        response = self.client.chat(
            model=self.model,
            messages=messages,
            format="json",
            think=self.think,
            options={"temperature": self.temperature, "num_predict": self.max_tokens},
        )
        if hasattr(response, "message"):
            content = response.message.content
        else:
            content = response["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty response")
        if self.on_event is not None:
            completed = time.perf_counter()
            self.on_event("ollama_first_result", completed)
            self.on_event("ollama_complete", completed)
        return content.strip()


def parse_response(raw_response: str) -> CatchResponse:
    """Parse and validate one strict Catch response from Ollama."""
    cleaned = raw_response.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]).strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].lstrip()
    try:
        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("Response JSON must be an object")
        response_type = payload.get("type")
        if response_type == "tool_call":
            return ToolCallResponse.model_validate(payload)
        if response_type == "response":
            return NormalResponse.model_validate(payload)
        if response_type == "clarify":
            return ClarifyResponse.model_validate(payload)
        raise ValueError("Response type must be 'tool_call', 'response', or 'clarify'")
    except (json.JSONDecodeError, ValidationError, ValueError) as error:
        raise ValueError(f"Invalid Catch LLM response: {error}") from error