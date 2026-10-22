"""Extract requirement candidates from text that changed since the last snapshot.

``Extractor.extract`` is the only method scanners and the review flow depend on.
v1 ships :class:`KeywordExtractor`. A later local model can implement the same
method and be selected from ``settings.yaml`` without touching fetchers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from vigil.config import Source

DEFAULT_KEYWORDS = (
    "target api level",
    "targetsdk",
    "api level",
    "xcode",
    "sdk",
    "must be built with",
    "deadline",
    "required",
    "minimum",
    "deprecat",
    "starting-month",
)

_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
_STARTING_MONTH = re.compile(rf"\bstarting\s+(?:{_MONTHS})\b", re.IGNORECASE)
_LINK_LINE = re.compile(r"\nLink:\s*(\S+)\s*$")
_API_LEVEL = re.compile(r"\bapi level\s+(\d+)\b", re.IGNORECASE)
_XCODE = re.compile(r"\bxcode\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE)
_IOS_TARGET = re.compile(r"\bios\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE)
_FLUTTER_STABLE = re.compile(r"\bflutter sdk stable\s+(\d+(?:\.\d+){1,3})\b", re.IGNORECASE)


@dataclass(frozen=True)
class Candidate:
    quote: str
    snippet_url: str
    suggested_field: str | None = None
    suggested_value: str | None = None


class Extractor(Protocol):
    def extract(self, changed_text: str, source: Source) -> list[Candidate]:
        """Return candidates found in ``changed_text`` for this source."""


def get_extractor(name: str) -> Extractor:
    if name == "keyword":
        return KeywordExtractor()
    raise NotImplementedError(
        f"extractor {name!r} is not implemented. v1 only includes 'keyword'."
    )


class KeywordExtractor:
    """Case-insensitive phrase filter. Returns the matching paragraph, not a rewrite."""

    def extract(self, changed_text: str, source: Source) -> list[Candidate]:
        keywords = tuple(source.keywords) if source.keywords else DEFAULT_KEYWORDS
        found: list[Candidate] = []
        seen: set[str] = set()
        for paragraph in _paragraphs(changed_text):
            quote, link = _split_link(paragraph)
            if not _matches(quote, keywords):
                continue
            key = re.sub(r"\s+", " ", quote).strip().casefold()
            if key in seen:
                continue
            seen.add(key)
            field, value = _suggest(quote)
            found.append(
                Candidate(
                    quote=quote[:700],
                    snippet_url=link or source.url,
                    suggested_field=field,
                    suggested_value=value,
                )
            )
        return found


def _paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text)
    return [part.strip() for part in parts if part.strip()]


def _split_link(paragraph: str) -> tuple[str, str | None]:
    match = _LINK_LINE.search(paragraph)
    if not match:
        return paragraph.strip(), None
    quote = paragraph[: match.start()].strip()
    return quote, match.group(1)


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    for keyword in keywords:
        if keyword == "starting-month":
            if _STARTING_MONTH.search(text):
                return True
            continue
        if keyword.casefold() in lowered:
            return True
    return False


def _unique(pattern: re.Pattern[str], text: str) -> str | None:
    found = pattern.findall(text)
    unique = list(dict.fromkeys(found))
    if len(unique) == 1:
        return unique[0]
    return None


def _suggest(quote: str) -> tuple[str | None, str | None]:
    lowered = quote.casefold()
    if "target api" in lowered or "targetsdk" in lowered or "api level" in lowered:
        return "android.target_api_min", _unique(_API_LEVEL, quote)
    if "xcode" in lowered:
        return "ios.min_xcode", _unique(_XCODE, quote)
    if "deployment target" in lowered or "iphoneos" in lowered:
        return "ios.min_deployment_target", _unique(_IOS_TARGET, quote)
    if "flutter sdk stable" in lowered:
        return "flutter.recommended_stable", _unique(_FLUTTER_STABLE, quote)
    return None, None
