"""Ask for a project folder, scan it, and let the user check what to monitor."""

from __future__ import annotations

from pathlib import Path

from vigil.config import ConfigError, Paths, load_repos, load_settings, set_projects_dir
from vigil.discover import discover_projects, mark_selected, write_monitored_repos
from vigil.folders import resolve_folder, run_folder_picker
from vigil.picker import row_text, run_picker


def run_projects(
    paths: Paths,
    directory: Path | None = None,
    *,
    input_fn=input,
    output_fn=print,
    picker=run_picker,
    choose_folder=None,
    interactive: bool | None = None,
) -> int:
    """Scan one folder and write the checked projects to repos.yaml.

    In a terminal, the folder is chosen by browsing. ``picker`` and
    ``choose_folder`` are the checklists tests replace so they do not open a screen.
    """
    paths.ensure()
    if interactive is None:
        import sys

        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    settings_path = paths.config_dir / "settings.yaml"
    folder = _chosen_folder(directory, settings_path, interactive, choose_folder, input_fn, output_fn)
    if folder is None:
        output_fn("No folder chosen.")
        return 0
    folder = folder.expanduser().resolve()
    set_projects_dir(settings_path, folder)
    output_fn(f"Scanning {folder}")
    projects = discover_projects(folder)
    if not projects:
        output_fn(f"No Flutter projects under {folder}.")
        output_fn("A project is a folder with pubspec.yaml that uses Flutter.")
        return 0
    monitored = _load_monitored(paths, output_fn)
    mark_selected(projects, monitored)
    output_fn(f"Found {len(projects)} Flutter projects.")
    if not interactive:
        for project in projects:
            output_fn(row_text(project))
        output_fn("Run vigil projects in a terminal to choose which ones to monitor.")
        return 0
    chosen = picker(projects)
    if chosen is None:
        output_fn("Cancelled. repos.yaml was not changed.")
        return 0
    write_monitored_repos(paths.config_dir / "repos.yaml", chosen)
    selected = sum(1 for project in chosen if project.selected)
    output_fn(f"Monitoring {selected} of {len(chosen)} projects.")
    return 0


def _chosen_folder(directory, settings_path, interactive, choose_folder, input_fn, output_fn) -> Path | None:
    folder = directory
    if folder is None and settings_path.is_file():
        folder = load_settings(settings_path).projects_dir
    if folder is not None and Path(folder).expanduser().is_dir():
        return Path(folder)
    if choose_folder is not None:
        return choose_folder()
    if interactive:
        return run_folder_picker(Path.home())
    return _ask_folder(input_fn, output_fn)


def _ask_folder(input_fn, output_fn) -> Path | None:
    output_fn("Folder that contains your projects:")
    while True:
        try:
            raw = input_fn("> ").strip()
        except EOFError:
            return None
        if not raw:
            return None
        folder = resolve_folder(raw, cwd=Path.cwd(), home=Path.home())
        if folder is not None:
            return folder
        output_fn(f"No folder matches {raw}.")


def _load_monitored(paths: Paths, output_fn) -> list:
    repos_path = paths.config_dir / "repos.yaml"
    if not repos_path.is_file():
        return []
    try:
        return load_repos(repos_path)
    except ConfigError as exc:
        output_fn(f"Could not read the current project list: {exc}")
        return []
