"""Desktop integration: apps launcher, icon, and Linux notification waiter.

Apps-grid ``.desktop`` files and systemd user units are Linux-only. Tray and
notify backends for every host live in :mod:`vigil.tray` and :mod:`vigil.notify`.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from vigil.config import Paths
from vigil.host import default_path_roots, open_path, supports_linux_desktop_files

logger = logging.getLogger("vigil.desktop")

_APP_ID = "vigil"
_ICON_SIZES = (16, 32, 48, 64, 128, 256)


def data_home() -> Path:
    return default_path_roots().data


def config_home() -> Path:
    return default_path_roots().config


def applications_dir() -> Path:
    return data_home() / "applications"


def autostart_dir() -> Path:
    return config_home() / "autostart"


def icons_root() -> Path:
    return data_home() / "icons" / "hicolor"


def vigil_binary() -> str:
    found = shutil.which("vigil")
    if found:
        return found
    return f"{sys.executable} -m vigil"


def latest_report(paths: Paths) -> Path | None:
    """Return the newest report path, preferring status.json then latest.html."""
    status_path = paths.status_path
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = None
        if isinstance(status, dict):
            reported = status.get("report_path")
            if reported:
                candidate = Path(str(reported))
                if candidate.is_file():
                    return candidate
    link = paths.reports_dir / "latest.html"
    if link.exists():
        return link.resolve() if link.is_symlink() else link
    return None


def open_latest_report(paths: Paths) -> int:
    report = latest_report(paths)
    if report is None:
        print("No report yet. Run: vigil scan", file=sys.stderr)
        return 1
    return open_path(report)


def open_reports_folder(paths: Paths) -> int:
    paths.reports_dir.mkdir(parents=True, exist_ok=True)
    return open_path(paths.reports_dir)


def write_icon(path: Path, size: int = 128) -> None:
    """A solid circle matching the tray's action color so the apps grid is recognizable."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = max(1, size // 16)
    draw.ellipse((margin, margin, size - margin - 1, size - margin - 1), fill=(249, 168, 37, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def install_icons() -> Path:
    root = icons_root()
    written = root
    for size in _ICON_SIZES:
        destination = root / f"{size}x{size}" / "apps" / f"{_APP_ID}.png"
        write_icon(destination, size)
        written = destination
    _update_icon_cache(root)
    return written


def _update_icon_cache(root: Path) -> None:
    gtk = shutil.which("gtk-update-icon-cache")
    if gtk is None:
        return
    subprocess.run([gtk, "-f", "-t", str(root)], check=False, capture_output=True)


def app_desktop_text(binary: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Vigil\n"
        "GenericName=Flutter maintenance watchdog\n"
        "Comment=Open the latest Vigil maintenance report\n"
        f"Exec={binary} open\n"
        f"Icon={_APP_ID}\n"
        "Terminal=false\n"
        "Categories=Development;Utility;\n"
        "Keywords=flutter;maintenance;scan;report;\n"
        "StartupNotify=false\n"
        f"X-GNOME-UsesNotifications=true\n"
        "Actions=scan;review;tray;folder;\n"
        "\n"
        "[Desktop Action scan]\n"
        "Name=Run scan\n"
        f"Exec={binary} scan\n"
        "\n"
        "[Desktop Action review]\n"
        "Name=Review proposals\n"
        f"Exec={binary} review\n"
        "\n"
        "[Desktop Action tray]\n"
        "Name=Show tray icon\n"
        f"Exec={binary} tray\n"
        "\n"
        "[Desktop Action folder]\n"
        "Name=Open reports folder\n"
        f"Exec={binary} open --folder\n"
    )


def tray_desktop_text(binary: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Vigil Tray\n"
        "Comment=Vigil status icon in the top bar\n"
        f"Exec={binary} tray\n"
        f"Icon={_APP_ID}\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n"
    )


def install_desktop_integration(*, quiet: bool = False) -> int:
    """Install host desktop hooks for Linux, Windows, or macOS."""
    from vigil.host import system_name

    name = system_name()
    if name == "windows":
        from vigil.windows_desktop import install_windows_integration

        return install_windows_integration(quiet=quiet)
    if name == "darwin":
        from vigil.macos_desktop import install_macos_integration

        return install_macos_integration(quiet=quiet)
    if not supports_linux_desktop_files():
        if not quiet:
            print(f"No desktop-file installer for this host ({name}).")
            print("Run `vigil tray` for the status icon and `vigil open` for the report.")
            print("Fallback if `vigil` is not on PATH: python -m vigil setup")
        return 0
    installed = install_desktop_files()
    units = install_user_units()
    if quiet:
        return 0
    print(f"apps launcher: {installed['app']}")
    print(f"tray autostart: {installed['tray']}")
    for unit in units:
        print(f"systemd: {unit}")
    print("Search for Vigil in the apps grid to open the latest report.")
    print("Log out and back in once so the tray starts, or run: vigil tray")
    return 0


def install_desktop_files(binary: str | None = None) -> dict[str, Path]:
    """Install the apps-grid launcher, tray autostart entry, and icons (Linux)."""
    if not supports_linux_desktop_files():
        raise RuntimeError(
            "Apps-grid desktop files are only installed on Linux. "
            "On macOS or Windows, run `vigil tray` and `vigil open` instead."
        )
    command = binary or vigil_binary()
    applications = applications_dir()
    autostart = autostart_dir()
    applications.mkdir(parents=True, exist_ok=True)
    autostart.mkdir(parents=True, exist_ok=True)
    app_path = applications / "vigil.desktop"
    tray_path = autostart / "vigil-tray.desktop"
    app_path.write_text(app_desktop_text(command), encoding="utf-8")
    tray_path.write_text(tray_desktop_text(command), encoding="utf-8")
    install_icons()
    _update_desktop_database(applications)
    return {"app": app_path, "tray": tray_path}


def _update_desktop_database(directory: Path) -> None:
    tool = shutil.which("update-desktop-database")
    if tool is None:
        return
    subprocess.run([tool, str(directory)], check=False, capture_output=True)


def scan_service_text(binary: str) -> str:
    return (
        "[Unit]\n"
        "Description=Vigil maintenance scan\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={binary} scan\n"
    )


def scan_timer_text() -> str:
    return (
        "[Unit]\n"
        "Description=Run the Vigil maintenance scan every month\n"
        "\n"
        "[Timer]\n"
        "OnCalendar=monthly\n"
        "Persistent=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def install_user_units() -> list[Path]:
    """Install and enable the monthly scan timer for the current user."""
    unit_dir = config_home() / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    binary = vigil_binary()
    service = unit_dir / "vigil-scan.service"
    timer = unit_dir / "vigil-scan.timer"
    service.write_text(scan_service_text(binary), encoding="utf-8")
    timer.write_text(scan_timer_text(), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", "vigil-scan.timer"],
        check=False,
        capture_output=True,
    )
    return [service, timer]


def wait_for_notification_action(message: str, report: Path | None) -> int:
    """Block until the user acts on the notification. Used by the detached helper."""
    command = [
        "notify-send",
        "--app-name=Vigil",
        f"--icon={_APP_ID}",
        "--urgency=normal",
        "--expire-time=0",
        "--hint=string:desktop-entry:vigil",
        "--action=open=Open report",
        "--action=folder=Open folder",
        "Vigil",
        message,
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=86_400)
    except subprocess.TimeoutExpired:
        return 0
    except OSError as exc:
        logger.warning("notify-send failed: %s", exc)
        return 1
    action = (completed.stdout or "").strip()
    if action == "open" and report is not None and report.exists():
        return open_path(report)
    if action == "folder":
        folder = report.parent if report is not None else Paths.from_env().reports_dir
        folder.mkdir(parents=True, exist_ok=True)
        return open_path(folder)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m vigil.desktop wait-notify <message> [report]", file=sys.stderr)
        return 2
    if args[0] == "wait-notify":
        message = args[1] if len(args) > 1 else "Vigil has a report"
        report = Path(args[2]) if len(args) > 2 and args[2] else None
        return wait_for_notification_action(message, report)
    print(f"unknown command: {args[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
