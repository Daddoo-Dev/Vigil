import json

from vigil.cli import main
from vigil.config import ConfigError, load_repos, load_sources
from vigil.scanners.flutter import parse_fvm_version, read_flutter


def test_init_is_idempotent_and_ships_checked_sources(paths, capsys, monkeypatch):
    monkeypatch.setattr("vigil.cli.install_desktop_integration", lambda quiet=False: 0)
    assert main(["init"]) == 0
    sources = load_sources(paths.config_dir / "sources.yaml")
    by_id = {source.id: source for source in sources}
    assert by_id["android-blog"].url == "https://developer.android.com/static/blog/atom.xml"
    assert by_id["play-target-api"].url.endswith("11926878")
    assert by_id["flutter-stable"].type == "json"
    assert "target_api_min" in (paths.config_dir / "requirements.yaml").read_text(encoding="utf-8")

    repos = paths.config_dir / "repos.yaml"
    repos.write_text("repos: []\n# local edit\n", encoding="utf-8")
    assert main(["init"]) == 0
    assert "local edit" in repos.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert "kept" in captured.out


def test_bad_priority_is_rejected(paths, tmp_path):
    from tests.conftest import write_yaml

    write_yaml(
        paths.config_dir / "repos.yaml",
        {"repos": [{"name": "app", "path": str(tmp_path), "platforms": ["android"], "priority": "urgent"}]},
    )
    try:
        load_repos(paths.config_dir / "repos.yaml")
    except ConfigError as exc:
        assert "priority" in str(exc)
    else:
        raise AssertionError("expected ConfigError")


def test_status_prints_the_summary(paths, capsys):
    paths.status_path.write_text(
        json.dumps(
            {
                "state": "degraded",
                "action_count": 2,
                "pending_count": 1,
                "last_run": "2026-10-21T08:00:00-06:00",
                "report_path": "/tmp/report.html",
                "errors": ["Play: failed (HTTP 503)"],
            }
        ),
        encoding="utf-8",
    )
    assert main(["status"]) == 0
    output = capsys.readouterr().out
    assert "degraded" in output
    assert "action items: 2" in output
    assert "Play: failed (HTTP 503)" in output


def test_scan_command_exits_zero_on_a_degraded_result(paths, monkeypatch):
    monkeypatch.setattr("vigil.cli.run_scan", lambda _paths: {"state": "degraded"})
    assert main(["scan"]) == 0


def test_fvm_pin_and_sdk_resolution(tmp_path, monkeypatch):
    monkeypatch.delenv("FLUTTER_ROOT", raising=False)
    repo = tmp_path / "app"
    (repo / ".fvm").mkdir(parents=True)
    (repo / ".fvm" / "fvm_config.json").write_text(
        '{"flutterSdkVersion": "3.24.5"}\n',
        encoding="utf-8",
    )
    assert parse_fvm_version(repo) == "3.24.5"
    info = read_flutter(repo)
    assert info.pinned_flutter == "3.24.5"
    assert info.notes
