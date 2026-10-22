from pathlib import Path

from vigil.cli import main
from vigil.config import Paths
from vigil.setup import needs_setup, run_setup


def test_needs_setup_when_config_or_repos_missing(paths: Paths, tmp_path: Path):
    assert needs_setup(paths) is True
    from tests.conftest import write_yaml

    write_yaml(paths.config_dir / "sources.yaml", {"sources": []})
    write_yaml(paths.config_dir / "repos.yaml", {"repos": []})
    assert needs_setup(paths) is True
    write_yaml(
        paths.config_dir / "repos.yaml",
        {
            "repos": [
                {
                    "name": "app",
                    "path": str(tmp_path),
                    "platforms": ["android"],
                    "priority": "normal",
                }
            ]
        },
    )
    assert needs_setup(paths) is False


def test_setup_wizard_runs_projects_scan_and_open(paths: Paths):
    calls: list[str] = []

    def fake_desktop():
        calls.append("desktop")
        return 0

    def fake_projects(_paths, **_kwargs):
        calls.append("projects")
        from tests.conftest import write_yaml

        write_yaml(
            paths.config_dir / "repos.yaml",
            {
                "repos": [
                    {
                        "name": "app",
                        "path": "/tmp/app",
                        "platforms": ["android"],
                        "priority": "normal",
                    }
                ]
            },
        )
        # sources required so needs_setup becomes false after projects
        if not (paths.config_dir / "sources.yaml").is_file():
            write_yaml(paths.config_dir / "sources.yaml", {"sources": []})
        return 0

    def fake_scan():
        calls.append("scan")
        return {"state": "ok"}

    def fake_open():
        calls.append("open")
        return 0

    answers = iter(["y"])
    lines: list[str] = []
    code = run_setup(
        paths,
        input_fn=lambda _prompt: next(answers),
        output_fn=lines.append,
        install_desktop=fake_desktop,
        projects=fake_projects,
        scan=fake_scan,
        open_report=fake_open,
        interactive=True,
    )
    assert code == 0
    assert calls == ["desktop", "projects", "scan", "open"]
    assert any("first scan" in line.casefold() or "Scanning" in line for line in lines)


def test_setup_can_skip_scan(paths: Paths):
    from tests.conftest import write_yaml

    def fake_projects(_paths, **_kwargs):
        write_yaml(paths.config_dir / "sources.yaml", {"sources": []})
        write_yaml(
            paths.config_dir / "repos.yaml",
            {
                "repos": [
                    {
                        "name": "app",
                        "path": "/tmp/app",
                        "platforms": ["android"],
                        "priority": "normal",
                    }
                ]
            },
        )
        return 0

    lines: list[str] = []
    code = run_setup(
        paths,
        input_fn=lambda _prompt: "n",
        output_fn=lines.append,
        install_desktop=lambda: 0,
        projects=fake_projects,
        scan=lambda: (_ for _ in ()).throw(AssertionError("scan should not run")),
        open_report=lambda: (_ for _ in ()).throw(AssertionError("open should not run")),
        interactive=True,
    )
    assert code == 0
    assert any("Skipped scan" in line for line in lines)


def test_bare_vigil_runs_setup_when_unset(paths, monkeypatch):
    monkeypatch.setattr(
        "vigil.cli.run_setup",
        lambda _paths: 0,
    )
    assert main([]) == 0


def test_bare_vigil_prints_status_when_configured(paths, monkeypatch, capsys):
    from tests.conftest import write_yaml

    write_yaml(paths.config_dir / "sources.yaml", {"sources": []})
    write_yaml(
        paths.config_dir / "repos.yaml",
        {
            "repos": [
                {
                    "name": "app",
                    "path": "/tmp/app",
                    "platforms": ["android"],
                    "priority": "normal",
                }
            ]
        },
    )
    paths.status_path.write_text(
        '{"state":"ok","action_count":0,"pending_count":0,"last_run":"x","report_path":"/tmp/r.html","errors":[]}\n',
        encoding="utf-8",
    )
    assert main([]) == 0
    assert "state: ok" in capsys.readouterr().out
