"""Hand-approved requirements, pending proposals, and severity checks.

Fetched pages never write this file. ``vigil review`` is the only writer.
Repo comparisons read ``requirements.yaml`` only.

Severity for a store minimum:

* below the minimum is ``action`` (the message includes the deadline when one exists)
* meeting it, with a deadline still ahead and under 60 days, is ``action``
* meeting it after the deadline has passed produces no finding (a passed date
  must not keep every compliant app on the list forever)
* an inherited value Vigil could not resolve is ``watch``
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from vigil.versions import constraint_lower_bound, version_eq, version_lt

_FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
_DATE_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}")


class _Dumper(yaml.SafeDumper):
    """Quote date-shaped strings so PyYAML does not turn them into date objects."""


def _represent_str(dumper: yaml.SafeDumper, data: str):
    if _DATE_TEXT.fullmatch(data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
    return yaml.representer.SafeRepresenter.represent_str(dumper, data)


_Dumper.add_representer(str, _represent_str)


_HEADER = (
    "# Hand-approved requirements. The scanner never writes this file from the network.\n"
    "# Only `vigil review` changes it.\n"
)


@dataclass(frozen=True)
class Finding:
    severity: str
    message: str
    repo: str | None = None
    priority: str = "normal"
    category: str = "requirement"


@dataclass(frozen=True)
class RepoFacts:
    """The few fields requirement checks need. Scanners fill this in."""

    name: str
    priority: str
    platforms: list[str]
    target_sdk: int | None
    target_sdk_unresolved: bool
    ios_deployment: str | None
    ios_unresolved: bool
    flutter_pin: str | None
    flutter_constraint: str | None
    fvm_channel: str | None = None


@dataclass
class Proposal:
    id: str
    source_id: str
    found_at: str
    quote: str
    snippet_url: str
    suggested_field: str | None
    suggested_value: str | None
    status: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "found_at": self.found_at,
            "quote": self.quote,
            "snippet_url": self.snippet_url,
            "suggested_field": self.suggested_field,
            "suggested_value": self.suggested_value,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Proposal:
        return cls(
            id=str(raw.get("id") or ""),
            source_id=str(raw.get("source_id") or ""),
            found_at=str(raw.get("found_at") or ""),
            quote=str(raw.get("quote") or ""),
            snippet_url=str(raw.get("snippet_url") or ""),
            suggested_field=raw.get("suggested_field") or None,
            suggested_value=(
                None if raw.get("suggested_value") in (None, "") else str(raw.get("suggested_value"))
            ),
            status=str(raw.get("status") or "pending"),
        )


def proposal_id(source_id: str, quote: str) -> str:
    normalized = re.sub(r"\s+", " ", quote).strip().casefold()
    digest = hashlib.sha256(f"{source_id}\n{normalized}".encode()).hexdigest()
    return digest[:16]


def as_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def due_phrase(deadline: date | None, today: date) -> str | None:
    if deadline is None:
        return None
    days = (deadline - today).days
    if days < 0:
        count = -days
        unit = "day" if count == 1 else "days"
        return f"overdue by {count} {unit}"
    if days == 0:
        return "due today"
    unit = "day" if days == 1 else "days"
    return f"due in {days} {unit}"


def load_requirements(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name} must be a YAML mapping")
    return loaded


def last_verified_text(requirements: dict) -> str:
    try:
        verified = as_date(requirements.get("last_verified"))
    except (TypeError, ValueError):
        return "unreadable"
    return verified.isoformat() if verified else "never"


def save_requirements(path: Path, data: dict) -> None:
    body = yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True)
    path.write_text(_HEADER + body, encoding="utf-8")


def load_proposals(path: Path) -> list[Proposal]:
    if not path.is_file():
        return []
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return []
    if not isinstance(loaded, dict):
        raise ValueError("requirements.pending.yaml must be a mapping")
    raw_items = loaded.get("proposals") or []
    if not isinstance(raw_items, list):
        raise ValueError("requirements.pending.yaml: 'proposals' must be a list")
    return [Proposal.from_dict(item) for item in raw_items if isinstance(item, dict)]


def save_proposals(path: Path, proposals: list[Proposal]) -> None:
    header = (
        "# Proposals produced by scans. Accept or dismiss them with `vigil review`.\n"
        "# Vigil does not copy these into requirements.yaml on its own.\n"
    )
    body = yaml.dump(
        {"proposals": [item.to_dict() for item in proposals]},
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
    )
    path.write_text(header + body, encoding="utf-8")


def merge_proposals(existing: list[Proposal], fresh: list[Proposal]) -> list[Proposal]:
    """Keep dismissed and accepted ids so the same quote is not proposed again."""
    known = {item.id for item in existing}
    return existing + [item for item in fresh if item.id not in known]


def _entry(requirements: dict, *parts: str) -> dict | None:
    node: object = requirements
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, dict) and "value" in node else None


def _deadline(entry: dict, today: date) -> date | None:
    if "deadline" not in entry or entry.get("deadline") in (None, ""):
        return None
    try:
        return as_date(entry.get("deadline"))
    except (TypeError, ValueError):
        return None


def _with_due(message: str, deadline: date | None, today: date) -> str:
    phrase = due_phrase(deadline, today)
    if phrase:
        return f"{message}, {phrase}"
    return message


def _upcoming_action(deadline: date | None, today: date) -> bool:
    if deadline is None:
        return False
    days = (deadline - today).days
    return 0 <= days < 60


def compare_repo(facts: RepoFacts, requirements: dict, today: date) -> list[Finding]:
    findings: list[Finding] = []
    if "android" in facts.platforms:
        findings.extend(_android(facts, requirements, today))
    if "ios" in facts.platforms:
        findings.extend(_ios(facts, requirements, today))
    findings.extend(_flutter(facts, requirements, today))
    return findings


def _android(facts: RepoFacts, requirements: dict, today: date) -> list[Finding]:
    entry = _entry(requirements, "android", "target_api_min")
    if entry is None:
        return []
    try:
        minimum = int(entry["value"])
    except (TypeError, ValueError):
        return [
            Finding(
                "watch",
                f"{facts.name}: android.target_api_min value {entry['value']!r} is not an integer",
                facts.name,
                facts.priority,
            )
        ]
    deadline = _deadline(entry, today)
    if facts.target_sdk is None:
        if facts.target_sdk_unresolved:
            return [
                Finding(
                    "watch",
                    f"{facts.name}: target SDK is inherited from the Flutter SDK and could not be resolved",
                    facts.name,
                    facts.priority,
                )
            ]
        return [
            Finding(
                "watch",
                f"{facts.name}: no targetSdk value found",
                facts.name,
                facts.priority,
            )
        ]
    if facts.target_sdk < minimum:
        message = _with_due(
            f"{facts.name}: target SDK {facts.target_sdk} is below Play minimum {minimum}",
            deadline,
            today,
        )
        return [Finding("action", message, facts.name, facts.priority)]
    if _upcoming_action(deadline, today):
        message = _with_due(
            f"{facts.name}: target SDK {facts.target_sdk} meets Play minimum {minimum}",
            deadline,
            today,
        )
        return [Finding("action", message, facts.name, facts.priority)]
    return []


def _ios(facts: RepoFacts, requirements: dict, today: date) -> list[Finding]:
    entry = _entry(requirements, "ios", "min_deployment_target")
    if entry is None:
        return []
    minimum = str(entry["value"])
    deadline = _deadline(entry, today)
    if not facts.ios_deployment:
        detail = (
            "iOS deployment target could not be resolved"
            if facts.ios_unresolved
            else "no iOS deployment target found"
        )
        return [Finding("watch", f"{facts.name}: {detail}", facts.name, facts.priority)]
    findings: list[Finding] = []
    if facts.ios_unresolved:
        findings.append(
            Finding(
                "watch",
                f"{facts.name}: iOS project also has a non-numeric deployment target",
                facts.name,
                facts.priority,
            )
        )
    if version_lt(facts.ios_deployment, minimum):
        message = _with_due(
            f"{facts.name}: iOS deployment target {facts.ios_deployment} is below minimum {minimum}",
            deadline,
            today,
        )
        findings.append(Finding("action", message, facts.name, facts.priority))
    elif _upcoming_action(deadline, today):
        message = _with_due(
            f"{facts.name}: iOS deployment target {facts.ios_deployment} meets minimum {minimum}",
            deadline,
            today,
        )
        findings.append(Finding("action", message, facts.name, facts.priority))
    return findings


def _flutter(facts: RepoFacts, requirements: dict, today: date) -> list[Finding]:
    entry = _entry(requirements, "flutter", "recommended_stable")
    if entry is None:
        return []
    recommended = str(entry["value"])
    deadline = _deadline(entry, today)
    if facts.fvm_channel and not facts.flutter_pin:
        return [
            Finding(
                "watch",
                f"{facts.name}: FVM pin {facts.fvm_channel!r} is not a version, so it cannot be compared to Flutter {recommended}",
                facts.name,
                facts.priority,
            )
        ]
    pin = facts.flutter_pin
    if pin:
        if version_lt(pin, recommended):
            message = _with_due(
                f"{facts.name}: Flutter {pin} is below recommended stable {recommended}",
                deadline,
                today,
            )
            return [Finding("action", message, facts.name, facts.priority)]
        if version_eq(pin, recommended) or not version_lt(recommended, pin):
            if _upcoming_action(deadline, today):
                message = _with_due(
                    f"{facts.name}: Flutter {pin} meets recommended stable {recommended}",
                    deadline,
                    today,
                )
                return [Finding("action", message, facts.name, facts.priority)]
        return []
    lower = constraint_lower_bound(facts.flutter_constraint)
    if lower and version_lt(lower, recommended):
        return [
            Finding(
                "watch",
                f"{facts.name}: Flutter constraint {facts.flutter_constraint} allows versions older than recommended stable {recommended}",
                facts.name,
                facts.priority,
            )
        ]
    if not pin and not facts.flutter_constraint:
        return [
            Finding(
                "watch",
                f"{facts.name}: no Flutter version pin; cannot compare to recommended stable {recommended}",
                facts.name,
                facts.priority,
            )
        ]
    return []


def global_findings(requirements: dict, today: date) -> list[Finding]:
    """Requirements Vigil cannot read from a repo, such as the Xcode minimum.

    A passed deadline is not repeated every month. An upcoming deadline inside
    60 days is ``action`` so it shows up before the store enforces it.
    """
    entry = _entry(requirements, "ios", "min_xcode")
    if entry is None:
        return []
    deadline = _deadline(entry, today)
    if not _upcoming_action(deadline, today):
        return []
    message = _with_due(
        f"Builds must use Xcode {entry['value']} or later. Vigil does not detect the local Xcode version",
        deadline,
        today,
    )
    return [Finding("action", message, None, "high")]


def validate_field(field: str) -> str | None:
    if _FIELD.fullmatch(field or ""):
        return None
    return "field must look like android.target_api_min"


def coerce_value(value: str) -> int | str:
    if re.fullmatch(r"\d+", value.strip()):
        return int(value.strip())
    return value.strip()


def set_requirement_field(
    data: dict,
    field: str,
    value: str,
    deadline: str | None,
    source: str | None,
) -> None:
    parts = field.split(".")
    node = data
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    entry: dict = {"value": coerce_value(value)}
    if deadline:
        entry["deadline"] = deadline
    if source:
        entry["source"] = source
    node[parts[-1]] = entry


def set_last_verified(data: dict, today: date) -> None:
    data["last_verified"] = today.isoformat()
