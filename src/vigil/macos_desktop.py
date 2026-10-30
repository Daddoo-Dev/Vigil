"""macOS PATH, Applications .app launchers, and LaunchAgents.

No App Store / notarization. Users install from a clone via ``install.command``.
Gatekeeper may still require right-click → Open the first time.
"""

from __future__ import annotations

import logging
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from vigil.config import Paths, load_settings
from vigil.schedule import ScanSchedule

logger = logging.getLogger("vigil.macos")

_PATH_MARKER = "# Vigil PATH (managed by vigil desktop)"
_LAUNCH_SCAN = "com.vigil.scan"
_LAUNCH_TRAY = "com.vigil.tray"


def vigil_bin() -> Path | None:
    found = shutil.which("vigil")
    if found:
        return Path(found).resolve()
    candidate = Path(sys.executable).resolve().parent / "vigil"
    if candidate.is_file():
        return candidate
    return None


def vigil_bin_dir() -> Path | None:
    binary = vigil_bin()
    return binary.parent if binary is not None else None


def applications_dir(home: Path | None = None) -> Path:
    home = Path.home() if home is None else home
    return home / "Applications"


def launch_agents_dir(home: Path | None = None) -> Path:
    home = Path.home() if home is None else home
    return home / "Library" / "LaunchAgents"


def profile_files(home: Path | None = None) -> list[Path]:
    home = Path.home() if home is None else home
    return [home / ".zprofile", home / ".bash_profile", home / ".profile"]


def path_export_line(bin_dir: Path) -> str:
    return f'export PATH="{bin_dir}:$PATH"'


def profile_needs_path(text: str, bin_dir: Path) -> bool:
    if _PATH_MARKER in text and str(bin_dir) in text:
        return False
    return True


def render_profile(text: str, bin_dir: Path) -> str:
    block = f"\n{_PATH_MARKER}\n{path_export_line(bin_dir)}\n"
    if _PATH_MARKER in text:
        # Replace the managed block.
        lines = text.splitlines(keepends=True)
        out: list[str] = []
        skipping = False
        for line in lines:
            if line.startswith(_PATH_MARKER):
                skipping = True
                continue
            if skipping:
                if line.startswith("export PATH=") and "vigil" in line.casefold():
                    continue
                skipping = False
            if not skipping:
                out.append(line)
        body = "".join(out).rstrip() + "\n"
        return body + block
    if text and not text.endswith("\n"):
        text += "\n"
    return text + block


def add_to_shell_path(bin_dir: Path, home: Path | None = None) -> list[Path]:
    """Ensure shell startup files export ``bin_dir``. Returns files written."""
    written: list[Path] = []
    for path in profile_files(home):
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not profile_needs_path(existing, bin_dir) and path.is_file():
            continue
        path.write_text(render_profile(existing, bin_dir), encoding="utf-8")
        written.append(path)
    # Current process.
    current = os.environ.get("PATH", "")
    prefix = str(bin_dir)
    if prefix not in current.split(":"):
        os.environ["PATH"] = prefix + ":" + current
    return written


def app_info_plist(bundle_name: str, display_name: str) -> bytes:
    data = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleExecutable": bundle_name,
        "CFBundleIdentifier": f"dev.vigil.{bundle_name.lower().replace(' ', '')}",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": display_name,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    }
    return plistlib.dumps(data)


def app_launcher_script(vigil: Path, arguments: str) -> str:
    args = f" {arguments}" if arguments else ""
    return (
        "#!/bin/bash\n"
        f'exec "{vigil}"{args}\n'
    )


def write_app_bundle(app_path: Path, *, vigil: Path, arguments: str, display_name: str) -> Path:
    """Write a minimal unsigned .app that runs ``vigil`` with optional args."""
    exe_name = "Vigil"
    macos = app_path / "Contents" / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    script = macos / exe_name
    script.write_text(app_launcher_script(vigil, arguments), encoding="utf-8")
    script.chmod(0o755)
    (app_path / "Contents" / "Info.plist").write_bytes(app_info_plist(exe_name, display_name))
    return app_path


