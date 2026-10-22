"""Expiry dates from the hand-edited expiries.yaml. Vigil never writes that file."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

WARN_DAYS = 60
URGENT_DAYS = 14


@dataclass(frozen=True)
class Expiry:
    app: str
    item: str
    expires: date
    notes: str
    days_left: int
    severity: str


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def load_expiries(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return []
    if not isinstance(loaded, dict):
        raise ValueError("expiries.yaml must be a mapping")
    rows = loaded.get("expiries") or []
    if not isinstance(rows, list):
        raise ValueError("expiries.yaml: 'expiries' must be a list")
    return [row for row in rows if isinstance(row, dict)]


def classify_expiry(days_left: int) -> str:
    if days_left <= URGENT_DAYS:
        return "action"
    if days_left <= WARN_DAYS:
        return "watch"
    return "info"


def check_expiries(rows: list[dict], today: date) -> tuple[list[Expiry], list[str]]:
    found: list[Expiry] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        app = str(row.get("app") or "").strip()
        item = str(row.get("item") or "").strip()
        if not app or not item or "expires" not in row:
            errors.append(f"expiries.yaml entry {index} needs app, item, and expires")
            continue
        try:
            expires = _as_date(row["expires"])
        except (TypeError, ValueError):
            errors.append(f"expiries.yaml entry {index} has an invalid expires date")
            continue
        days_left = (expires - today).days
        found.append(
            Expiry(
                app=app,
                item=item,
                expires=expires,
                notes=str(row.get("notes") or ""),
                days_left=days_left,
                severity=classify_expiry(days_left),
            )
        )
    found.sort(key=lambda item: item.days_left)
    return found, errors


def expiry_message(expiry: Expiry) -> str:
    when = expiry.expires.isoformat()
    if expiry.days_left < 0:
        days = -expiry.days_left
        unit = "day" if days == 1 else "days"
        timing = f"expired {days} {unit} ago ({when})"
    elif expiry.days_left == 0:
        timing = f"expires today ({when})"
    else:
        unit = "day" if expiry.days_left == 1 else "days"
        timing = f"expires in {expiry.days_left} {unit} ({when})"
    note = f" {expiry.notes}" if expiry.notes else ""
    return f"{expiry.app}: {expiry.item} {timing}.{note}".rstrip()
