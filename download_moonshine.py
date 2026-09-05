"""Download Catch's configured Moonshine model from the official sherpa-onnx release."""

from __future__ import annotations

from speech.whisper import download_moonshine_model


def main() -> int:
    model_path = download_moonshine_model()
    print(f"Moonshine model ready: {model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
