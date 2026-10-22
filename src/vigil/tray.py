"""Tray icon. This process never scans; it reads status.json and starts ``vigil scan``.

The tray UI uses pystray on every host. Help text and missing-backend hints are
selected by :mod:`vigil.host`. Linux needs AppIndicator under GNOME; macOS and
Windows use the native status-item backends pystray picks.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageDraw

from vigil.config import Paths
from vigil.desktop import open_latest_report, open_reports_folder
from vigil.host import system_name

logger = logging.getLogger("vigil.tray")

POLL_SECONDS = 60
_COLORS = {
    "ok": (46, 125, 50, 255),
    "action": (249, 168, 37, 255),
    "degraded": (198, 40, 40, 255),
    "unknown": (117, 117, 117, 255),
}


class TrayBackend(Protocol):
    """Minimal surface so a future non-pystray tray can be swapped in."""

    def run(self, paths: Paths) -> int:
        """Block until the tray exits. Return a process exit code."""


def backend_help(system: str | None = None) -> str:
    name = system or system_name()
    if name == "linux":
        return (
            "The tray backend is unavailable.\n"
            "On Fedora / GNOME, install:\n"
            "  sudo dnf install python3-gobject libappindicator-gtk3 "
            "gnome-shell-extension-appindicator\n"
            "Then log out and back in, or enable the AppIndicator extension.\n"
            "The scanner does not need the tray. Search for Vigil in the apps grid, "
            "or run `vigil open`.\n"
        )
    if name == "darwin":
        return (
            "The tray backend is unavailable on this Mac.\n"
            "Install Vigil's Python deps (including pystray and Pillow), then run "
            "`vigil tray` again.\n"
            "The scanner does not need the tray. Run `vigil open` for the latest report.\n"
        )
    if name == "windows":
        return (
            "The tray backend is unavailable on this Windows install.\n"
            "Install Vigil's Python deps (including pystray and Pillow), then run "
            "`vigil tray` again.\n"
            "The scanner does not need the tray. Run `vigil open` for the latest report.\n"
        )
    return (
        "The tray backend is unavailable on this system.\n"
        "The scanner does not need the tray. Run `vigil open` for the latest report.\n"
    )


def make_icon(state: str) -> Image.Image:
    color = _COLORS.get(state, _COLORS["unknown"])
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, 60, 60), fill=color)
    return image


def read_status(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def tooltip(status: dict | None) -> str:
    if not status:
        return "Vigil: no scan yet"
    state = status.get("state", "unknown")
    actions = status.get("action_count", 0)
    return f"Vigil: {state} ({actions} actions)"


def vigil_command() -> list[str]:
    found = shutil.which("vigil")
    if found:
        return [found]
    return [sys.executable, "-m", "vigil"]


class PystrayTray:
    """Default tray implementation for Linux, macOS, and Windows."""

    def run(self, paths: Paths) -> int:
        try:
            import pystray
            from pystray import Menu, MenuItem
        except Exception as exc:
            print(backend_help())
            print(f"Import failed: {exc}")
            return 0

        stop = threading.Event()
        scanning = threading.Lock()

        def apply(icon, status: dict | None) -> None:
            state = str(status.get("state")) if status else "unknown"
            icon.icon = make_icon(state)
            icon.title = tooltip(status)

        def refresh(icon) -> None:
            apply(icon, read_status(paths.status_path))

        def watch(icon) -> None:
            seen = None
            while not stop.is_set():
                status = read_status(paths.status_path)
                token = json.dumps(status, sort_keys=True) if status else ""
                if token != seen:
                    seen = token
                    apply(icon, status)
                stop.wait(POLL_SECONDS)

        def open_report(_icon=None, _item=None) -> None:
            code = open_latest_report(paths)
            if code != 0:
                logger.warning("no report to open")

        def open_folder(_icon, _item) -> None:
            open_reports_folder(paths)

        def run_scan_now(icon, _item) -> None:
            if not scanning.acquire(blocking=False):
                return

            def work() -> None:
                try:
                    icon.title = "Vigil: scanning"
                    subprocess.run(vigil_command() + ["scan"], check=False)
                    refresh(icon)
                finally:
                    scanning.release()

            threading.Thread(target=work, daemon=True).start()

        def quit_tray(icon, _item) -> None:
            stop.set()
            icon.stop()

        menu = Menu(
            MenuItem("Open latest report", open_report, default=True),
            MenuItem("Run scan now", run_scan_now),
            MenuItem("Open reports folder", open_folder),
            MenuItem("Quit", quit_tray),
        )
        icon = pystray.Icon("vigil", make_icon("unknown"), "Vigil: no scan yet", menu)

        def setup(icon) -> None:
            icon.visible = True
            threading.Thread(target=watch, args=(icon,), daemon=True).start()

        try:
            icon.run(setup)
        except Exception as exc:
            print(backend_help())
            print(f"Tray exited: {exc}")
            return 0
        finally:
            stop.set()
        return 0


def get_tray(name: str | None = None) -> TrayBackend:
    """Return the tray backend. Today every host uses pystray."""
    _ = name or system_name()
    return PystrayTray()


def run_tray(paths: Paths) -> int:
    return get_tray().run(paths)
