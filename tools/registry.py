"""Validated tool registry for Catch's untrusted LLM planner."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tools.file_actions import open_file
from tools.cleanup import delete_temp_files
from tools.folders import open_folder
from tools.files import search_files
from tools.media import spotify_search, youtube_search
from tools.spotify import spotify_play
from tools.system import (
    adjust_brightness,
    lock_computer,
    media_adjust_volume,
    media_mute,
    media_next,
    media_pause,
    media_play,
    media_play_pause,
    media_previous,
    media_set_volume,
    media_stop,
    media_volume_down,
    media_volume_up,
    open_settings,
    power_action,
    set_battery_saver,
    set_brightness,
    set_radio,
    sleep_computer,
    windows_search,
    get_resource_usage,
    volume_control,
)
from tools.images import show_animal_image
from tools.web import google_search, open_url
from tools.weather import get_weather
from tools.windows import close_all_applications, close_application, open_application


class PermissionLevel(StrEnum):
    """Risk classification for registered tools."""

    READ_ONLY = "read_only"
    SAFE_ACTION = "safe_action"
    SENSITIVE_ACTION = "sensitive_action"
    DESTRUCTIVE_ACTION = "destructive_action"


class SearchFilesArgs(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1)


class OpenFileArgs(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    path: str = Field(min_length=1)


class ApplicationArgs(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    app_name: str = Field(min_length=1)


class GoogleSearchArgs(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1)


class OpenUrlArgs(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    url: str = Field(min_length=3)


class OpenFolderArgs(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    folder: str = Field(min_length=1)


class MediaSearchArgs(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1)


class WeatherArgs(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    location: str = ""


class PercentArgs(BaseModel):
    percent: float = Field(ge=0, le=100)


class DeltaArgs(BaseModel):
    delta: float = Field(ge=-100, le=100)


class RadioArgs(BaseModel):
    radio: str = Field(pattern=r"^(wifi|bluetooth)$")
    enabled: bool


class EnabledArgs(BaseModel):
    enabled: bool


class PowerArgs(BaseModel):
    action: str = Field(pattern=r"^(restart|shutdown)$")
    confirm: bool = False


class SettingsArgs(BaseModel):
    page: str = ""


class VolumeArgs(BaseModel):
    action: str
    application: str = ""
    percent: float | None = None
    delta: float | None = None


class CleanupArgs(BaseModel):
    items: list[dict[str, Any]]


class AnimalArgs(BaseModel):
    animal: str


class CloseAllArgs(BaseModel):
    confirm: bool = False


class NoArgs(BaseModel):
    """Argument schema for tools without parameters."""


class ToolDefinition:
    """Metadata and validated handler for one Catch tool."""

    def __init__(
        self,
        name: str,
        description: str,
        args_model: type[BaseModel],
        handler: Callable[..., Any],
        permission: PermissionLevel,
    ) -> None:
        self.name = name
        self.description = description
        self.args_model = args_model
        self.handler = handler
        self.permission = permission


class ToolRegistry:
    """Registry that validates tool names and arguments before execution."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        """Register a tool definition, rejecting duplicate names."""
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        if not issubclass(definition.args_model, BaseModel):
            raise TypeError("Tool argument schema must inherit from pydantic.BaseModel")
        self._tools[definition.name] = definition

    def names(self) -> list[str]:
        """Return registered names in stable order."""
        return sorted(self._tools)

    def definitions(self) -> list[ToolDefinition]:
        """Return registered definitions in stable order."""
        return [self._tools[name] for name in self.names()]

    def execute(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        """Validate and execute one named tool, never executing unknown input."""
        definition = self._tools.get(name)
        if definition is None:
            return {"success": False, "error": f"Unknown tool: {name}"}
        try:
            validated_arguments = definition.args_model.model_validate(arguments or {})
        except ValidationError as error:
            return {"success": False, "error": "Invalid tool arguments", "details": error.errors()}
        try:
            result = definition.handler(**validated_arguments.model_dump())
        except Exception as error:  # Tool failures must not terminate the assistant loop.
            return {"success": False, "error": str(error)}
        if isinstance(result, dict):
            return result
        return {"success": True, "result": result}


def _get_time() -> dict[str, Any]:
    return {"success": True, "time": datetime.now().strftime("%H:%M:%S")}


def _get_date() -> dict[str, Any]:
    return {"success": True, "date": date.today().isoformat()}


def build_default_registry() -> ToolRegistry:
    """Build the initial safe tool registry."""
    registry = ToolRegistry()
    registry.register(ToolDefinition("search_files", "Search configured folders by filename", SearchFilesArgs, search_files, PermissionLevel.READ_ONLY))
    registry.register(ToolDefinition("open_file", "Open a validated file", OpenFileArgs, open_file, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("open_folder", "Open an allowlisted Windows folder", OpenFolderArgs, open_folder, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("open_application", "Open a discovered application", ApplicationArgs, open_application, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("close_application", "Close a discovered application", ApplicationArgs, close_application, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("close_all_applications", "Close all opened applications after confirmation", CloseAllArgs, close_all_applications, PermissionLevel.DESTRUCTIVE_ACTION))
    registry.register(ToolDefinition("google_search", "Open a Google search in the default browser", GoogleSearchArgs, google_search, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("open_url", "Open a validated website in the default browser", OpenUrlArgs, open_url, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("get_weather", "Get current weather using the profile location or requested city", WeatherArgs, get_weather, PermissionLevel.READ_ONLY))
    registry.register(ToolDefinition("spotify_search", "Search Spotify tracks using the configured API token", MediaSearchArgs, spotify_search, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("spotify_play", "Resolve and play a Spotify track through SpotAPI", MediaSearchArgs, spotify_play, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("youtube_search", "Search YouTube using Data API v3 and open the first result", MediaSearchArgs, youtube_search, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_play", "Play the active Windows media session", NoArgs, media_play, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_pause", "Pause the active Windows media session", NoArgs, media_pause, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_play_pause", "Toggle the active Windows media session", NoArgs, media_play_pause, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_next", "Skip the active Windows media session", NoArgs, media_next, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_previous", "Go back in the active Windows media session", NoArgs, media_previous, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_stop", "Stop the active Windows media session", NoArgs, media_stop, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_volume_up", "Increase Windows master volume", NoArgs, media_volume_up, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_volume_down", "Decrease Windows master volume", NoArgs, media_volume_down, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_mute", "Mute Windows master volume", NoArgs, media_mute, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_set_volume", "Set Windows master volume percentage", PercentArgs, lambda percent: media_set_volume(percent), PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("media_adjust_volume", "Adjust Windows master volume percentage", DeltaArgs, lambda delta: media_adjust_volume(delta), PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("volume_control", "Read or control system or application volume", VolumeArgs, volume_control, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("get_resource_usage", "Read current CPU and RAM usage", NoArgs, get_resource_usage, PermissionLevel.READ_ONLY))
    registry.register(ToolDefinition("clear_temp_files", "Delete reviewed temporary files after confirmation", CleanupArgs, delete_temp_files, PermissionLevel.DESTRUCTIVE_ACTION))
    registry.register(ToolDefinition("show_animal_image", "Fetch a cat or dog image", AnimalArgs, show_animal_image, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("set_brightness", "Set display brightness percentage", PercentArgs, lambda percent: set_brightness(percent), PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("adjust_brightness", "Adjust display brightness percentage", DeltaArgs, lambda delta: adjust_brightness(delta), PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("set_radio", "Enable or disable Wi-Fi or Bluetooth", RadioArgs, set_radio, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("set_battery_saver", "Enable or disable battery saver", EnabledArgs, set_battery_saver, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("lock_computer", "Lock the Windows computer", NoArgs, lock_computer, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("sleep_computer", "Put the Windows computer to sleep", NoArgs, sleep_computer, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("power_action", "Restart or shut down Windows after confirmation", PowerArgs, power_action, PermissionLevel.DESTRUCTIVE_ACTION))
    registry.register(ToolDefinition("open_settings", "Open an allowlisted Windows Settings page", SettingsArgs, open_settings, PermissionLevel.SAFE_ACTION))
    registry.register(ToolDefinition("windows_search", "Open Windows Search for a query", SearchFilesArgs, windows_search, PermissionLevel.READ_ONLY))
    registry.register(ToolDefinition("get_time", "Return the current local time", NoArgs, _get_time, PermissionLevel.READ_ONLY))
    registry.register(ToolDefinition("get_date", "Return the current local date", NoArgs, _get_date, PermissionLevel.READ_ONLY))
    return registry
