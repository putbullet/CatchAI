"""Tests for Catch's default desktop launch behavior."""

import sys

import main


def test_no_arguments_default_to_tray(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["Catch.exe"])
    monkeypatch.setattr(main, "run_tray", lambda: 0)

    assert main.main() == 0
