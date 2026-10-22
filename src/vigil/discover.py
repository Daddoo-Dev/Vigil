"""Find Flutter projects under a folder the user chose."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from vigil.config import Repo

_FLUTTER_BLOCK = re.compile(r"(?m)^flutter:\s*(?:$|#)")
_SKIP_NAMES = {
    "build",
    "node_modules",
    "Pods",
    "ephemeral",
    "android",
    "ios",
    "linux",
    "macos",
    "windows",
    "web",
}


@dataclass
class Project:
    path: Path
    label: str
    platforms: list[str]
    priority: str = "normal"
    selected: bool = False
    save_name: str = field(default="")


def discover_projects(root: Path) -> list[Project]:
    """Walk ``root`` and return Flutter projects.

    A project is a directory whose pubspec uses Flutter. The walk stops there,
    so packages and example apps inside it are not listed again. Flutter SDK
    checkouts and dependency folders are not walked.
    """
    root = root.expanduser().resolve()
    found: list[Project] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=_ignore):
        current = Path(dirpath)
        if _is_flutter_sdk(current):
            dirnames.clear()
            continue
        dirnames[:] = sorted(name for name in dirnames if not _skip_dir(name))
        if "pubspec.yaml" not in filenames:
            continue
        if not _uses_flutter(current / "pubspec.yaml"):
            continue
        platforms = _platforms(current)
        found.append(Project(path=current, label=_label(root, current), platforms=platforms))
        dirnames.clear()
    found.sort(key=lambda project: project.label.casefold())
    return found


def mark_selected(projects: list[Project], monitored: list[Repo]) -> list[Project]:
    """Check projects that are already in repos.yaml and keep their priority."""
    by_path = {repo.path.expanduser().resolve(): repo for repo in monitored}
    for project in projects:
        previous = by_path.get(project.path.resolve())
        if previous is None:
            continue
        project.selected = True
        project.priority = previous.priority
    return projects


def write_monitored_repos(path: Path, projects: list[Project]) -> None:
    """Replace repos.yaml with the checked projects."""
    chosen = [project for project in projects if project.selected]
    _assign_save_names(chosen)
    rows = [
        {
            "name": project.save_name,
            "path": str(project.path),
            "platforms": list(project.platforms),
            "priority": project.priority,
        }
        for project in chosen
    ]
    body = yaml.safe_dump({"repos": rows}, sort_keys=False, allow_unicode=True)
    header = "# Written by `vigil projects`. Run that command again to change the list.\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + body, encoding="utf-8")


def _assign_save_names(projects: list[Project]) -> None:
    counts: dict[str, int] = {}
    for project in projects:
        counts[project.path.name] = counts.get(project.path.name, 0) + 1
    for project in projects:
        if counts[project.path.name] == 1:
            project.save_name = project.path.name
        else:
            project.save_name = f"{project.path.parent.name}-{project.path.name}"


def _label(root: Path, project: Path) -> str:
    try:
        relative = project.resolve().relative_to(root.resolve())
    except ValueError:
        relative = project
    text = relative.as_posix()
    if text == ".":
        return project.name
    return text


def _skip_dir(name: str) -> bool:
    return name.startswith(".") or name in _SKIP_NAMES


def _is_flutter_sdk(directory: Path) -> bool:
    return (directory / "bin" / "flutter").is_file() and (directory / "packages" / "flutter").is_dir()


def _uses_flutter(pubspec: Path) -> bool:
    try:
        text = pubspec.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if "sdk: flutter" in text or _FLUTTER_BLOCK.search(text):
        return True
    return False


def _platforms(directory: Path) -> list[str]:
    platforms = []
    if (directory / "android").is_dir():
        platforms.append("android")
    if (directory / "ios").is_dir():
        platforms.append("ios")
    return platforms


def _ignore(_error: OSError) -> None:
    return None
