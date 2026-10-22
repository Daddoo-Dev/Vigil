"""First-run wizard: config, pick projects, optional first scan, open the report."""

from __future__ import annotations

import sys
from pathlib import Path

from vigil.config import ConfigError, Paths, init_config, load_repos
from vigil.desktop import open_latest_report
from vigil.projects import run_projects
from vigil.scan import run_scan


def needs_setup(paths: Paths) -> bool:
    """True when config is missing or no projects are monitored yet."""
    sources = paths.config_dir / "sources.yaml"
    if not sources.is_file():
        return True
    repos_path = paths.config_dir / "repos.yaml"
    if not repos_path.is_file():
        return True
    try:
        return len(load_repos(repos_path)) == 0
    except (ConfigError, FileNotFoundError):
        return True


def run_setup(
    paths: Paths,
    *,
    input_fn=input,
    output_fn=print,
    install_desktop=None,
    projects=None,
    scan=None,
    open_report=None,
    interactive: bool | None = None,
) -> int:
    """Walk a new user from zero config to a report.

    ``install_desktop``, ``projects``, ``scan``, and ``open_report`` are
    injectable so tests never open a real UI or hit the network.
    """
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()

    output_fn("Vigil first-run setup")
    output_fn("Your project list and reports stay on this machine, not in the git repo.")
    if not interactive:
        output_fn("Run this in a terminal: vigil setup")
        return 0

    init_config(paths)
    if install_desktop is None:
        from vigil.desktop import install_desktop_integration

        install_desktop = lambda: install_desktop_integration(quiet=True)
    install_desktop()

    projects_fn = projects or run_projects
    code = projects_fn(paths, interactive=True)
    if code != 0:
        return code
    if needs_setup(paths):
        output_fn("No projects are monitored yet. Run `vigil setup` again when you are ready.")
        return 0

    answer = _ask(input_fn, output_fn, "Run the first scan now? [Y/n] ", default="y")
    if answer not in {"", "y", "yes"}:
        output_fn("Skipped scan. When you are ready: vigil scan && vigil open")
        return 0

    output_fn("Scanning. The first run can take a few minutes and may list many proposals.")
    output_fn("That is normal: review them later with `vigil review`.")
    scan_fn = scan or (lambda: run_scan(paths))
    status = scan_fn()
    state = status.get("state") if isinstance(status, dict) else None
    if state:
        output_fn(f"Scan finished: {state}")
    open_fn = open_report or (lambda: open_latest_report(paths))
    open_fn()
    output_fn("Opened the latest report. Later: vigil review, vigil status, vigil tray.")
    return 0


def _ask(input_fn, output_fn, prompt: str, *, default: str) -> str:
    try:
        raw = input_fn(prompt)
    except EOFError:
        output_fn("")
        return default
    return str(raw).strip().casefold()
