"""Store normalized source text and report only the paragraphs that were added."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Diff:
    changed: bool
    added: list[str]


def normalize_paragraph(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def normalize_paragraphs(paragraphs: list[str]) -> list[str]:
    normalized = [normalize_paragraph(item) for item in paragraphs]
    return [item for item in normalized if item]


def content_hash(paragraphs: list[str]) -> str:
    blob = "\n\n".join(paragraphs).encode()
    return hashlib.sha256(blob).hexdigest()


def diff_snapshot(previous: list[str] | None, current: list[str]) -> Diff:
    """Unchanged text is a no-op. Added means paragraphs that were not in the last snapshot.

    A pure deletion or reorder changes the hash but yields no added paragraphs,
    so the caller does not treat it as a missed extraction.
    """
    current = normalize_paragraphs(current)
    if previous is not None:
        previous = normalize_paragraphs(previous)
        if content_hash(previous) == content_hash(current):
            return Diff(changed=False, added=[])
    previous_set = set(previous or [])
    added = [item for item in current if item not in previous_set]
    return Diff(changed=True, added=added)


def load_snapshot(path: Path) -> list[str] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    paragraphs = payload.get("paragraphs") if isinstance(payload, dict) else None
    if not isinstance(paragraphs, list):
        return None
    return [str(item) for item in paragraphs]


def save_snapshot(path: Path, paragraphs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_paragraphs(paragraphs)
    body = {"hash": content_hash(normalized), "paragraphs": normalized}
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
