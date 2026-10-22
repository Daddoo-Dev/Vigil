"""Host OS helpers: default data paths, open-a-file, and system id.

Vigil's personal config never lives in the git checkout. These roots pick the
usual per-user location for Linux (XDG), macOS, and Windows. ``VIGIL_*`` and
the XDG variables still override everything for tests and custom installs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathRoots:
    config: Path
    state: Path
    data: Path


def system_name() -> str:
    """Normalized host id: ``linux``, ``darwin``, ``windows``, or ``other``."""
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform in {"win32", "cygwin"}:
        return "windows"
    return "other"


def default_path_roots(home: Path | None = None) -> PathRoots:
    """Return the platform default roots (without the trailing ``vigil`` name)."""
    home = Path.home() if home is None else home
    name = system_name()
    if name == "darwin":
        support = home / "Library" / "Application Support"
        caches = home / "Library" / "Caches"
        return PathRoots(config=support, state=caches, data=support)
    if name == "windows":
        appdata = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
        local = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
        return PathRoots(config=appdata, state=local, data=local)
    config = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config"))
    state = Path(os.environ.get("XDG_STATE_HOME") or (home / ".local" / "state"))
    data = Path(os.environ.get("XDG_DATA_HOME") or (home / ".local" / "share"))
    return PathRoots(config=config, state=state, data=data)


def open_path(target: Path) -> int:
    """Open a file or folder with the host's default handler."""
    path = str(target)
    name = system_name()
    try:
        if name == "darwin":
            subprocess.Popen(["open", path], start_new_session=True)
        elif name == "windows":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path], start_new_session=True)
    except OSError as exc:
        print(f"Could not open {target}: {exc}", file=sys.stderr)
        return 1
    return 0


def supports_linux_desktop_files() -> bool:
    return system_name() == "linux"
