"""Controlled Windows application discovery and process control."""

from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, TypedDict

import psutil

from config import load_config


class ApplicationRecord(TypedDict):
    """A safely discovered application launch record."""

    name: str
    executable: str
    launch_path: str
    category: str
    aliases: list[str]
    app_id: str


_application_cache: dict[str, ApplicationRecord] | None = None
_DENIED_PROCESS_NAMES = {"csrss.exe", "explorer.exe", "lsass.exe", "services.exe", "smss.exe", "system", "wininit.exe", "winlogon.exe"}
_PROTECTED_PROCESS_NAMES = _DENIED_PROCESS_NAMES | {
    "python.exe", "pythonw.exe", "catchai.exe", "ollama.exe", "ollama_app.exe",
    "svchost.exe", "dwm.exe", "ctfmon.exe", "sihost.exe", "taskhostw.exe",
    "shellexperiencehost.exe", "searchhost.exe", "startmenuexperiencehost.exe",
    "conhost.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
}
_LAUNCHED_APPLICATIONS: list[dict[str, Any]] = []


def record_launched_application(name: str, executable: str, pid: int | None = None) -> None:
    """Track an application launched through Catch in this session."""
    _LAUNCHED_APPLICATIONS.append({
        "name": name,
        "executable": executable.casefold(),
        "pid": pid,
    })


def get_launched_applications() -> list[dict[str, Any]]:
    return list(_LAUNCHED_APPLICATIONS)


def clear_launched_applications() -> None:
    _LAUNCHED_APPLICATIONS.clear()


_APPLICATION_ALIASES = {
    "vscode": "visualstudiocode",
    "vs code": "visual studio code",
    "code": "visual studio code",
    "mozilla": "firefox",
    "edge": "microsoft edge",
}


@dataclass(frozen=True)
class ApplicationMatch:
    """A ranked application candidate returned by the deterministic resolver."""

    application: ApplicationRecord
    score: float
    reason: str


_CATEGORY_TERMS = {
    "browser": ("browser", "brave", "firefox", "edge", "zen", "chrome", "opera"),
    "development": ("code", "studio", "ide", "python", "node", "git", "eclipse", "sublime", "ollama", "visual"),
    "media": ("spotify", "vlc", "media", "obs", "stremio", "photos", "sound"),
    "communication": ("discord", "whatsapp", "outlook", "teams", "phone link"),
    "productivity": ("excel", "word", "powerpoint", "publisher", "access", "onenote", "office", "to do"),
    "system": ("settings", "calculator", "notepad", "paint", "terminal", "explorer", "control panel"),
    "security": ("defender", "burp", "wireshark", "zap", "vpn", "security"),
    "gaming": ("steam", "epic", "roblox", "riot", "counter", "mortal", "osu", "game"),
    "utility": ("cpu-z", "core temp", "recuva", "winrar", "crystal", "afterburner"),
}


def _learned_alias_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Catch"
    root.mkdir(parents=True, exist_ok=True)
    return root / "application_aliases.json"


