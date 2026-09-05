# Catch

Catch is a local-first Windows voice assistant. The CLI prototype is being built in small, verified stages before the graphical interface.

## Current milestone

Project bootstrap, environment diagnostics, CLI Whisper recording, benchmarking, and read-only file search are implemented.

Run:

```powershell
a:/code/CatchAI/.venv/Scripts/python.exe diagnostics.py
a:/code/CatchAI/.venv/Scripts/python.exe test_whisper.py
a:/code/CatchAI/.venv/Scripts/python.exe benchmark_whisper.py
```

The diagnostics check Python, Ollama and the configured model, faster-whisper, microphones, Windows, and Desktop/Documents/Downloads. The Whisper test records five seconds, saves a temporary WAV file, transcribes it locally, and reports latency and real-time factor. The first run may download the configured model.

Use `--device ID` to select a microphone from the diagnostic list, or `--model tiny.en`, `--model base.en`, or `--model small.en` to override configuration for a test.

The benchmark records once and evaluates `tiny.en`, `base.en`, and `small.en` against the same audio. The first benchmark may download any models that are not already cached.

Filename search is available through `tools.files.search_files`. It searches configured Desktop, Documents, and Downloads roots recursively without opening file contents or modifying the filesystem. A harmless test document is stored in `Documents/Catch_Test/catch_test_document.txt`.

Controlled application operations are available through `tools.windows.open_application` and `tools.windows.close_application`. Discovery is cached and combines configured executables, Windows `Get-StartApps`, and Start Menu shortcuts; packaged apps use their validated AppsFolder identifier when no executable path is available. The resolver uses generated aliases, categories, token/fuzzy ranking, and safe ambiguity results rather than trusting arbitrary executable paths, shell commands, or process IDs. Confirmed speech corrections are stored in `%LOCALAPPDATA%\\Catch\\application_aliases.json`.

Google search is available through `tools.web.google_search`. It URL-encodes the query and opens the result in the default browser. It does not automate or read the browser.

Media tools are available through `tools.media`, with Spotify isolated in `tools.spotify`. Spotify catalog search uses the installed SpotAPI provider without an API key; authenticated playback is experimental and requires `SPOTIFY_TEST_EMAIL` and `SPOTIFY_TEST_PASSWORD` from the environment or `%LOCALAPPDATA%\\Catch\\secrets.json`. SpotAPI may require CAPTCHA solving or an active player session, so Catch reports a clean failure when playback cannot be controlled. YouTube uses Data API v3 with `YOUTUBE_API_KEY`.

YouTube live smoke test:

```powershell
$env:YOUTUBE_API_KEY = "your-new-key"
a:/code/CatchAI/.venv/Scripts/python.exe test_youtube.py "Python decorators"
```

This calls the official `search.list` endpoint and opens the first returned video. It reports a clear setup error when the environment variable is missing.

Set secrets only in the user environment before starting Catch, or store them in `%LOCALAPPDATA%\\Catch\\secrets.json`. Never commit that file or print credentials in logs.

Current weather is available through `get_weather`. Catch reads `OPENWEATHER_API_KEY` from the environment or `%LOCALAPPDATA%\\Catch\\secrets.json`, calls OpenWeather's current-weather endpoint in metric units, and uses the requested city when one is spoken. With no city, it uses saved coordinates when present and otherwise the editable home city/country in `%LOCALAPPDATA%\\Catch\\user_profile\\profile.json`. Catch creates `profile.json`, `preferences.json`, and `history.json` there without overwriting existing files. Edit those files directly to change personal information; credentials remain in `secrets.json` and are never included in profile responses.

Global commands such as `pause`, `resume`, `next song`, `previous song`, `volume up`, `mute`, and `set volume to 50` use Windows media/audio controls and do not assume Spotify is active. Windows Search, lock, sleep, Settings, Wi-Fi, Bluetooth, and battery-saver intents are routed through fixed allowlisted capabilities; the LLM never receives shell execution access.

The optional local profile is `%LOCALAPPDATA%\\Catch\\profile.json`, for example `{"preferred_name": "Alex"}`. `What's my name?` is answered locally without Ollama.

The validated registry in `tools.registry` exposes `search_files`, `open_file`, `open_folder`, `open_application`, `close_application`, `google_search`, `get_time`, and `get_date`. Each call is checked against a Pydantic argument schema before the Python handler runs; unknown tools and malformed arguments are rejected.

Simple commands such as `open Excel`, `launch Chrome`, `open Spotify`, `open Discord`, `open Calculator`, `open Downloads`, `open Pictures`, and `close Chrome` are classified by `brain.fast_router` and go directly to the safe Python tool without Ollama. `open a browser` produces a numbered choice instead of launching an arbitrary browser; a follow-up such as `the second one` is resolved from short-lived assistant context. Inventory questions such as `what browsers do I have` also use the cached machine inventory. Complex requests continue through Qwen.

Ten dry-run `open Excel` dispatches averaged `0.019 ms` with a `0.007 ms` median and zero Ollama calls. The previous observed full simple-command latency was approximately 7-10 seconds, dominated by Ollama; a real voice run should still be measured with the timing breakdown printed by `--listen`.

The local Ollama adapter is in `brain.llm`, with the Catch system prompt in `brain.prompts`. `brain.router.route_response` validates the model's JSON and sends only registered tool calls to the registry.

