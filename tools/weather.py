"""OpenWeather current-conditions tool with profile-based location fallback."""

from __future__ import annotations

from typing import Any

import httpx

from config import get_secret
from core.profile import weather_location


def _format_weather(payload: dict[str, Any], location: str) -> str:
    weather = (payload.get("weather") or [{}])[0]
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    description = str(weather.get("description") or "unknown conditions")
    temperature = main.get("temp")
    feels_like = main.get("feels_like")
    humidity = main.get("humidity")
    wind_speed = wind.get("speed")
    return (
        f"Current weather in {location}: {description}, {temperature}°C "
        f"(feels like {feels_like}°C), humidity {humidity}%, "
        f"wind {wind_speed} m/s."
    )


def get_weather(location: str = "") -> dict[str, Any]:
    """Fetch current weather for an explicit city or the saved profile location."""
    api_key = get_secret("OPENWEATHER_API_KEY")
    if not api_key:
        return {"success": False, "error": "OpenWeather API key is not configured"}

    requested = " ".join(location.split()).strip(" .,!?")
    profile_location = weather_location()
    params: dict[str, str] = {"appid": api_key, "units": "metric", "lang": "en"}
    if requested:
        params["q"] = requested
        display_location = requested
    elif profile_location.get("latitude") is not None:
        params["lat"] = str(profile_location["latitude"])
        params["lon"] = str(profile_location["longitude"])
        display_location = "your current location"
    else:
        city = profile_location.get("city", "")
        country = profile_location.get("country", "")
        if not city:
            return {"success": False, "error": "No weather location is saved in your profile"}
        params["q"] = f"{city},{country}" if country else city
        display_location = f"{city}, {country}" if country else city

    try:
        response = httpx.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        return {"success": False, "error": f"Weather request failed: {error}"}

    if not isinstance(payload, dict):
        return {"success": False, "error": "Weather service returned an invalid response"}
    return {
        "success": True,
        "location": display_location,
        "weather": payload,
        "message": _format_weather(payload, display_location),
    }