def _load_learned_aliases() -> dict[str, str]:
    try:
        payload = json.loads(_learned_alias_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def remember_application_alias(alias: str, application_name: str) -> None:
    """Persist a user-confirmed speech correction for future deterministic routing."""
    aliases = _load_learned_aliases()
    aliases[" ".join(alias.casefold().split())] = application_name
    path = _learned_alias_path()
    path.write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_name(value: str) -> str:
    """Normalize an application identity for registry lookup."""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _category_for(name: str) -> str:
    lowered = name.casefold()
    for category, terms in _CATEGORY_TERMS.items():
        if any(term in lowered for term in terms):
            return category
    return "other"


def _aliases_for(name: str, executable: str = "") -> list[str]:
    aliases = {name.casefold()}
    normalized = name.casefold()
    if normalized.endswith(" browser"):
        aliases.add(normalized.removesuffix(" browser"))
    elif _category_for(name) == "browser":
        aliases.add(f"{normalized} browser")
    if normalized.startswith("microsoft "):
        aliases.add(normalized.removeprefix("microsoft "))
    if normalized.startswith("mozilla "):
        aliases.add(normalized.removeprefix("mozilla "))
    if executable:
        aliases.add(Path(executable).stem.casefold())
    return sorted(alias for alias in aliases if alias)


def _add_application(
    registry: dict[str, ApplicationRecord],
    name: str,
    executable: str = "",
    launch_path: str | Path = "",
    app_id: str = "",
) -> None:
    key = _normalize_name(name)
    if not key:
        return
    record = {
        "name": name,
        "executable": executable,
        "launch_path": str(launch_path),
        "category": _category_for(name),
        "aliases": _aliases_for(name, executable),
        "app_id": app_id,
    }
    existing = registry.get(key)
    if existing is None:
        registry[key] = record
        return
    if not existing["executable"] and executable:
        existing["executable"] = executable
    if not existing["launch_path"] and launch_path:
        existing["launch_path"] = str(launch_path)
    if not existing.get("app_id") and app_id:
        existing["app_id"] = app_id
    existing["aliases"] = sorted(set(existing.get("aliases", [])) | set(record["aliases"]))


def _discover_start_apps() -> list[dict[str, str]]:
    """Read Windows' Start Apps inventory without trusting shell input."""
    if os.name != "nt":
        return []
    command = (
        "Get-StartApps | Select-Object Name,AppID | "
        "ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=8,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if not completed.stdout.strip():
        return []
    try:
        payload: Any = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    rows = payload if isinstance(payload, list) else [payload]
    return [
        {"name": str(row.get("Name", "")).strip(), "app_id": str(row.get("AppID", "")).strip()}
        for row in rows
        if isinstance(row, dict) and str(row.get("Name", "")).strip()
    ]


def discover_applications(config: dict | None = None, refresh: bool = False) -> dict[str, ApplicationRecord]:
    """Discover configured apps, PATH executables, and Start Menu shortcuts."""
    global _application_cache
    using_default_config = config is None
    if _application_cache is not None and not refresh and using_default_config:
        return dict(_application_cache)

    config = config or load_config()
    registry: dict[str, ApplicationRecord] = {}
    configured = config.get("applications", {})
    for name, details in configured.items():
        executable = str(details.get("executable", ""))
        resolved = shutil.which(executable)
        if resolved:
            _add_application(registry, str(name), Path(resolved).name, Path(resolved))

    for item in _discover_start_apps():
            _add_application(registry, item["name"], app_id=item["app_id"])

    start_menu_roots = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    for root in start_menu_roots:
        if not root.is_dir():
            continue
        for shortcut in root.rglob("*.lnk"):
            _add_application(registry, shortcut.stem, shortcut.name, shortcut)

    if using_default_config:
        _application_cache = dict(registry)
    return registry


def resolve_application(
    app_name: str,
    category: str | None = None,
    registry: dict[str, ApplicationRecord] | None = None,
) -> list[ApplicationMatch]:
    """Rank installed applications using exact, alias, token, and fuzzy signals."""
    registry = registry if registry is not None else discover_applications()
    target = " ".join(app_name.casefold().split()).strip(" .!?\"")
    category_aliases = {
        "browser": "browser",
        "browsers": "browser",
        "navigateur": "browser",
        "navigators": "browser",
        "media player": "media",
        "media players": "media",
        "development": "development",
        "ide": "development",
    }
    requested_category = category or category_aliases.get(target)
    category_records = list(registry.values())
    category_names = {record["name"].casefold() for record in category_records}
    if requested_category:
        return [
            ApplicationMatch(record, 1.0, f"category:{requested_category}")
            for record in category_records
            if record.get("category", "other") == requested_category
            and not (
                "private browsing" in record["name"].casefold()
                and record["name"].casefold().replace(" private browsing", "") in category_names
            )
        ]

    normalized_target = _normalize_name(target)
    alias_target = _APPLICATION_ALIASES.get(target, target)
    alias_target = _load_learned_aliases().get(target, alias_target)
    normalized_alias_target = _normalize_name(alias_target)
    matches: list[ApplicationMatch] = []
    for record in registry.values():
        names = {record["name"].casefold(), *(alias.casefold() for alias in record.get("aliases", []))}
        normalized_names = {_normalize_name(name) for name in names}
        if alias_target in names or normalized_alias_target in normalized_names or normalized_target in normalized_names:
            matches.append(ApplicationMatch(record, 1.0, "exact-or-alias"))
            continue
        best = max(SequenceMatcher(None, normalized_target, value).ratio() for value in normalized_names)
        target_tokens = set(re.findall(r"[a-z0-9]+", target))
        name_tokens = set(re.findall(r"[a-z0-9]+", record["name"].casefold()))
        overlap = len(target_tokens & name_tokens) / max(1, len(target_tokens))
        score = max(best, best * 0.75 + overlap * 0.25)
        if score >= 0.58:
            reason = "token-and-fuzzy" if overlap else "fuzzy"
            matches.append(ApplicationMatch(record, score, reason))
    return sorted(matches, key=lambda item: (-item.score, item.application["name"].casefold()))


def _find_application(app_name: str) -> ApplicationRecord | None:
    matches = resolve_application(app_name)
    if matches and matches[0].score >= 0.82:
        return matches[0].application
    return None


def _selection_result(app_name: str, matches: list[ApplicationMatch]) -> dict[str, object]:
    result: dict[str, object] = {
        "success": False,
        "application": app_name,
        "selection_required": True,
        "candidates": [
            {"name": match.application["name"], "category": match.application.get("category", "other"), "score": round(match.score, 3)}
            for match in matches
        ],
        "error": "More than one application matched",
    }
    if matches and matches[0].score >= 0.72 and not matches[0].reason.startswith("category:"):
        result["suggestion"] = matches[0].application["name"]
    return result


def open_application(app_name: str) -> dict[str, object]:
    """Launch a known application without accepting arbitrary shell input."""
    matches = resolve_application(app_name)
    if matches and matches[0].reason.startswith("category:"):
        return _selection_result(app_name, matches)
    if len(matches) > 1 and matches[0].score < 0.9 and matches[0].score - matches[1].score < 0.12:
        return _selection_result(app_name, matches[:5])
    application = matches[0].application if matches and matches[0].score >= 0.72 else None
    if application is None:
        return {"success": False, "application": app_name, "error": "Application was not found"}

    launch_path = Path(application["launch_path"])
    try:
        proc = None
        if application.get("app_id"):
            os.startfile(f"shell:AppsFolder\\{application['app_id']}")
        elif launch_path.suffix.casefold() == ".lnk":
            os.startfile(str(launch_path))
        else:
            proc = subprocess.Popen([str(launch_path)], shell=False)
        record_launched_application(
            application["name"],
            application["executable"],
            proc.pid if proc else None,
        )
    except (OSError, PermissionError) as error:
        return {"success": False, "application": application["name"], "error": str(error)}
    return {"success": True, "application": application["name"], "message": f"{application['name']} launched"}


def close_application(app_name: str) -> dict[str, object]:
    """Terminate all matching instances of a known, non-critical application."""
    application = _find_application(app_name)
    if application is None:
        return {"success": False, "application": app_name, "error": "Application was not found"}
    process_name = application["executable"].casefold()
    if process_name in _DENIED_PROCESS_NAMES or process_name in _PROTECTED_PROCESS_NAMES:
        return {"success": False, "application": application["name"], "error": "This system process cannot be closed"}

    matches = []
    for process in psutil.process_iter(["name"]):
        try:
            if (process.info.get("name") or "").casefold() == process_name:
                matches.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not matches:
        return {"success": False, "application": application["name"], "error": "Application is not running"}

    try:
        for process in matches:
            process.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
        return {"success": False, "application": application["name"], "error": str(error)}
    return {"success": True, "application": application["name"], "message": f"{application['name']} closed", "instances": len(matches)}


def close_all_applications(confirm: bool = False) -> dict[str, object]:
    """Safely terminate session-launched or user-opened desktop applications with confirmation."""
    if not confirm:
        return {
            "success": False,
            "confirmation_required": True,
            "message": "Are you sure you want to close all opened applications? Say yes to confirm or no to cancel.",
        }

    current_pid = os.getpid()
    catch_pids = {current_pid}
    try:
        current_process = psutil.Process(current_pid)
        catch_pids.update(p.pid for p in current_process.children(recursive=True))
        parent = current_process.parent()
        if parent:
            catch_pids.add(parent.pid)
    except Exception:
        pass

    closed_names: set[str] = set()
    total_closed = 0

    launched_executables = {app["executable"].casefold() for app in _LAUNCHED_APPLICATIONS if app.get("executable")}
    launched_pids = {app["pid"] for app in _LAUNCHED_APPLICATIONS if app.get("pid")}

    for process in psutil.process_iter(["pid", "name"]):
        try:
            pid = process.info.get("pid")
            name = (process.info.get("name") or "").casefold()
            if not pid or pid in catch_pids:
                continue
            if name in _PROTECTED_PROCESS_NAMES or name in _DENIED_PROCESS_NAMES:
                continue
            should_close = False
            if pid in launched_pids or name in launched_executables:
                should_close = True

            if should_close:
                process.terminate()
                closed_names.add(name)
                total_closed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    clear_launched_applications()

    if total_closed == 0:
        return {"success": True, "message": "No session applications were open to close.", "instances": 0}
    return {
        "success": True,
        "message": f"Closed {total_closed} application instance(s).",
        "closed_apps": sorted(closed_names),
        "instances": total_closed,
    }