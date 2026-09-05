"""Cat and dog image retrieval for the floating Catch UI."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import httpx

from config import get_secret


def _download_image(url: str, prefix: str) -> str:
    response = httpx.get(url, timeout=10, follow_redirects=True)
    response.raise_for_status()
    suffix = Path(url.split("?", 1)[0]).suffix or ".jpg"
    with tempfile.NamedTemporaryFile(prefix=f"catch_{prefix}_", suffix=suffix, delete=False) as file:
        file.write(response.content)
        return file.name


def show_animal_image(animal: str) -> dict[str, Any]:
    try:
        if animal == "dog":
            response = httpx.get("https://dog.ceo/api/breeds/image/random", timeout=10)
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "success" or not payload.get("message"):
                return {"success": False, "error": "The dog image service returned no image"}
            url = str(payload["message"])
        elif animal == "cat":
            key = get_secret("CAT_API_KEY")
            if not key:
                return {"success": False, "error": "Cat image API key is not configured"}
            response = httpx.get(
                "https://api.thecatapi.com/v1/images/search?limit=1",
                headers={"x-api-key": key},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            url = str(payload[0]["url"]) if payload and payload[0].get("url") else ""
            if not url:
                return {"success": False, "error": "The cat image service returned no image"}
        else:
            return {"success": False, "error": "Unsupported animal"}
        return {"success": True, "animal": animal, "image_url": url, "image_path": _download_image(url, animal), "message": f"Here is a {animal} image."}
    except (httpx.HTTPError, OSError, KeyError, IndexError, TypeError, ValueError) as error:
        return {"success": False, "error": f"Could not fetch a {animal} image: {error}"}
