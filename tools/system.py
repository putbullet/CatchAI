"""Controlled Windows system and global media capabilities."""

from __future__ import annotations

import ctypes
import os
import subprocess
from urllib.parse import quote
from typing import Any

from config import load_config


_VK_MEDIA = {
    "play": 0xB3,
    "pause": 0xB3,
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "stop": 0xB2,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
}


def _media_key(action: str) -> dict[str, Any]:
    if os.name != "nt":
        return {"success": False, "error": "Global media controls require Windows"}
    key = _VK_MEDIA[action]
    try:
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key, 0, 2, 0)
    except OSError as error:
        return {"success": False, "error": str(error)}
    return {"success": True, "action": action, "message": f"Media {action.replace('_', ' ')}"}


def media_play() -> dict[str, Any]:
    return _media_key("play")


def media_pause() -> dict[str, Any]:
    return _media_key("pause")


def media_play_pause() -> dict[str, Any]:
    return _media_key("play_pause")


def media_next() -> dict[str, Any]:
    return _media_key("next")


def media_previous() -> dict[str, Any]:
    return _media_key("previous")


def media_stop() -> dict[str, Any]:
    return _media_key("stop")


def media_volume_up() -> dict[str, Any]:
    return _media_key("volume_up")


def media_volume_down() -> dict[str, Any]:
    return _media_key("volume_down")


def media_mute() -> dict[str, Any]:
    return _media_key("mute")


def _endpoint_volume() -> Any:
    from pycaw.pycaw import AudioUtilities

    device = AudioUtilities.GetSpeakers()
    return device.EndpointVolume


def media_set_volume(percent: float) -> dict[str, Any]:
    if not 0 <= percent <= 100:
        return {"success": False, "error": "Volume must be between 0 and 100"}
    if os.name != "nt":
        return {"success": False, "error": "Volume control requires Windows"}
    try:
        _endpoint_volume().SetMasterVolumeLevelScalar(percent / 100, None)
    except (OSError, RuntimeError, ImportError) as error:
        return {"success": False, "error": f"Could not set volume: {error}"}
    return {"success": True, "percent": percent, "message": f"Volume set to {percent:g}%"}


def media_adjust_volume(delta: float) -> dict[str, Any]:
    if os.name != "nt":
        return {"success": False, "error": "Volume control requires Windows"}
    try:
        endpoint = _endpoint_volume()
        current = float(endpoint.GetMasterVolumeLevelScalar()) * 100
        target = max(0.0, min(100.0, current + delta))
        endpoint.SetMasterVolumeLevelScalar(target / 100, None)
    except (OSError, RuntimeError, ImportError) as error:
        return {"success": False, "error": f"Could not adjust volume: {error}"}
    return {"success": True, "percent": target, "message": f"Volume set to {target:g}%"}


def _session_volume(application: str) -> Any:
    from pycaw.pycaw import AudioUtilities

    target = application.casefold().removesuffix(".exe").removesuffix(" application").removesuffix(" app").strip()
    for session in AudioUtilities.GetAllSessions():
        process = session.Process
        if process is not None and process.name().casefold().removesuffix(".exe") == target:
            return session.SimpleAudioVolume
    return None


def volume_control(
    action: str,
    application: str = "",
    percent: float | None = None,
    delta: float | None = None,
) -> dict[str, Any]:
    """Read or change master volume, or a named application's audio session."""
    if action not in {"up", "down", "set", "mute", "unmute", "get"}:
        return {"success": False, "error": "Unsupported volume action"}
    if os.name != "nt":
        return {"success": False, "error": "Volume control requires Windows"}
    try:
        target = _session_volume(application) if application.strip() else _endpoint_volume()
        if target is None:
            return {"success": False, "error": f"No active audio session found for {application}"}
        if application.strip():
            current = float(target.GetMasterVolume()) * 100
            setter = target.SetMasterVolume
            get_mute = target.GetMute
            set_mute = target.SetMute
        else:
            current = float(target.GetMasterVolumeLevelScalar()) * 100
            setter = lambda value: target.SetMasterVolumeLevelScalar(value / 100, None)
            get_mute = target.GetMute
            set_mute = lambda value: target.SetMute(value, None)
        if action == "get":
            return {"success": True, "percent": current, "muted": bool(get_mute()), "message": f"{application or 'System'} volume is {current:g}%"}
        if action == "mute":
            set_mute(True)
        elif action == "unmute":
            set_mute(False)
        else:
            if action == "set":
                target_percent = percent
            else:
                configured_step = float(load_config().get("volume", {}).get("adjustment_step_percent", 10))
                target_percent = current + (delta if delta is not None else configured_step) * (1 if action == "up" else -1)
            if target_percent is None or not 0 <= target_percent <= 100:
                return {"success": False, "error": "Volume must be between 0 and 100"}
            setter(target_percent)
            current = target_percent
        label = application or "system"
        return {"success": True, "percent": current, "application": application, "message": f"{label.title()} volume {'muted' if action == 'mute' else 'unmuted' if action == 'unmute' else f'set to {current:g}%'}"}
    except (OSError, RuntimeError, ImportError, AttributeError) as error:
        return {"success": False, "error": f"Could not control volume: {error}"}


