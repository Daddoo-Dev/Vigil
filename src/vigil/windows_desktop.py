"""Windows Start Menu shortcuts, user PATH, and a monthly scheduled task.

Called from ``vigil desktop`` / setup on Windows. The PowerShell installer also
creates the venv; this module wires the shell experience afterward.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from vigil.config import Paths, load_settings
from vigil.schedule import ScanSchedule, windows_task_names

logger = logging.getLogger("vigil.windows")


def vigil_scripts_dir() -> Path | None:
    """Directory that contains ``vigil.exe`` when installed in a venv or Scripts."""
    found = shutil.which("vigil")
    if found:
        return Path(found).resolve().parent
    # Editable install often puts scripts next to the active interpreter.
    candidate = Path(sys.executable).resolve().parent
    if (candidate / "vigil.exe").is_file() or (candidate / "vigil").is_file():
        return candidate
    return None


def vigil_exe() -> Path | None:
    directory = vigil_scripts_dir()
    if directory is None:
        return None
    for name in ("vigil.exe", "vigil"):
        path = directory / name
        if path.is_file():
            return path
    return None


def user_path_entries() -> list[str]:
    raw = os.environ.get("PATH", "")
    return [part for part in raw.split(os.pathsep) if part]


def path_needs(directory: Path, entries: list[str] | None = None) -> bool:
    target = str(directory)
    current = entries if entries is not None else user_path_entries()
    target_fold = os.path.normcase(os.path.normpath(target))
    for entry in current:
        if os.path.normcase(os.path.normpath(entry)) == target_fold:
            return False
    return True


def add_to_user_path(directory: Path) -> bool:
    """Append ``directory`` to the current user's PATH. Returns True if changed."""
    if sys.platform not in {"win32", "cygwin"}:
        return False
    import winreg

    directory = directory.resolve()
    if not path_needs(directory):
        return False
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE
    ) as key:
        try:
            current, reg_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, reg_type = "", winreg.REG_EXPAND_SZ
        if not isinstance(current, str):
            current = str(current)
        parts = [part for part in current.split(";") if part]
        if not path_needs(directory, parts):
            return False
        parts.append(str(directory))
        winreg.SetValueEx(key, "Path", 0, reg_type, ";".join(parts))
    _broadcast_path_change()
    # So the rest of this process sees it without a new shell.
    os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")
    return True


def _broadcast_path_change() -> None:
    try:
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0, 5000, None
        )
    except Exception as exc:  # noqa: BLE001 - best effort on Windows only
        logger.debug("PATH broadcast failed: %s", exc)


def start_menu_programs() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def create_shortcut(path: Path, target: Path, *, arguments: str = "", description: str = "") -> None:
    """Create a ``.lnk`` via PowerShell (no extra Python deps)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ps = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut('{_ps_literal(path)}')
$shortcut.TargetPath = '{_ps_literal(target)}'
$shortcut.WorkingDirectory = '{_ps_literal(target.parent)}'
$shortcut.Arguments = '{_ps_literal(arguments)}'
$shortcut.Description = '{_ps_literal(description)}'
$shortcut.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        check=False,
        capture_output=True,
        text=True,
    )


def _ps_literal(value: Path | str) -> str:
    text = str(value).replace("'", "''")
    return text


def install_start_menu_shortcuts(exe: Path) -> list[Path]:
    folder = start_menu_programs()
    written = [
        folder / "Vigil.lnk",
        folder / "Vigil Tray.lnk",
        folder / "Vigil Setup.lnk",
    ]
    create_shortcut(written[0], exe, arguments="open", description="Open the latest Vigil report")
    create_shortcut(written[1], exe, arguments="tray", description="Show the Vigil status icon")
    create_shortcut(written[2], exe, arguments="setup", description="Vigil first-run setup")
    return written


def _load_schedule() -> ScanSchedule:
    try:
        return load_settings(Paths.from_env().config_dir / "settings.yaml").schedule
    except Exception:  # noqa: BLE001
        return ScanSchedule()


def _delete_task(name: str) -> None:
    subprocess.run(
        ["schtasks", "/Delete", "/TN", name, "/F"],
        check=False,
        capture_output=True,
        text=True,
    )


def install_scan_task(exe: Path, schedule: ScanSchedule | None = None) -> bool:
    """Register or remove the user scheduled task from the scan schedule."""
    schedule = schedule or ScanSchedule()
    task_name, legacy = windows_task_names()
    _delete_task(legacy)
    args = schedule.windows_schtasks(str(exe))
    if args is None:
        _delete_task(task_name)
        return True
    command = ["schtasks", *args]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        logger.warning(
            "Could not create scan task: %s",
            (completed.stderr or completed.stdout)[:300],
        )
        return False
    return True


def install_monthly_task(exe: Path) -> bool:
    """Backward-compatible alias for :func:`install_scan_task`."""
    return install_scan_task(exe)


def install_windows_integration(*, quiet: bool = False) -> int:
    """PATH + Start Menu shortcuts + scheduled scan task for the current user."""
    exe = vigil_exe()
    scripts = vigil_scripts_dir()
    if exe is None or scripts is None:
        if not quiet:
            print("Could not find vigil.exe. Finish install.ps1 first, open a new terminal, then run: vigil desktop")
        return 1
    changed = add_to_user_path(scripts)
    shortcuts = install_start_menu_shortcuts(exe)
    schedule = _load_schedule()
    task = install_scan_task(exe, schedule)
    if quiet:
        return 0
    if changed:
        print(f"Added to user PATH: {scripts}")
        print("Open a new terminal so `vigil` is found everywhere.")
    else:
        print(f"User PATH already includes: {scripts}")
    for path in shortcuts:
        print(f"Start Menu: {path}")
    print(f"scan schedule: {schedule.describe()}")
    task_name, _legacy = windows_task_names()
    if schedule.kind == "off":
        print(f"Scheduled task: {task_name} removed (off)")
    elif task:
        print(f"Scheduled task: {task_name}")
    else:
        print("Scheduled task was not created; run scans with: vigil scan")
    print("Start Menu → Vigil opens the latest report. Vigil Setup runs the wizard.")
    print("Change the timer with: vigil schedule weekly|biweekly|monthly|off|days <N>")
    return 0
