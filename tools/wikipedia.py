"""Fast factual lookups through Wikipedia with graceful fallback."""

from __future__ import annotations

import re
from typing import Any
import httpx


USER_AGENT = "Catch/1.0 (ana65123780123@gmail.com)"


def _find_attribute_sentence(text: str, attribute: str) -> str | None:
    sentences = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    if attribute in {"height", "tall"}:
        for sentence in sentences:
            s_lower = sentence.casefold()
            if any(term in s_lower for term in ("standing", "is tall", "height of", "tall,")):
                if any(unit in s_lower for unit in ("foot", "feet", "ft", "meter", "cm", "m tall")):
                    return sentence.strip(". ") + "."
            if re.search(r"\b\d+\s*(?:feet|ft|m)\s*(?:\d+\s*(?:inches|in))?\s*(?:\([^)]+\)\s*)?tall\b", s_lower):
                return sentence.strip(". ") + "."
    elif attribute in {"birthplace", "born"}:
        for sentence in sentences:
            s_lower = sentence.casefold()
            if "born" in s_lower and any(prep in s_lower for prep in (" in ", " at ")):
                return sentence.strip(". ") + "."
    elif attribute in {"age", "old"}:
        for sentence in sentences:
            s_lower = sentence.casefold()
            if "born" in s_lower or "years old" in s_lower:
                return sentence.strip(". ") + "."
    return None


def wikipedia_summary(topic: str, attribute: str | None = None) -> dict[str, Any]:
    try:
        import wikipediaapi
    except ImportError:
        return {"success": False}
    try:
        cleaned_topic = topic.strip(" .!?\"'")
        cleaned_topic = re.sub(
            r"^(?:how\s+tall\s+is|how\s+old\s+is|where\s+was|who\s+is|who\s+was|what\s+is|what\s+are|tell\s+me\s+about)\s+",
            "",
            cleaned_topic,
            flags=re.IGNORECASE,
        ).strip(" .!?")

        wiki = wikipediaapi.Wikipedia(user_agent=USER_AGENT, language="en", timeout=4, max_retries=0)
        page = wiki.page(cleaned_topic.title())
        if not page.exists():
            page = wiki.page(cleaned_topic)
        if not page.exists():
            response = httpx.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "opensearch", "search": cleaned_topic, "limit": 1, "format": "json"},
                headers={"User-Agent": USER_AGENT},
                timeout=4,
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

        if attribute:
            attr_sentence = _find_attribute_sentence(summary, attribute)
            if not attr_sentence and page.text:
                attr_sentence = _find_attribute_sentence(page.text, attribute)
            if attr_sentence:
                # Clean up leading section titles if present
                clean_attr = re.sub(
                    r"^.*?\b((?:Standing\s+)?\d+\s*(?:feet|ft|m)\b.*)$",
                    r"\1",
                    attr_sentence,
                    flags=re.IGNORECASE,
                )
                return {
                    "success": True,
                    "message": clean_attr,
                    "topic": page.title,
                    "summary": summary,
                }

        sentences = summary.split(". ")
        return {
            "success": True,
            "message": ". ".join(sentences[:3]).strip(". ") + ".",
            "topic": page.title,
            "summary": summary,
        }
    except BaseException:
        return {"success": False}
