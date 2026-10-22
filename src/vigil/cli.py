"""Command line: setup (default), init, projects, scan, review, status, open, tray, desktop."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from vigil.config import Paths, configure_logging, init_config
from vigil.desktop import install_desktop_integration, open_latest_report, open_reports_folder
from vigil.projects import run_projects
from vigil.review import run_review
from vigil.scan import run_scan
from vigil.setup import needs_setup, run_setup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vigil",
        description="Personal maintenance watchdog for published Flutter apps.",
    )
    parser.add_argument("--verbose", action="store_true", help="also log to the terminal")
    commands = parser.add_subparsers(dest="command", required=False)
    commands.add_parser(
        "setup",
        help="first-run wizard: config, pick projects, optional scan (default if no command)",
    )
    commands.add_parser("init", help="create config directories and example files only")
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
    command = args.command
    if command is None:
        command = "setup" if needs_setup(paths) else "status"

    if command == "init":
        init_config(paths)
        return install_desktop_integration(quiet=False)
    if command == "setup":
        try:
            configure_logging(paths.state_dir, args.verbose)
            return run_setup(paths)
        except KeyboardInterrupt:
            return 130
        except Exception:
            import logging

            logging.getLogger("vigil").exception("internal error")
            print(
                "Vigil crashed. Details are in the log under the state directory.",
                file=sys.stderr,
            )
            return 1
    try:
        configure_logging(paths.state_dir, args.verbose)
        if command == "projects":
            return run_projects(paths, args.dir)
        if command == "scan":
            run_scan(paths)
            return 0
        if command == "review":
            try:
                run_review(paths, date.today())
            except EOFError:
                print("\nReview stopped. Decisions already entered were saved.")
            return 0
        if command == "status":
            if needs_setup(paths) and not paths.status_path.is_file():
                print("Vigil is not set up yet. Run: vigil setup")
                return 0
            print_status(paths)
            return 0
        if command == "open":
            if args.folder:
                return open_reports_folder(paths)
            return open_latest_report(paths)
        if command == "tray":
            from vigil.tray import run_tray

            return run_tray(paths)
        if command == "desktop":
            return install_desktop_integration(quiet=False)
    except KeyboardInterrupt:
        return 130
    except Exception:
        import logging

        logging.getLogger("vigil").exception("internal error")
        print("Vigil crashed. Details are in the log under the state directory.", file=sys.stderr)
        return 1
    return 1


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
