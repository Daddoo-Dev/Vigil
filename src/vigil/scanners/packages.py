"""Package outdated data from ``flutter pub outdated --json`` and pubspec.lock."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from vigil.versions import major

_OUTDATED_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class OutdatedPackage:
    name: str
    kind: str
    current: str | None
    upgradable: str | None
    latest: str | None
    discontinued: bool
    retracted: bool
    advisory: bool
    major_behind: bool

    @property
    def is_outdated(self) -> bool:
        return bool(self.current and self.latest and self.current != self.latest)


def parse_lock_versions(text: str) -> dict[str, str]:
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        return {}
    packages = loaded.get("packages") or {}
    if not isinstance(packages, dict):
        return {}
    versions: dict[str, str] = {}
    for name, meta in packages.items():
        if isinstance(meta, dict) and meta.get("version"):
            versions[str(name)] = str(meta["version"])
    return versions


def _version_field(node: object) -> str | None:
    if isinstance(node, dict) and node.get("version"):
        return str(node["version"])
    return None


def parse_outdated(payload: dict) -> list[OutdatedPackage]:
    rows = payload.get("package_dependencies") or payload.get("packages") or []
    if not isinstance(rows, list):
        raise ValueError("outdated JSON has no package list")
    parsed: list[OutdatedPackage] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("package"):
            continue
        current = _version_field(row.get("current"))
        latest = _version_field(row.get("latest"))
        current_major = major(current)
        latest_major = major(latest)
        behind = (
            current_major is not None
            and latest_major is not None
            and latest_major > current_major
        )
        parsed.append(
            OutdatedPackage(
                name=str(row["package"]),
                kind=str(row.get("kind") or "direct"),
                current=current,
                upgradable=_version_field(row.get("upgradable")),
                latest=latest,
                discontinued=bool(row.get("isDiscontinued")),
                retracted=bool(row.get("isCurrentRetracted")),
                advisory=bool(row.get("isCurrentAffectedByAdvisory")),
                major_behind=behind,
            )
        )
    return parsed


def read_lock(repo: Path) -> dict[str, str]:
    path = repo / "pubspec.lock"
    if not path.is_file():
        return {}
    return parse_lock_versions(path.read_text(encoding="utf-8", errors="replace"))


def run_outdated(repo: Path, timeout: float = _OUTDATED_TIMEOUT_SECONDS) -> tuple[list[OutdatedPackage] | None, str | None]:
    """Run ``flutter pub outdated``. A missing Flutter SDK is an error string, not a crash."""
    flutter = shutil.which("flutter")
    if flutter is None:
        return None, "flutter is not on PATH; skipped flutter pub outdated"
    try:
        completed = subprocess.run(
            [flutter, "pub", "outdated", "--json"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, f"flutter pub outdated timed out after {int(timeout)}s"
    except OSError as exc:
        return None, f"could not run flutter pub outdated: {exc}"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        last = detail.splitlines()[-1] if detail else "unknown error"
        return None, f"flutter pub outdated failed: {last[:300]}"
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None, "flutter pub outdated returned unexpected output"
    if not isinstance(payload, dict):
        return None, "flutter pub outdated returned unexpected output"
    try:
        return parse_outdated(payload), None
    except ValueError as exc:
        return None, f"flutter pub outdated returned unexpected output: {exc}"
