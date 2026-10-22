"""Fetch RSS, JSON, and HTML sources. Failures stay attached to the source; they do not raise."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import feedparser
import httpx
from bs4 import BeautifulSoup

from vigil.config import Source

logger = logging.getLogger("vigil.fetchers")

USER_AGENT = "Vigil/0.1 (personal Flutter maintenance watchdog)"
MAX_BYTES = 3_000_000
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_ATTEMPTS = 3


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    name: str
    status: str
    paragraphs: list[str]
    detail: str


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        timeout=httpx.Timeout(20.0, connect=10.0),
        follow_redirects=True,
    )


def fetch_source(source: Source, client: httpx.Client, sleeper=time.sleep) -> FetchResult:
    """GET the source. HEAD is not used: some Google help pages return 404 to HEAD and 200 to GET."""
    last_error = "no response"
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            response = client.get(source.url)
        except httpx.HTTPError as exc:
            last_error = str(exc)
            logger.warning("%s attempt %s failed: %s", source.id, attempt, exc)
            if attempt < _ATTEMPTS:
                sleeper(attempt)
            continue
        if response.status_code in _RETRY_STATUSES and attempt < _ATTEMPTS:
            last_error = f"HTTP {response.status_code}"
            logger.warning("%s attempt %s got %s", source.id, attempt, response.status_code)
            sleeper(attempt)
            continue
        return _interpret(source, response)
    return FetchResult(source.id, source.name, "failed", [], last_error)


def _interpret(source: Source, response: httpx.Response) -> FetchResult:
    if response.status_code >= 400:
        return FetchResult(
            source.id,
            source.name,
            "failed",
            [],
            f"HTTP {response.status_code}",
        )
    body = response.content[:MAX_BYTES]
    truncated = len(response.content) > MAX_BYTES
    text = body.decode(response.encoding or "utf-8", errors="replace")
    try:
        if source.type == "rss":
            paragraphs = feed_paragraphs(text)
        elif source.type == "json":
            paragraphs = json_paragraphs(text)
        elif source.type == "html":
            paragraphs = html_to_paragraphs(text)
        else:
            return FetchResult(source.id, source.name, "unexpected", [], f"unknown type {source.type}")
    except ValueError as exc:
        return FetchResult(source.id, source.name, "unexpected", [], str(exc))
    if not paragraphs:
        return FetchResult(
            source.id,
            source.name,
            "unexpected",
            [],
            "response did not contain any entries Vigil could read",
        )
    detail = "ok"
    if truncated:
        detail = f"truncated to {MAX_BYTES} bytes"
    return FetchResult(source.id, source.name, "ok", paragraphs[:500], detail)


def feed_paragraphs(body: str) -> list[str]:
    parsed = feedparser.parse(body)
    if not parsed.entries:
        raise ValueError("feed had no entries")
    paragraphs: list[str] = []
    for entry in parsed.entries:
        title = " ".join(str(entry.get("title") or "").split())
        summary_html = ""
        if entry.get("content"):
            summary_html = str(entry.content[0].get("value") or "")
        if not summary_html:
            summary_html = str(entry.get("summary") or entry.get("description") or "")
        summary = _fragment_text(summary_html)[:1500]
        text = " ".join(f"{title}. {summary}".split()).strip(" .")
        if not text:
            continue
        link = str(entry.get("link") or "").strip()
        if link:
            text = f"{text}\nLink: {link}"
        paragraphs.append(text)
    if not paragraphs:
        raise ValueError("feed entries were empty")
    return paragraphs


def json_paragraphs(body: str) -> list[str]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("response was not JSON") from exc
    if isinstance(data, dict) and "current_release" in data and isinstance(data.get("releases"), list):
        return _flutter_releases(data)
    paragraphs = _generic_json(data)
    if not paragraphs:
        raise ValueError("JSON did not contain any entries Vigil could read")
    return paragraphs


def _flutter_releases(data: dict) -> list[str]:
    releases = [item for item in data.get("releases") or [] if isinstance(item, dict)]
    stable = [item for item in releases if item.get("channel") == "stable" and item.get("version")]
    stable.sort(key=lambda item: str(item.get("release_date") or ""), reverse=True)
    lines = []
    for item in stable[:12]:
        day = str(item.get("release_date") or "")[:10]
        dart = item.get("dart_sdk_version") or "unknown"
        lines.append(
            f"Flutter SDK stable {item['version']} (Dart SDK {dart}) released {day}."
        )
    if not lines:
        raise ValueError("Flutter releases JSON had no stable channel")
    return lines


def _generic_json(data: object) -> list[str]:
    rows: object = data
    if isinstance(data, dict):
        for key in ("releases", "items", "entries"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    if not isinstance(rows, list):
        return []
    lines: list[str] = []
    for item in rows[:30]:
        if isinstance(item, str) and item.strip():
            lines.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        bits = []
        for key in ("name", "title", "version", "tag_name", "date", "published_at"):
            value = item.get(key)
            if value and not _looks_like_hash(str(value)):
                bits.append(f"{key}: {value}")
        if bits:
            lines.append(" ".join(bits))
    return lines


def _looks_like_hash(value: str) -> bool:
    return len(value) >= 40 and all(character in "0123456789abcdefABCDEF" for character in value)


def html_to_paragraphs(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript", "svg", "nav", "header", "footer", "form", "iframe"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    blocks = _block_paragraphs(root)
    if len(blocks) >= 1:
        return blocks
    return _line_paragraphs(root)


def _block_paragraphs(root) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for element in root.find_all(["h1", "h2", "h3", "p", "li", "td"]):
        if element.find(["p", "li", "td", "h1", "h2", "h3"]):
            continue
        text = " ".join(element.get_text(" ", strip=True).split())
        if len(text) < 40 or text in seen:
            continue
        seen.add(text)
        found.append(text)
        if len(found) >= 500:
            break
    return found


def _line_paragraphs(root) -> list[str]:
    raw = root.get_text("\n", strip=True)
    found: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        text = " ".join(line.split())
        if len(text) < 40 or text in seen:
            continue
        seen.add(text)
        found.append(text)
        if len(found) >= 500:
            break
    return found


def _fragment_text(fragment: str) -> str:
    if not fragment:
        return ""
    soup = BeautifulSoup(fragment, "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split())
