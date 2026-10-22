from pathlib import Path

from vigil.config import load_repos
from vigil.discover import discover_projects
from vigil.picker import row_text
from vigil.projects import run_projects


def _flutter_app(root: Path, relative: str, *, android: bool = True, ios: bool = False) -> None:
    project = root / relative
    project.mkdir(parents=True)
    (project / "pubspec.yaml").write_text(
        "name: demo\ndependencies:\n  flutter:\n    sdk: flutter\n",
        encoding="utf-8",
    )
    if android:
        (project / "android").mkdir()
    if ios:
        (project / "ios").mkdir()


def test_scan_finds_nested_apps_and_skips_sdks_and_dependencies(tmp_path: Path):
    _flutter_app(tmp_path, "alpha", android=True, ios=True)
    _flutter_app(tmp_path, "group/beta", android=True)
    dart_only = tmp_path / "server"
    dart_only.mkdir()
    (dart_only / "pubspec.yaml").write_text("name: server\n", encoding="utf-8")

    sdk = tmp_path / "vendor" / "flutter"
    (sdk / "bin").mkdir(parents=True)
    (sdk / "bin" / "flutter").write_text("#!/bin/sh\n", encoding="utf-8")
    example = sdk / "examples" / "hello"
    example.mkdir(parents=True)
    (sdk / "packages" / "flutter").mkdir(parents=True)
    (example / "pubspec.yaml").write_text("name: hello\ndependencies:\n  flutter:\n    sdk: flutter\n", encoding="utf-8")

    hidden = tmp_path / "alpha" / "node_modules" / "plugin"
    hidden.mkdir(parents=True)
    (hidden / "pubspec.yaml").write_text("name: plugin\ndependencies:\n  flutter:\n    sdk: flutter\n", encoding="utf-8")
    _flutter_app(tmp_path, "alpha/packages/flame")
    _flutter_app(tmp_path, "alpha/packages/flame/example")

    found = discover_projects(tmp_path)
    assert [project.label for project in found] == ["alpha", "group/beta"]
    alpha = found[0]
    assert alpha.platforms == ["android", "ios"]
    assert found[1].platforms == ["android"]


def test_checked_projects_are_saved_and_previous_priority_is_kept(paths, tmp_path: Path):
    _flutter_app(tmp_path, "alpha", android=True, ios=True)
    _flutter_app(tmp_path, "beta", android=True)
    repos = paths.config_dir / "repos.yaml"
    repos.write_text(
        "repos:\n"
        f"  - name: alpha\n    path: {tmp_path / 'alpha'}\n"
        "    platforms: [android, ios]\n    priority: high\n",
        encoding="utf-8",
    )

    def choose(found):
        by_label = {project.label: project for project in found}
        assert by_label["alpha"].selected is True
        assert by_label["alpha"].priority == "high"
        by_label["beta"].selected = True
        return found

    lines: list[str] = []
    code = run_projects(
        paths,
        tmp_path,
        output_fn=lines.append,
        picker=choose,
        interactive=True,
    )
    assert code == 0
    text = repos.read_text(encoding="utf-8")
    assert "name: alpha" in text
    assert "priority: high" in text
    assert "name: beta" in text
    assert "Monitoring 2 of 2 projects." in lines
    saved = (paths.config_dir / "settings.yaml").read_text(encoding="utf-8")
    assert f"projects_dir: {tmp_path.resolve()}" in saved


def test_unchecked_project_is_left_out(paths, tmp_path: Path):
    _flutter_app(tmp_path, "alpha")
    _flutter_app(tmp_path, "beta")

    def choose(found):
        for project in found:
            project.selected = project.label == "beta"
        return found

    run_projects(paths, tmp_path, output_fn=lambda _line: None, picker=choose, interactive=True)
    repos = load_repos(paths.config_dir / "repos.yaml")
    assert [repo.name for repo in repos] == ["beta"]


def test_cancel_does_not_rewrite_repos(paths, tmp_path: Path):
    _flutter_app(tmp_path, "alpha")
    repos = paths.config_dir / "repos.yaml"
    repos.write_text("repos: []\n# keep me\n", encoding="utf-8")
    code = run_projects(
        paths,
        tmp_path,
        output_fn=lambda _line: None,
        picker=lambda _projects: None,
        interactive=True,
    )
    assert code == 0
    assert repos.read_text(encoding="utf-8") == "repos: []\n# keep me\n"


def test_backslash_and_wrong_case_still_find_the_folder(tmp_path: Path):
    home = tmp_path / "home"
    target = home / "Documents" / "github"
    target.mkdir(parents=True)
    cwd = target / "vigil"
    cwd.mkdir()
    from vigil.folders import resolve_folder

    assert resolve_folder(r"documents\github", cwd=cwd, home=home) == target.resolve()
    assert resolve_folder("~/documents/github", cwd=cwd, home=home) == target.resolve()
    assert resolve_folder("no/such/place", cwd=cwd, home=home) is None


def test_folder_list_starts_on_a_child_not_the_scan_action(tmp_path: Path):
    (tmp_path / "Documents").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "node_modules").mkdir()
    from vigil.folders import folder_rows, opening_cursor

    rows = folder_rows(tmp_path)
    assert rows[0].label == "Search this folder"
    assert rows[0].scans is True
    assert any(row.label == ".." for row in rows)
    assert [row.label for row in rows if row.label.endswith("/")] == ["Documents/"]
    assert opening_cursor(rows) == rows.index(next(row for row in rows if row.label == "Documents/"))


def test_space_stops_at_the_highlighted_folder_and_enter_opens_it(tmp_path: Path):
    projects = tmp_path / "github"
    projects.mkdir()
    (projects / "game_app").mkdir()
    from vigil.folders import activate, folder_rows, opening_cursor

    rows = folder_rows(tmp_path)
    cursor = next(index for index, row in enumerate(rows) if row.label == "github/")
    _location, _cursor, chosen = activate(tmp_path, cursor, choose=True)
    assert chosen == projects.resolve()

    opened, next_cursor, chosen = activate(tmp_path, cursor, choose=False)
    assert chosen is None
    assert opened == projects
    assert folder_rows(opened)[next_cursor].label == "game_app/"
    assert opening_cursor(folder_rows(opened)) == next_cursor


def test_cancelling_the_folder_list_saves_nothing(paths):
    lines: list[str] = []
    code = run_projects(
        paths,
        choose_folder=lambda: None,
        output_fn=lines.append,
        interactive=True,
    )
    assert code == 0
    assert "No folder chosen." in lines
    assert not (paths.config_dir / "repos.yaml").exists()


def test_row_text_uses_checkboxes():
    from vigil.discover import Project

    blank = Project(Path("alpha"), "alpha", ["android", "ios"], selected=False)
    checked = Project(Path("beta"), "beta", ["android"], selected=True)
    assert row_text(blank) == "[ ] alpha    android, ios"
    assert row_text(checked) == "[X] beta    android"