def install_app_bundles(vigil: Path, home: Path | None = None) -> list[Path]:
    root = applications_dir(home)
    root.mkdir(parents=True, exist_ok=True)
    specs = [
        ("Vigil.app", "open", "Vigil"),
        ("Vigil Setup.app", "setup", "Vigil Setup"),
        ("Vigil Tray.app", "tray", "Vigil Tray"),
    ]
    written: list[Path] = []
    for folder, args, title in specs:
        path = root / folder
        if path.exists():
            shutil.rmtree(path)
        write_app_bundle(path, vigil=vigil, arguments=args, display_name=title)
        written.append(path)
    return written


def scan_launch_agent_plist(vigil: Path, schedule: ScanSchedule | None = None) -> dict | None:
    """LaunchAgent payload for the scan schedule, or None when schedule is off."""
    schedule = schedule or ScanSchedule()
    interval = schedule.launchd_interval()
    if interval is None:
        return None
    payload = {
        "Label": _LAUNCH_SCAN,
        "ProgramArguments": [str(vigil), "scan"],
        "StandardOutPath": str(Path.home() / "Library" / "Logs" / "vigil-scan.log"),
        "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "vigil-scan.err"),
    }
    payload.update(interval)
    return payload


def _load_schedule() -> ScanSchedule:
    try:
        return load_settings(Paths.from_env().config_dir / "settings.yaml").schedule
    except Exception:  # noqa: BLE001
        return ScanSchedule()


def uninstall_launch_agent(label: str, home: Path | None = None) -> Path | None:
    directory = launch_agents_dir(home)
    path = directory / f"{label}.plist"
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(path)], check=False, capture_output=True)
    if path.is_file():
        path.unlink()
        return path
    return None


def tray_launch_agent_plist(vigil: Path) -> dict:
    return {
        "Label": _LAUNCH_TRAY,
        "ProgramArguments": [str(vigil), "tray"],
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(Path.home() / "Library" / "Logs" / "vigil-tray.log"),
        "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "vigil-tray.err"),
    }


def install_launch_agent(label: str, payload: dict, home: Path | None = None) -> Path:
    directory = launch_agents_dir(home)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{label}.plist"
    path.write_bytes(plistlib.dumps(payload))
    # load/bootstrap best-effort; fails harmlessly on Linux CI.
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(path)], check=False, capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(path)], check=False, capture_output=True)
    subprocess.run(["launchctl", "enable", f"gui/{uid}/{label}"], check=False, capture_output=True)
    return path


def install_macos_integration(*, quiet: bool = False) -> int:
    vigil = vigil_bin()
    bin_dir = vigil_bin_dir()
    if vigil is None or bin_dir is None:
        if not quiet:
            print("Could not find the vigil binary. Finish packaging/install.command first,")
            print("open a new terminal, then run: vigil desktop")
            print("Fallback: python3 -m vigil setup")
        return 1
    profiles = add_to_shell_path(bin_dir)
    apps = install_app_bundles(vigil)
    schedule = _load_schedule()
    scan_payload = scan_launch_agent_plist(vigil, schedule)
    if scan_payload is None:
        removed = uninstall_launch_agent(_LAUNCH_SCAN)
        scan_plist = removed
    else:
        scan_plist = install_launch_agent(_LAUNCH_SCAN, scan_payload)
    tray_plist = install_launch_agent(_LAUNCH_TRAY, tray_launch_agent_plist(vigil))
    if quiet:
        return 0
    if profiles:
        for path in profiles:
            print(f"Shell PATH: {path}")
        print("Open a new terminal so `vigil` is on PATH.")
    else:
        print(f"Shell PATH already includes: {bin_dir}")
    for app in apps:
        print(f"Applications: {app}")
    print(f"scan schedule: {schedule.describe()}")
    if scan_plist is not None:
        print(f"LaunchAgent: {scan_plist}")
    else:
        print("LaunchAgent: scan timer off")
    print(f"LaunchAgent: {tray_plist} (tray at login)")
    print("Open ~/Applications/Vigil.app for the latest report (first time: right-click → Open).")
    print("Change the timer with: vigil schedule weekly|biweekly|monthly|off|days <N>")
    return 0
