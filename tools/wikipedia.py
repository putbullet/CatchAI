"""Fast factual lookups through Wikipedia with graceful fallback."""

from __future__ import annotations

import httpx


USER_AGENT = "Catch/1.0 (ana65123780123@gmail.com)"


def wikipedia_summary(topic: str) -> dict[str, str | bool]:
    try:
        import wikipediaapi
    except ImportError:
        return {"success": False}
    try:
        wiki = wikipediaapi.Wikipedia(user_agent=USER_AGENT, language="en", timeout=3, max_retries=0)
        page = wiki.page(topic.title())
        if not page.exists():
            response = httpx.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "opensearch", "search": topic, "limit": 1, "format": "json"},
                headers={"User-Agent": USER_AGENT},
                timeout=3,
            )
            response.raise_for_status()
            results = response.json()[1]
            if not results:
                return {"success": False}
            page = wiki.page(results[0])
        if not page.exists() or any("disambiguation" in str(category).casefold() for category in page.categories):
            return {"success": False}
        summary = " ".join(page.summary.split())
        if not summary:
            return {"success": False}
        sentences = summary.split(". ")
        return {"success": True, "message": ". ".join(sentences[:3]).strip(". ") + "."}
    except BaseException:
        return {"success": False}