def get_resource_usage() -> dict[str, Any]:
    """Return current CPU and memory usage."""
    try:
        import psutil

        memory = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
    except (ImportError, OSError, RuntimeError) as error:
        return {"success": False, "error": f"Could not read resource usage: {error}"}
    return {
        "success": True,
        "cpu_percent": cpu,
        "memory_percent": memory.percent,
        "memory_used_gb": memory.used / 1024**3,
        "memory_total_gb": memory.total / 1024**3,
        "message": f"CPU is at {cpu:.0f}% and RAM is at {memory.percent:.0f}% ({memory.used / 1024**3:.1f} of {memory.total / 1024**3:.1f} GB).",
    }


def set_brightness(percent: float) -> dict[str, Any]:
    if not 0 <= percent <= 100:
        return {"success": False, "error": "Brightness must be between 0 and 100"}
    command = (
        "$brightness = [byte]([math]::Round(" + str(percent) + ")); "
        "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
        "Invoke-CimMethod -Name WmiSetBrightness -Arguments @{Brightness=$brightness; Timeout=1}"
    )
    return _run_fixed_powershell(command, f"Brightness set to {percent:g}%")


def adjust_brightness(delta: float) -> dict[str, Any]:
    return {"success": False, "error": "Relative brightness control requires a readable monitor level"}


def set_radio(radio: str, enabled: bool) -> dict[str, Any]:
    commands = {
        "wifi": "Get-NetAdapter -Name 'Wi-Fi' -ErrorAction Stop | "
        + ("Enable-NetAdapter -Confirm:$false" if enabled else "Disable-NetAdapter -Confirm:$false"),
        "bluetooth": "Get-PnpDevice -Class Bluetooth -ErrorAction Stop | "
        + ("Enable-PnpDevice -Confirm:$false" if enabled else "Disable-PnpDevice -Confirm:$false"),
    }
    command = commands.get(radio)
    if command is None:
        return {"success": False, "error": "Unsupported radio"}
    return _run_fixed_powershell(command, f"{radio.title()} {'enabled' if enabled else 'disabled'}")


def set_battery_saver(enabled: bool) -> dict[str, Any]:
    return {
        "success": False,
        "enabled": enabled,
        "error": "Battery saver control is not available through a stable built-in Windows API",
    }


def lock_computer() -> dict[str, Any]:
    if os.name != "nt":
        return {"success": False, "error": "Locking requires Windows"}
    try:
        locked = bool(ctypes.windll.user32.LockWorkStation())
    except OSError as error:
        return {"success": False, "error": str(error)}
    return {"success": locked, "message": "Computer locked" if locked else "Could not lock computer"}


def power_action(action: str, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        return {"success": False, "confirmation_required": True, "action": action}
    executable = {"restart": "/r", "shutdown": "/s"}.get(action)
    if executable is None:
        return {"success": False, "error": "Unsupported power action"}
    try:
        subprocess.run(["shutdown.exe", executable, "/t", "0"], check=True, capture_output=True)
    except (OSError, subprocess.SubprocessError) as error:
        return {"success": False, "error": str(error)}
    return {"success": True, "action": action}


def sleep_computer() -> dict[str, Any]:
    if os.name != "nt":
        return {"success": False, "error": "Sleep requires Windows"}
    try:
        ctypes.windll.powrprof.SetSuspendState(False, True, False)
    except OSError as error:
        return {"success": False, "error": str(error)}
    return {"success": True, "message": "Computer is sleeping"}


def open_settings(page: str = "") -> dict[str, Any]:
    allowed = {
        "": "ms-settings:",
        "bluetooth": "ms-settings:bluetooth",
        "wifi": "ms-settings:network-wifi",
        "sound": "ms-settings:sound",
        "display": "ms-settings:display",
        "battery": "ms-settings:batterysaver",
    }
    uri = allowed.get(page.casefold())
    if uri is None:
        return {"success": False, "error": "Unsupported Settings page"}
    try:
        os.startfile(uri)
    except OSError as error:
        return {"success": False, "error": str(error)}
    return {"success": True, "page": page or "home"}


def _run_fixed_powershell(command: str, message: str) -> dict[str, Any]:
    if os.name != "nt":
        return {"success": False, "error": "This operation requires Windows"}
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"success": False, "error": str(error)}
    return {"success": True, "message": message}


def windows_search(query: str) -> dict[str, Any]:
    """Open Windows Search with a URL-encoded query."""
    cleaned = query.strip()
    if not cleaned:
        return {"success": False, "error": "Windows search query cannot be empty"}
    try:
        os.startfile(f"search-ms:query={quote(cleaned)}")
    except OSError as error:
        return {"success": False, "error": str(error)}
    return {"success": True, "query": cleaned, "message": f"Searching Windows for {cleaned}"}
