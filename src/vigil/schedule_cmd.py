"""``vigil schedule`` — show or change the automatic scan timer."""

from __future__ import annotations

from vigil.config import Paths, load_settings, set_schedule
from vigil.schedule import ScanSchedule, parse_schedule


def apply_host_schedule(schedule: ScanSchedule) -> int:
    """Rewrite the OS timer for the current host to match ``schedule``."""
    from vigil.host import system_name

    name = system_name()
    if name == "windows":
        from vigil.windows_desktop import install_scan_task, vigil_exe

        exe = vigil_exe()
        if exe is None:
            print("Could not find vigil.exe. Run packaging install first, then retry.")
            return 1
        ok = install_scan_task(exe, schedule)
        return 0 if ok or schedule.kind == "off" else 1
    if name == "darwin":
        from vigil.macos_desktop import (
            _LAUNCH_SCAN,
            install_launch_agent,
            scan_launch_agent_plist,
            uninstall_launch_agent,
            vigil_bin,
        )

        vigil = vigil_bin()
        if vigil is None:
            print("Could not find the vigil binary. Finish install.command, then retry.")
            return 1
        payload = scan_launch_agent_plist(vigil, schedule)
        if payload is None:
            uninstall_launch_agent(_LAUNCH_SCAN)
        else:
            install_launch_agent(_LAUNCH_SCAN, payload)
        return 0
    from vigil.desktop import install_user_units
    from vigil.host import supports_linux_desktop_files

    if not supports_linux_desktop_files():
        print(f"No automatic timer installer for this host ({name}).")
        print("Run scans manually with: vigil scan")
        return 0
    install_user_units(schedule)
    return 0


def run_schedule(paths: Paths, argv: list[str]) -> int:
    """CLI entry. No args: show current. Args: set schedule then apply host timer."""
    settings_path = paths.config_dir / "settings.yaml"
    if not argv:
        settings = load_settings(settings_path)
        print(f"schedule: {settings.schedule.describe()}")
        print(f"settings: {settings_path}")
        print("Change with: vigil schedule weekly|biweekly|monthly|off|days <N>")
        return apply_host_schedule(settings.schedule)

    kind = argv[0].strip().casefold()
    every_days = None
    if kind == "days":
        if len(argv) < 2:
            print("usage: vigil schedule days <N>")
            return 2
        try:
            every_days = int(argv[1])
        except ValueError:
            print("every_days must be a positive integer")
            return 2
    elif len(argv) > 1:
        print("usage: vigil schedule [weekly|biweekly|monthly|off|days <N>]")
        return 2
    try:
        schedule = parse_schedule(kind, every_days)
    except ValueError as exc:
        print(exc)
        return 2
    paths.ensure()
    set_schedule(settings_path, schedule)
    print(f"schedule: {schedule.describe()}")
    print(f"wrote {settings_path}")
    return apply_host_schedule(schedule)
