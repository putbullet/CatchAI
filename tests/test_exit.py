"""Tests for CatchAI exit command classification and false-positive prevention."""

import pytest
from brain.fast_router import classify_exit_command
from brain.assistant import CatchAssistant


def test_classify_exit_exact_phrases() -> None:
    positive_phrases = [
        "exit",
        "quit",
        "close yourself",
        "goodbye",
        "bye",
        "kill",
        "kill yourself",
        "go away",
        "get out of here",
        "just go",
        "shut down",
        "leave",
        "stop",
        "terminate",
        "Hey Jarvis, exit",
        "Hey Jarvis, please quit",
        "Hey Jarvis, go away",
        "close yourself now",
        "just go please",
        "Catch, exit",
        "Catch, shut down",
    ]
    for phrase in positive_phrases:
        result = classify_exit_command(phrase)
        assert result is not None, f"Expected '{phrase}' to classify as exit"
        assert result["tool"] == "exit"


def test_classify_exit_false_positives() -> None:
    negative_phrases = [
        "I don't want to quit my job",
        "do not exit",
        "don't stop the music",
        "should I exit this program?",
        "why did you stop?",
        "quit the game",
        "stop the video",
        "kill the process",
        "exit the app",
        "leave the room",
        "kill my task",
    ]
    for phrase in negative_phrases:
        result = classify_exit_command(phrase)
        assert result is None, f"Expected '{phrase}' NOT to classify as exit, but got {result}"


def test_assistant_handles_exit_command() -> None:
    class DummyLLM:
        def complete(self, message, context=None):
            raise AssertionError("LLM should not be called for exit command")

    assistant = CatchAssistant(DummyLLM())
    result = assistant.handle_text("Hey Jarvis, goodbye")

    assert result["success"] is True
    assert result["type"] == "exit"
    assert "Goodbye!" in result["message"]
    assert result["fast_path"] is True
