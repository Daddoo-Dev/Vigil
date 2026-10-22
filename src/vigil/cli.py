"""Command line: init, projects, scan, review, status, open, tray, desktop."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from vigil.config import Paths, configure_logging, init_config
from vigil.desktop import (
    install_desktop_files,
    install_user_units,
    open_latest_report,
    open_reports_folder,
)
from vigil.projects import run_projects
from vigil.review import run_review
from vigil.scan import run_scan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vigil")
    parser.add_argument("--verbose", action="store_true", help="also log to the terminal")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="create config directories and example files")
    projects = commands.add_parser("projects", help="choose which projects in a folder to monitor")
    projects.add_argument("--dir", type=Path, help="folder to scan instead of the saved one")
    commands.add_parser("scan", help="scan repos and sources, then write a report")
    commands.add_parser("review", help="accept or dismiss pending requirement proposals")
    commands.add_parser("status", help="print the latest status.json summary")
    open_cmd = commands.add_parser("open", help="open the latest report in your browser")
    open_cmd.add_argument(
        "--folder",
        action="store_true",
        help="open the reports folder instead of the latest file",
    )
    commands.add_parser("tray", help="tray icon that opens reports and can start a scan")
    commands.add_parser(
        "desktop",
        help="install the apps-grid launcher, tray autostart, and monthly timer",
    )
    args = parser.parse_args(argv)
    paths = Paths.from_env()
    if args.command == "init":
        init_config(paths)
        _install_desktop(quiet=False)
        if sys.stdin.isatty() and sys.stdout.isatty():
            return run_projects(paths)
        print("Run `vigil projects` and point it at the folder where you keep projects.")
        return 0
    try:
        configure_logging(paths.state_dir, args.verbose)
        if args.command == "projects":
            return run_projects(paths, args.dir)
        if args.command == "scan":
            run_scan(paths)
            return 0
        if args.command == "review":
            try:
                run_review(paths, date.today())
            except EOFError:
                print("\nReview stopped. Decisions already entered were saved.")
            return 0
        if args.command == "status":
            print_status(paths)
            return 0
        if args.command == "open":
            if args.folder:
                return open_reports_folder(paths)
            return open_latest_report(paths)
        if args.command == "tray":
            from vigil.tray import run_tray

            return run_tray(paths)
        if args.command == "desktop":
            return _install_desktop(quiet=False)
    except KeyboardInterrupt:
        return 130
    except Exception:
        import logging

        logging.getLogger("vigil").exception("internal error")
        print("Vigil crashed. Details are in the log under the state directory.", file=sys.stderr)
        return 1
    return 1


def _install_desktop(*, quiet: bool) -> int:
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


def print_status(paths: Paths) -> None:
    if not paths.status_path.is_file():
        print("No scan yet. Run: vigil scan")
        return
    try:
        status = json.loads(paths.status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"Could not read {paths.status_path}")
        return
    print(f"state: {status.get('state')}")
    print(f"action items: {status.get('action_count')}")
    print(f"pending proposals: {status.get('pending_count')}")
    print(f"last run: {status.get('last_run')}")
    print(f"report: {status.get('report_path')}")
    errors = status.get("errors") or []
    if errors:
        print("errors:")
        for error in errors:
            print(f"  - {error}")
