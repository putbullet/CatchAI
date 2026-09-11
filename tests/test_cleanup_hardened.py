"""Tests for disk cleanup, drive detection, confirmation flow, and error resilience."""

from pathlib import Path
import pytest
from brain.assistant import CatchAssistant
from brain.fast_router import classify_cleanup_command
from tools.cleanup import delete_temp_files, scan_temp_files, get_available_drives


def test_classify_cleanup_commands_with_drives() -> None:
    assert classify_cleanup_command("clean C drive") == {"tool": "clear_temp_files", "arguments": {"drive": "C"}}
    assert classify_cleanup_command("clean C:") == {"tool": "clear_temp_files", "arguments": {"drive": "C"}}
    assert classify_cleanup_command("clean D drive") == {"tool": "clear_temp_files", "arguments": {"drive": "D"}}
    assert classify_cleanup_command("free disk space") == {"tool": "clear_temp_files", "arguments": {}}
    assert classify_cleanup_command("clean my computer") == {"tool": "clear_temp_files", "arguments": {}}
    assert classify_cleanup_command("clear temp files") == {"tool": "clear_temp_files", "arguments": {}}


def test_get_available_drives() -> None:
    drives = get_available_drives()
    assert isinstance(drives, list)
    assert len(drives) >= 1
    assert all(isinstance(d, str) and len(d) == 1 for d in drives)


def test_delete_temp_files_safe_boundary(tmp_path: Path) -> None:
    # Files inside a 'temp' folder are allowed
    temp_dir = tmp_path / "AppData" / "Local" / "Temp"
    temp_dir.mkdir(parents=True)
    temp_file = temp_dir / "test_junk.tmp"
    temp_file.write_text("junk data")

    # File outside any temp folder (should be protected)
    protected_dir = tmp_path / "Documents"
    protected_dir.mkdir(parents=True)
    protected_file = protected_dir / "important.docx"
    protected_file.write_text("precious")

    items = [
        {"path": str(temp_file), "size": len("junk data")},
        {"path": str(protected_file), "size": len("precious")},
    ]

    result = delete_temp_files(items)
    assert result["success"] is True
    assert result["deleted"] == 1
    assert result["skipped"] == 1
    assert not temp_file.exists()
    assert protected_file.exists()


def test_cleanup_confirmation_flow(monkeypatch, tmp_path: Path) -> None:
    temp_dir = tmp_path / "Temp"
    temp_dir.mkdir()
    f1 = temp_dir / "a.tmp"
    f1.write_text("aaa")

    monkeypatch.setattr(
        "brain.assistant.scan_temp_files",
        lambda drive=None: {"success": True, "items": [{"path": str(f1), "size": 3}], "count": 1, "size": 3},
    )

    class DummyLLM:
        def complete(self, message, context=None):
            raise AssertionError("LLM should not be called")

    assistant = CatchAssistant(DummyLLM())

    # Step 1: User asks to clean temporary files
    step1 = assistant.handle_text("clean temporary files")
    assert step1["tool"] == "clear_temp_files"
    assert step1["tool_result"]["confirmation_required"] is True
    assert assistant.pending_cleanup_items is not None
    assert f1.exists()

    # Step 2: User confirms with "yes"
    step2 = assistant.handle_text("yes")
    assert step2["tool"] == "clear_temp_files"
    assert step2["tool_result"]["deleted"] == 1
    assert not f1.exists()
    assert assistant.pending_cleanup_items is None


def test_cleanup_cancellation_flow(monkeypatch) -> None:
    monkeypatch.setattr(
        "brain.assistant.scan_temp_files",
        lambda drive=None: {"success": True, "items": [{"path": "dummy.tmp", "size": 100}], "count": 1, "size": 100},
    )

    class DummyLLM:
        def complete(self, message, context=None):
            raise AssertionError("LLM should not be called")

    assistant = CatchAssistant(DummyLLM())
    assistant.handle_text("clean temporary files")
    assert assistant.pending_cleanup_items is not None

    cancel_step = assistant.handle_text("no")
    assert cancel_step["success"] is True
    assert "won't clear" in cancel_step["message"]
    assert assistant.pending_cleanup_items is None
