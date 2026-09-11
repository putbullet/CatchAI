# CatchAI Changelog

## Latest Release - Full Hardening Pass: Media, Factual Retrieval, Spotify & Application Control

### 1. YouTube & Interactive Selection Hardening
- **Number Words & Natural Language Selection**: Support for word numbers (`one`, `two`, `three`, `four`, `five`), ordinals (`first` through `fifth`, `last`), and conversational prefixes (`option five`, `number 5`, `the fifth one`, `play five`, `watch 2`) across all interactive selection prompts (YouTube, Spotify, Drive selection, and Application disambiguation).
- **Interaction State Priority**: Active pending selections and confirmation dialogs now strictly take precedence over standard intent routing and exit keywords (e.g. saying `"stop"` or `"cancel"` while choices are presented cancels playback selection instead of terminating the Catch process).
- **Broadened YouTube URL Handling**: Playback validation now supports `https://www.youtube.com/watch?`, `https://youtube.com/watch?`, and short-form `https://youtu.be/` links.
- **Speech Error Suppression**: Suppressed false `"No speech was detected"` error banners in the background loop so silence or thinking pauses during selection mode do not disrupt the UI.

### 2. Factual Queries & Information Retrieval ("How tall is LeBron James?")
- **Fast Factual Attribute Routing**: Expanded fast-path pattern matching to capture attribute queries (`how tall is <subject>`, `how old is <subject>`, `where was <subject> born`, `when was <subject> built`, `where is <subject>`).
- **Targeted Wikipedia Attribute Extraction**: Upgraded `wikipedia_summary` with automated attribute sentence matching and OpenSearch fallback, answering queries such as *"How tall is LeBron James?"* directly in under 1 second without hallucination.
- **Native ClarifyResponse Support**: Catch assistant now natively processes `ClarifyResponse` models from the local LLM planner, presenting clarification questions smoothly to the user instead of triggering silent failures or unexpected errors.
- **System Prompt Refinement**: Removed ambiguous disambiguation examples that caused the sub-1B Ollama model to hallucinate city-based clarifying questions for well-known people.

### 3. Spotify Search & Playback Hardening
- **Query Normalization**: Implemented `normalize_spotify_query` to cleanly strip `"on spotify"`, `"play"`, `"the song"` and parse `(title, artist)` tuples before invoking search.
- **Multi-Signal Candidate Ranking**: Added penalties against karaoke, tribute, instrumental, cover, and parody tracks unless explicitly requested by the user, ensuring authentic original releases are prioritized for playback.
- **Desktop Client Fallback**: Implemented automatic fallback to the installed Windows Spotify client (`_open_spotify_track` via `os.startfile(uri)`) when headless testing credentials (`SPOTIFY_TEST_EMAIL`, `SPOTIFY_TEST_PASSWORD`) are not set or when SpotAPI experiences session errors.

### 4. Application Control & Safe "Close All"
- **Safe "Close All" Command**: Added deterministic recognition for `"close all apps"`, `"close all applications"`, `"close all windows"`, and `"kill all apps"`.
- **Conversational Confirmation**: Closing all applications requires explicit confirmation (*"Are you sure you want to close all opened applications? Say yes to confirm or no to cancel."*).
- **Process Protection**: Strict process protection list (`_PROTECTED_PROCESS_NAMES` and `_DENIED_PROCESS_NAMES`) guarantees system processes (`explorer.exe`, `csrss.exe`, etc.) and CatchAI processes (`python.exe`, `catchai.exe`, `ollama.exe`, etc.) can never be terminated.
- **Session Application Tracking**: Added `record_launched_application`, `get_launched_applications`, and `clear_launched_applications` to safely track applications started during the session.

### 5. Lifecycle & Stability Improvements
- Startup health checks and graceful handling of missing models or dependencies.
- Interactive multi-drive disk cleanup with dry-run scan reviews and confirmation before deletion.
- Floating overlay and tray synchronization reliability.
- **148 automated tests** passing with zero regressions.
