"""Local Moonshine transcription for CatchAI."""

from __future__ import annotations

import time
from functools import lru_cache
import os
import sys
from pathlib import Path
from urllib.request import urlopen
import tarfile
import tempfile

import sherpa_onnx
import soundfile as sf

from config import PROJECT_ROOT, load_config


MOONSHINE_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "asr-models/sherpa-onnx-moonshine-tiny-en-int8.tar.bz2"
)


@lru_cache(maxsize=4)
def _create_recognizer(
    model_dir: str,
    num_threads: int,
) -> sherpa_onnx.OfflineRecognizer:
    """Load and cache a Moonshine recognizer."""

    model_path = Path(model_dir)

    if not model_path.is_dir():
        raise FileNotFoundError(
            f"Moonshine model directory does not exist: {model_path}"
        )

    required_files = [
        "preprocess.onnx",
        "encode.int8.onnx",
        "uncached_decode.int8.onnx",
        "cached_decode.int8.onnx",
        "tokens.txt",
    ]

    missing_files = [
        filename
        for filename in required_files
        if not (model_path / filename).is_file()
    ]

    if missing_files:
        raise FileNotFoundError(
            "Moonshine model is missing required files:\n"
            + "\n".join(f"  - {filename}" for filename in missing_files)
        )

    return sherpa_onnx.OfflineRecognizer.from_moonshine(
        preprocessor=str(model_path / "preprocess.onnx"),
        encoder=str(model_path / "encode.int8.onnx"),
        uncached_decoder=str(model_path / "uncached_decode.int8.onnx"),
        cached_decoder=str(model_path / "cached_decode.int8.onnx"),
        tokens=str(model_path / "tokens.txt"),
        num_threads=num_threads,
        provider="cpu",
    )


def _resolve_model_path(model_name: str) -> Path:
    """
    Resolve the Moonshine model directory.

    Example:
        moonshine-tiny-en-int8
        -> models/moonshine-tiny-en-int8
    """

    model_path = Path(model_name)

    # If config.yaml already contains a full/relative path,
    # use it directly.
    if model_path.is_dir():
        return model_path

    # Resolve configured model names relative to the application, not cwd.
    return _model_root() / model_name


def _model_root() -> Path:
    """Return a writable model root for development and frozen builds."""

    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Catch" / "models"
    return PROJECT_ROOT / "models"


def download_moonshine_model(
    destination: Path | None = None,
    url: str = MOONSHINE_MODEL_URL,
) -> Path:
    """Download the official Moonshine model archive into Catch's models folder."""

    target_root = destination or _model_root()
    target_root.mkdir(parents=True, exist_ok=True)
    target_dir = target_root / "moonshine-tiny-en-int8"
    if target_dir.is_dir():
        return target_dir

    with tempfile.NamedTemporaryFile(
        prefix="catch_moonshine_",
        suffix=".tar.bz2",
        delete=False,
    ) as archive_file:
        archive_path = Path(archive_file.name)

    try:
        with urlopen(url, timeout=120) as response, archive_path.open("wb") as output:
            output.write(response.read())
        with tarfile.open(archive_path, mode="r:bz2") as archive:
            archive.extractall(target_root, filter="data")
    except (OSError, tarfile.TarError) as error:
        raise RuntimeError(f"Could not download Moonshine model: {error}") from error
    finally:
        archive_path.unlink(missing_ok=True)

    official_dir = target_root / "sherpa-onnx-moonshine-tiny-en-int8"
    if official_dir.is_dir() and not target_dir.exists():
        official_dir.rename(target_dir)

    if not target_dir.is_dir():
        raise RuntimeError(
            f"Moonshine download completed but expected model directory is missing: {target_dir}"
        )
    return target_dir


def transcribe_audio(
    audio_path: Path,
    model_name: str | None = None,
) -> tuple[str, float]:
    """
    Transcribe an audio file using Moonshine.

    Args:
        audio_path:
            Path to the WAV audio file.

        model_name:
            Optional Moonshine model name/path.
            If omitted, the value from config.yaml is used.

    Returns:
        A tuple containing:
            - transcription text
            - transcription time in seconds
    """

    if not audio_path.is_file():
        raise FileNotFoundError(
            f"Audio file does not exist: {audio_path}"
        )

    config = load_config()
    speech_config = config.get("speech", {})

    selected_model = model_name or str(
        speech_config.get(
            "model",
            "moonshine-tiny-en-int8",
        )
    )

    num_threads = int(
        speech_config.get("num_threads", 2)
    )

    model_path = _resolve_model_path(selected_model)
    if not model_path.is_dir() and selected_model == "moonshine-tiny-en-int8":
        model_path = download_moonshine_model()

    recognizer = _create_recognizer(
        str(model_path),
        num_threads,
    )

    started = time.perf_counter()

    # Load audio as normalized float32.
    #
    # always_2d=True guarantees a 2-D array:
    #   (samples, channels)
    #
    # Moonshine expects a 1-D waveform, so we take
    # the first channel.
    audio, sample_rate = sf.read(
        str(audio_path),
        dtype="float32",
        always_2d=True,
    )

    audio = audio[:, 0]

    if audio.size == 0:
        raise ValueError(
            f"Audio file is empty: {audio_path}"
        )

    # Create a new stream for this utterance.
    stream = recognizer.create_stream()

    # Feed the audio to Moonshine.
    #
    # sherpa-onnx handles resampling when the input
    # sample rate differs from what the model expects.
    stream.accept_waveform(
        sample_rate,
        audio,
    )

    # Run Moonshine inference.
    recognizer.decode_stream(stream)

    text = stream.result.text.strip()

    elapsed = time.perf_counter() - started

    return text, elapsed