"""Tests for Catch's one-shot voice pipeline."""

from pathlib import Path

from speech.pipeline import VoiceAssistant


class FakeAssistant:
    def __init__(self, result):
        self.result = result
        self.transcripts: list[str] = []

    def handle_text(self, transcript: str):
        self.transcripts.append(transcript)
        return self.result


def test_voice_pipeline_connects_recording_transcription_and_assistant(monkeypatch, tmp_path: Path) -> None:
    assistant = FakeAssistant({"success": True, "message": "Found it"})
    monkeypatch.setattr("speech.pipeline.tempfile.NamedTemporaryFile", lambda **kwargs: open(tmp_path / "sample.wav", "wb"))
    monkeypatch.setattr("speech.pipeline.record_audio", lambda duration_seconds, output_path, device: 5.0)
    monkeypatch.setattr("speech.pipeline.transcribe_audio", lambda path: ("Find my report", 0.8))

    result = VoiceAssistant(assistant).run_once(device=2)

    assert result["success"] is True
    assert result["transcript"] == "Find my report"
    assert result["transcription_time"] == 0.8
    assert assistant.transcripts == ["Find my report"]


def test_voice_pipeline_does_not_call_assistant_without_speech(monkeypatch, tmp_path: Path) -> None:
    assistant = FakeAssistant({"success": True})
    monkeypatch.setattr("speech.pipeline.tempfile.NamedTemporaryFile", lambda **kwargs: open(tmp_path / "sample.wav", "wb"))
    monkeypatch.setattr("speech.pipeline.record_audio", lambda duration_seconds, output_path, device: 5.0)
    monkeypatch.setattr("speech.pipeline.transcribe_audio", lambda path: ("", 0.2))

    result = VoiceAssistant(assistant).run_once()

    assert result["success"] is False
    assert result["error"] == "No speech was detected"
    assert assistant.transcripts == []


def test_voice_pipeline_reports_recording_failure(monkeypatch) -> None:
    assistant = FakeAssistant({"success": True})
    monkeypatch.setattr("speech.pipeline.record_audio", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("microphone unavailable")))

    result = VoiceAssistant(assistant).run_once()

    assert result == {"success": False, "error": "microphone unavailable", "state": "error"}


def test_streaming_voice_executes_only_after_final_transcript(monkeypatch) -> None:
    assistant = FakeAssistant({"success": True, "message": "Opened Excel"})
    observed: list[str] = []

    def fake_stream(**kwargs):
        kwargs["on_partial"]("open")
        observed.append("before-final")
        kwargs["on_partial"]("open Excel")
        return "open Excel", 0.4

    monkeypatch.setattr("speech.pipeline.transcribe_stream", fake_stream)
    result = VoiceAssistant(assistant).run_streaming_once()

    assert result["success"] is True
    assert result["transcript"] == "open Excel"
    assert result["partials"] == ["open", "open Excel"]
    assert observed == ["before-final"]
    assert assistant.transcripts == ["open Excel"]


def test_streaming_voice_reports_empty_final_transcript(monkeypatch) -> None:
    assistant = FakeAssistant({"success": True})
    monkeypatch.setattr("speech.pipeline.transcribe_stream", lambda **kwargs: ("", 0.1))

    result = VoiceAssistant(assistant).run_streaming_once()

    assert result["success"] is False
    assert result["error"] == "No speech was detected"
    assert assistant.transcripts == []


def test_streaming_voice_reports_valid_state_order(monkeypatch) -> None:
    assistant = FakeAssistant({"success": True})
    states: list[str] = []
    monkeypatch.setattr("speech.pipeline.transcribe_stream", lambda **kwargs: ("open Excel", 0.1))

    result = VoiceAssistant(assistant).run_streaming_once(on_state=states.append)

    assert result["success"] is True
    assert states == ["listening", "transcribing", "thinking"]