The text pipeline in `brain.assistant` performs the complete planning, validation, tool execution, and final-response loop. Try a harmless conversation with:

```powershell
a:/code/CatchAI/.venv/Scripts/python.exe main.py --text "Hello Catch"
a:/code/CatchAI/.venv/Scripts/python.exe main.py --voice
```

Voice mode records one command for five seconds, transcribes it with the configured Whisper model, and sends the transcript through the same validated text pipeline. Use `--duration SECONDS` or `--device ID` when needed. Continuous wake-word mode is available through `--listen` and tray mode.

Wake-word and tray commands use streaming capture when `speech.streaming` is enabled in `config.yaml`. Catch re-decodes the accumulated Moonshine audio every `partial_interval_seconds`, displays partials such as `open` and `open Excel`, finalizes after `silence_duration_seconds`, and executes the validated tool only once for the final transcript. This is rolling partial recognition rather than native token-level decoding because the configured Moonshine recognizer is offline.

The wake-word adapter is in `wakeword.detector` and uses the official openWakeWord `hey_jarvis` model without invoking Whisper on idle audio. The model is stored by the installed package in `.venv/Lib/site-packages/openwakeword/resources/models/hey_jarvis_v0.1.onnx` after `WakeWordDetector.from_config()` downloads it through the package's official loader. The configured test phrase is `Hey Jarvis`; `phrase_detected()` provides isolated phrase-test coverage.

`wakeword.listener.WakeWordListener` provides bounded microphone streaming in 80 ms frames with a finite timeout and a small queue. It sends frames only to the wake detector; Whisper remains activated only after a future wake event.

The lifecycle state machine is in `core.state` and covers `IDLE`, `WAITING_FOR_WAKE`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `EXECUTING`, `RESPONDING`, and `ERROR`. Invalid transitions are rejected so future background listening and UI layers share one predictable state model.

Continuous listening is available with:

```powershell
a:/code/CatchAI/.venv/Scripts/python.exe main.py --listen
```

It loads the official pretrained `hey_jarvis` model as `hey_jarvis_v0.1.onnx` from `.venv/Lib/site-packages/openwakeword/resources/models/`, using threshold `0.5`. The listener processes 1,280-sample mono frames (80 ms at 16 kHz) and does not run Whisper until wake detection. Press Ctrl+C to stop it.

Press Ctrl+C once to stop CLI `--listen` cleanly. For tray mode, use right-click on the Catch tray icon and select `Exit`; this stops the worker before closing the application.

The PySide6 tray shell is available with `a:/code/CatchAI/.venv/Scripts/python.exe main.py --tray`. It provides Catch identity, state display, Settings, About, and Exit. The compact floating control starts at the bottom-right, can be dragged with left-click, hidden by double-click or right-click, and restored from the tray menu. Its transparent text bar shows `Waiting for "Hey Jarvis"`, the recognized user command, Catch's response, and clear status/error messages, without exposing internal logs or result dictionaries. The wake backend runs in a separate Qt worker thread, and Exit requests the worker to stop before closing Qt. Backend logic remains outside the Qt widgets.

Optional startup is available from the tray menu as `Start Catch with Windows`. It creates a per-user `Catch.cmd` entry in the Windows Startup folder and launches only the Catch tray mode through the environment's `pythonw.exe`. Uncheck the menu item to remove it.

Packaged and development launches write diagnostic logs to `%LOCALAPPDATA%\Catch\logs\catch.log`, which is useful when the windowless packaged application encounters a startup or dependency error.

After recording ends, the floating animation changes to `catch_thinking.webm` during transcription and Ollama/tool processing. With `wakeword.keep_awake: true`, Catch accepts follow-up commands without repeating `Hey Jarvis` until the configured `keep_awake_timeout_seconds` expires or silence ends the session, then returns to wake listening.

## Configuration

Edit `config.yaml` to change the Ollama host/model, Whisper model, and file search roots. User folders are resolved through Windows Known Folders, including localized or redirected folders.

Optional YouTube and Spotify credentials are read first from process environment variables (`YOUTUBE_API_KEY` and `SPOTIFY_ACCESS_TOKEN`). For tray/Desktop launches, persist them locally instead of setting them only in a PowerShell session by creating `%LOCALAPPDATA%\\Catch\\secrets.json`:

```json
{
  "YOUTUBE_API_KEY": "your-key"
}
```

Catch never writes these values to logs. A command such as `open example.com`, `visit wikipedia.org`, or `open https://example.tech/path` opens the validated URL directly in the default browser; it does not perform a Google search.

Ollama generation is configured with `think: false` and `max_tokens: 128` for responsive structured JSON on CPU. Increase these only when a different local model requires more output.

Run `a:/code/CatchAI/.venv/Scripts/python.exe benchmark_runtime.py` to measure wake-model load time, idle listener CPU/RAM, and configured-root file-search latency on this machine. The benchmark listens silently for five seconds by default and does not invoke Whisper or Ollama.

Run `a:/code/CatchAI/.venv/Scripts/python.exe benchmark_latency.py --runs 10` to measure repeated deterministic command routing. It uses a dry-run application handler, so it does not launch Excel ten times and fails if Ollama is called.

## Planned architecture

Microphone -> local speech-to-text -> Ollama -> validated Python tool -> result

The LLM will select only registered, Pydantic-validated tools. It will never execute arbitrary shell commands.
