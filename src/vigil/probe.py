"""Canary upgrade probes. Vigil bumps one package, tries pub get + release APK, restores.

A failed ``pub get`` becomes a repo-scoped solver hold. A failed build after a
successful resolve becomes a global hold so other apps stop listing that major.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from vigil.holds import PackageHold, extract_blocked_by, make_hold, make_ready
from vigil.scanners.packages import OutdatedPackage

logger = logging.getLogger("vigil.probe")

_PUB_TIMEOUT = 180
_BUILD_TIMEOUT = 600
_DEP_LINE = re.compile(
    r"^([ \t]*)([A-Za-z0-9_]+):\s*(\^[^\s#]+|\"[^\"]+\"|'[^']+'|[^\s#]+)\s*(#.*)?$"
)
_PUB_ADD_HINT = re.compile(
    r"flutter pub add ([A-Za-z0-9_]+):(\^?[0-9][^\s\"']*)",
    re.IGNORECASE,
)
# Local project/CI setup — not evidence the package major is unshippable.
_INFRA_FAILURE = re.compile(
    r"storeFile|SigningConfig|signingConfig|key\.properties|"
    r"No matching client found for package name|GOOGLE_APPLICATION_CREDENTIALS|"
    r"Failed to read key from store",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProbeCandidate:
    package: str
    latest: str
    current: str | None
    repo_name: str
    repo_path: Path
    apps: tuple[str, ...]


@dataclass(frozen=True)
class ProbeResult:
    hold: PackageHold | None  # ready or blocked verdict
    detail: str


def collect_probe_candidates(scans) -> list[ProbeCandidate]:
    """Unique packages with a resolvable major upgrade, preferring multi-app hits."""
    by_package: dict[str, list[tuple[str, Path, OutdatedPackage]]] = {}
    for scan in scans:
        if "android" not in scan.repo.platforms:
            continue
        for row in scan.outdated:
            if row.kind != "direct" or not row.resolvable_major_upgrade or not row.latest:
                continue
            if row.name not in scan.flutter.direct_dependencies:
                continue
            by_package.setdefault(row.name, []).append((scan.repo.name, scan.repo.path, row))
    candidates: list[ProbeCandidate] = []
    for package, rows in by_package.items():
        latest = rows[0][2].latest or ""
        rows_sorted = sorted(rows, key=lambda item: item[0].casefold())
        name, path, row = rows_sorted[0]
        apps = tuple(sorted({item[0] for item in rows}, key=str.casefold))
        candidates.append(
            ProbeCandidate(
                package=package,
                latest=latest,
                current=row.current,
                repo_name=name,
                repo_path=path,
                apps=apps,
            )
        )
    candidates.sort(key=lambda item: (-len(item.apps), item.package.casefold()))
    return candidates


def run_canary_probes(
    candidates: list[ProbeCandidate],
    *,
    held_packages: set[str],
    today: date,
    budget: int,
    build_runner=None,
) -> list[ProbeResult]:
    """Probe packages not already judged. ``budget`` 0 = drain the whole queue."""
    if budget < 0:
        return []
    limit = len(candidates) if budget == 0 else budget
    if limit == 0:
        return []
    runner = build_runner or _build_debug_apk
    results: list[ProbeResult] = []
    used = 0
    for candidate in candidates:
        if used >= limit:
            break
        if candidate.package in held_packages:
            continue
        if not candidate.latest:
            continue
        used += 1
        logger.info(
            "canary probe %s -> %s on %s (also on %s)",
            candidate.package,
            candidate.latest,
            candidate.repo_name,
            ", ".join(candidate.apps),
        )
        results.append(_probe_one(candidate, today=today, build_runner=runner))
    return results


def _probe_one(candidate: ProbeCandidate, *, today: date, build_runner) -> ProbeResult:
    pubspec = candidate.repo_path / "pubspec.yaml"
    lock = candidate.repo_path / "pubspec.lock"
    if not pubspec.is_file():
        return ProbeResult(None, f"{candidate.package}: no pubspec.yaml in {candidate.repo_name}")
    backup_yaml = pubspec.read_text(encoding="utf-8")
    backup_lock = lock.read_text(encoding="utf-8") if lock.is_file() else None
    try:
        rewritten = set_dependency_constraint(backup_yaml, candidate.package, f"^{candidate.latest}")
        if rewritten == backup_yaml:
            return ProbeResult(
                None,
                f"{candidate.package}: could not rewrite constraint in {candidate.repo_name}",
            )
        pubspec.write_text(rewritten, encoding="utf-8")
        pub_ok, pub_detail = _pub_get(candidate.repo_path)
        if not pub_ok:
            # Pub often suggests companion bumps (file_picker 13 → package_info_plus 10).
            companion_text = rewritten
            for package_name, constraint in _companion_hints(pub_detail):
                if package_name == candidate.package:
                    continue
                normalized = constraint if constraint.startswith("^") else f"^{constraint}"
                companion_text = set_dependency_constraint(
                    companion_text, package_name, normalized
                )
            if companion_text != rewritten:
                pubspec.write_text(companion_text, encoding="utf-8")
                pub_ok, pub_detail = _pub_get(candidate.repo_path)
        if not pub_ok:
            by_pkg, by_ver = extract_blocked_by(pub_detail, candidate.package)
            hold = make_hold(
                package=candidate.package,
                latest=candidate.latest,
                reason=_trim_error(pub_detail),
                source="solver",
                scope="repo",
                discovered_in=candidate.repo_name,
                today=today,
                repo=candidate.repo_name,
                status="blocked",
                blocked_by_package=by_pkg,
                blocked_by_version=by_ver,
            )
            return ProbeResult(hold, f"{candidate.package}: pub get failed on {candidate.repo_name}")
        build_ok, build_detail = build_runner(candidate.repo_path)
        if build_ok:
            ready = make_ready(
                package=candidate.package,
                latest=candidate.latest,
                discovered_in=candidate.repo_name,
                today=today,
                apps=candidate.apps,
            )
            return ProbeResult(
                ready,
                f"{candidate.package}: verified Ready on {candidate.repo_name} "
                f"(apps: {', '.join(candidate.apps)})",
            )
        trimmed = _trim_error(build_detail)
        if _INFRA_FAILURE.search(trimmed) or _INFRA_FAILURE.search(build_detail):
            return ProbeResult(
                None,
                f"{candidate.package}: canary inconclusive on {candidate.repo_name} "
                f"(project/signing setup, not a package hold): {trimmed[:180]}",
            )
        hold = make_hold(
            package=candidate.package,
            latest=candidate.latest,
            reason=trimmed,
            source="build",
            scope="global",
            discovered_in=candidate.repo_name,
            today=today,
            status="blocked",
        )
        return ProbeResult(
            hold,
            f"{candidate.package}: blocked on {candidate.repo_name}; global hold written",
        )

    finally:
        pubspec.write_text(backup_yaml, encoding="utf-8")
        if backup_lock is None:
            if lock.is_file():
                lock.unlink()
        else:
            lock.write_text(backup_lock, encoding="utf-8")
        _pub_get(candidate.repo_path)


def set_dependency_constraint(pubspec_text: str, package: str, constraint: str) -> str:
    """Replace a top-level dependency constraint for ``package``."""
    lines = pubspec_text.splitlines(keepends=True)
    in_deps = False
    out: list[str] = []
    replaced = False
    for line in lines:
        raw = line.rstrip("\r\n")
        stripped = raw.strip()
        indent = len(line) - len(line.lstrip(" \t"))
        if indent == 0 and re.match(r"^(dependencies|dev_dependencies)\s*:", stripped):
            in_deps = True
            out.append(line)
            continue
        if in_deps:
            if stripped and not stripped.startswith("#") and indent == 0:
                in_deps = False
            elif in_deps:
                match = _DEP_LINE.match(raw)
                if match and match.group(2) == package:
                    lead, _name, _old, comment = match.groups()
                    suffix = f"  {comment}" if comment else ""
                    newline = "\n" if line.endswith("\n") else ""
                    out.append(f"{lead}{package}: {constraint}{suffix}{newline}")
                    replaced = True
                    continue
        out.append(line)
    return "".join(out) if replaced else pubspec_text


def _pub_get(repo: Path) -> tuple[bool, str]:
    flutter = shutil.which("flutter")
    if flutter is None:
        return False, "flutter is not on PATH"
    try:
        completed = subprocess.run(
            [flutter, "pub", "get"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=_PUB_TIMEOUT,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"flutter pub get timed out after {_PUB_TIMEOUT}s"
    except OSError as exc:
        return False, f"could not run flutter pub get: {exc}"
    if completed.returncode == 0:
        return True, "ok"
    detail = (completed.stderr or completed.stdout or "pub get failed").strip()
    return False, detail


def _build_debug_apk(repo: Path) -> tuple[bool, str]:
    """Debug APK avoids release signing false positives for package holds."""
    flutter = shutil.which("flutter")
    if flutter is None:
        return False, "flutter is not on PATH"
    try:
        completed = subprocess.run(
            [flutter, "build", "apk", "--debug"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=_BUILD_TIMEOUT,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"flutter build apk --debug timed out after {_BUILD_TIMEOUT}s"
    except OSError as exc:
        return False, f"could not run flutter build apk --debug: {exc}"
    if completed.returncode == 0:
        return True, "ok"
    detail = (completed.stderr or completed.stdout or "build failed").strip()
    return False, detail


def _companion_hints(pub_detail: str) -> list[tuple[str, str]]:
    """Upgrade suggestions only — skip downgrade alternatives pub also prints."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in pub_detail.splitlines():
        if "downgrad" in line.casefold():
            continue
        match = _PUB_ADD_HINT.search(line)
        if not match:
            continue
        name, constraint = match.group(1), match.group(2)
        if name in seen:
            continue
        seen.add(name)
        found.append((name, constraint))
        if len(found) >= 2:
            break
    return found


def _trim_error(detail: str) -> str:
    lines = [line.strip() for line in detail.splitlines() if line.strip()]
    interesting = [
        line
        for line in lines
        if not line.startswith("Running ")
        and "Waiting for another flutter" not in line
    ]
    if not interesting:
        interesting = lines
    for index, line in enumerate(interesting):
        lowered = line.casefold()
        if (
            "what went wrong" in lowered
            or "extension with name" in lowered
            or "version solving failed" in lowered
            or "because " in lowered and "depends on" in lowered
        ):
            chunk = interesting[index : index + 6]
            return " ".join(chunk)[:500]
    return " ".join(interesting[-8:])[:500]
