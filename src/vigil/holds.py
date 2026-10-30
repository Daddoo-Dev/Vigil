"""Package upgrade verdicts. Vigil writes Ready or Blocked after each probe.

Blocked hides a major everywhere it applies. Ready means the canary succeeded.
Recheck is cheap: re-canary only when this package's latest moves, or when a
recorded ``blocked_by`` dependency's latest moves.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from vigil.versions import major, version_eq, version_lt

_DATE_TEXT = re.compile(r"\d{4}-\d{2}-\d{2}")
_HEADER = (
    "# Package upgrade verdicts. Vigil writes Ready/Blocked after solver or canary probes.\n"
    "# Only Ready majors appear as bump recommendations. Blocked stays out of the todo list.\n"
    "# Recheck when this package's latest moves, or blocked_by's latest moves.\n"
)
_BOTH_DEPS = re.compile(
    r"depends on both\s+([A-Za-z0-9_]+)\s+\^?([0-9][\w.+-]*)\s+and\s+"
    r"([A-Za-z0-9_]+)\s+\^?([0-9][\w.+-]*)",
    re.IGNORECASE,
)
_BLOCKED = frozenset({"blocked", "active"})
_READY = frozenset({"ready"})


class _Dumper(yaml.SafeDumper):
    pass


def _represent_str(dumper: yaml.SafeDumper, data: str):
    if _DATE_TEXT.fullmatch(data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")
    return yaml.representer.SafeRepresenter.represent_str(dumper, data)


_Dumper.add_representer(str, _represent_str)


@dataclass
class PackageHold:
    id: str
    package: str
    blocked_major: int | None
    latest_when_held: str
    reason: str
    source: str  # solver | build
    scope: str  # global | repo
    discovered_in: str
    found_at: str
    status: str = "blocked"  # ready | blocked | cleared
    repo: str | None = None
    blocked_by_package: str | None = None
    blocked_by_version: str | None = None

    @property
    def is_blocked(self) -> bool:
        return self.status in _BLOCKED

    @property
    def is_ready(self) -> bool:
        return self.status in _READY

    def to_dict(self) -> dict:
        status = "blocked" if self.status == "active" else self.status
        payload = {
            "id": self.id,
            "package": self.package,
            "blocked_major": self.blocked_major,
            "latest_when_held": self.latest_when_held,
            "reason": self.reason,
            "source": self.source,
            "scope": self.scope,
            "discovered_in": self.discovered_in,
            "found_at": self.found_at,
            "status": status,
        }
        if self.repo:
            payload["repo"] = self.repo
        if self.blocked_by_package:
            payload["blocked_by_package"] = self.blocked_by_package
        if self.blocked_by_version:
            payload["blocked_by_version"] = self.blocked_by_version
        return payload

    @classmethod
    def from_dict(cls, raw: dict) -> PackageHold:
        blocked = raw.get("blocked_major")
        status = str(raw.get("status") or "blocked")
        if status == "active":
            status = "blocked"
        return cls(
            id=str(raw.get("id") or ""),
            package=str(raw.get("package") or ""),
            blocked_major=int(blocked) if blocked not in (None, "") else None,
            latest_when_held=str(raw.get("latest_when_held") or ""),
            reason=str(raw.get("reason") or ""),
            source=str(raw.get("source") or "solver"),
            scope=str(raw.get("scope") or "global"),
            discovered_in=str(raw.get("discovered_in") or ""),
            found_at=str(raw.get("found_at") or ""),
            status=status,
            repo=(None if raw.get("repo") in (None, "") else str(raw.get("repo"))),
            blocked_by_package=(
                None
                if raw.get("blocked_by_package") in (None, "")
                else str(raw.get("blocked_by_package"))
            ),
            blocked_by_version=(
                None
                if raw.get("blocked_by_version") in (None, "")
                else str(raw.get("blocked_by_version"))
            ),
        )


def hold_id(
    package: str,
    blocked_major: int | None,
    scope: str,
    repo: str | None,
    latest: str,
) -> str:
    key = f"{package}\n{blocked_major}\n{scope}\n{repo or ''}\n{latest}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def extract_blocked_by(reason: str, package: str) -> tuple[str | None, str | None]:
    """Best-effort conflicting package + version from pub solver text."""
    match = _BOTH_DEPS.search(reason or "")
    if not match:
        return None, None
    left, left_ver, right, right_ver = match.groups()
    left_ver = left_ver.rstrip(".,;")
    right_ver = right_ver.rstrip(".,;")
    if left == package:
        return right, right_ver
    if right == package:
        return left, left_ver
    return None, None


def load_holds(path: Path) -> list[PackageHold]:
    if not path.is_file():
        return []
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return []
    if not isinstance(loaded, dict):
        raise ValueError("holds.yaml must be a mapping")
    raw_items = loaded.get("holds") or []
    if not isinstance(raw_items, list):
        raise ValueError("holds.yaml: 'holds' must be a list")
    return [PackageHold.from_dict(item) for item in raw_items if isinstance(item, dict)]


def save_holds(path: Path, holds: list[PackageHold]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.dump(
        {"holds": [item.to_dict() for item in holds]},
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
    )
    path.write_text(_HEADER + body, encoding="utf-8")


def active_holds(holds: list[PackageHold]) -> list[PackageHold]:
    return [item for item in holds if item.is_blocked]


def ready_holds(holds: list[PackageHold]) -> list[PackageHold]:
    return [item for item in holds if item.is_ready]


def _matches_major(
    hold: PackageHold,
    *,
    package: str,
    latest: str | None,
    repo: str | None,
) -> bool:
    if hold.package != package or not latest:
        return False
    if hold.scope == "repo" and hold.repo and hold.repo != repo:
        return False
    held_major = hold.blocked_major
    latest_major = major(latest)
    if held_major is not None and latest_major is not None and latest_major == held_major:
        return True
    if hold.latest_when_held and latest == hold.latest_when_held:
        return True
    return False


def suppresses(
    hold: PackageHold,
    *,
    package: str,
    latest: str | None,
    repo: str | None,
) -> bool:
    if not hold.is_blocked:
        return False
    return _matches_major(hold, package=package, latest=latest, repo=repo)


def is_held(
    holds: list[PackageHold],
    *,
    package: str,
    latest: str | None,
    repo: str | None,
) -> PackageHold | None:
    for hold in active_holds(holds):
        if suppresses(hold, package=package, latest=latest, repo=repo):
            return hold
    return None


def is_ready(
    holds: list[PackageHold],
    *,
    package: str,
    latest: str | None,
    repo: str | None,
) -> PackageHold | None:
    for hold in ready_holds(holds):
        if _matches_major(hold, package=package, latest=latest, repo=repo):
            return hold
    return None


def clear_stale_holds(
    holds: list[PackageHold],
    latest_by_package: dict[str, str],
) -> list[PackageHold]:
    """Clear Ready/Blocked when this package's latest moved, or blocked_by moved."""
    for hold in holds:
        if hold.status == "cleared":
            continue
        latest = latest_by_package.get(hold.package)
        if latest:
            latest_major = major(latest)
            if (
                hold.blocked_major is not None
                and latest_major is not None
                and latest_major > hold.blocked_major
            ):
                hold.status = "cleared"
                continue
            if hold.latest_when_held and version_lt(hold.latest_when_held, latest):
                hold.status = "cleared"
                continue
        if hold.is_blocked and hold.blocked_by_package and hold.blocked_by_version:
            blocker_latest = latest_by_package.get(hold.blocked_by_package)
            # Any move of the conflicting package (usually an upgrade) wakes abc.
            if blocker_latest and not version_eq(hold.blocked_by_version, blocker_latest):
                hold.status = "cleared"
    return holds


def upsert_hold(holds: list[PackageHold], fresh: PackageHold) -> list[PackageHold]:
    """Replace a matching ready/blocked row or append. Cleared rows stay for history."""
    if fresh.scope == "global" and (fresh.is_blocked or fresh.is_ready):
        for existing in holds:
            if (
                (existing.is_blocked or existing.is_ready)
                and existing.package == fresh.package
                and existing.blocked_major == fresh.blocked_major
                and existing.scope == "repo"
            ):
                existing.status = "cleared"
    for index, existing in enumerate(holds):
        if existing.status == "cleared":
            continue
        same_package = existing.package == fresh.package
        same_scope = existing.scope == fresh.scope and existing.repo == fresh.repo
        same_major = existing.blocked_major == fresh.blocked_major
        if same_package and same_scope and same_major:
            holds[index] = fresh
            return holds
    holds.append(fresh)
    return holds


def make_hold(
    *,
    package: str,
    latest: str,
    reason: str,
    source: str,
    scope: str,
    discovered_in: str,
    today: date,
    repo: str | None = None,
    status: str = "blocked",
    blocked_by_package: str | None = None,
    blocked_by_version: str | None = None,
) -> PackageHold:
    blocked = major(latest)
    by_pkg, by_ver = blocked_by_package, blocked_by_version
    if status == "blocked" and not by_pkg:
        by_pkg, by_ver = extract_blocked_by(reason, package)
    return PackageHold(
        id=hold_id(package, blocked, scope, repo, latest),
        package=package,
        blocked_major=blocked,
        latest_when_held=latest,
        reason=reason[:500],
        source=source,
        scope=scope,
        discovered_in=discovered_in,
        found_at=today.isoformat(),
        status=status,
        repo=repo if scope == "repo" else None,
        blocked_by_package=by_pkg,
        blocked_by_version=by_ver,
    )


def make_ready(
    *,
    package: str,
    latest: str,
    discovered_in: str,
    today: date,
    apps: tuple[str, ...] = (),
) -> PackageHold:
    note = f"canary debug build ok on {discovered_in}"
    if apps:
        note = f"{note} (also: {', '.join(apps)})"
    return make_hold(
        package=package,
        latest=latest,
        reason=note,
        source="build",
        scope="global",
        discovered_in=discovered_in,
        today=today,
        status="ready",
    )
