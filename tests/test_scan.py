import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from tests.conftest import quiet, write_yaml
from vigil.fetchers import json_paragraphs
from vigil.requirements import load_proposals, proposal_id
from vigil.scan import TerminalProgress, run_scan
from vigil.snapshots import load_snapshot, save_snapshot

TODAY = date(2026, 10, 21)


@pytest.fixture(autouse=True)
def no_host_flutter(monkeypatch):
    """Repo checks must not read the Flutter SDK installed on this machine."""
    monkeypatch.delenv("FLUTTER_ROOT", raising=False)
    monkeypatch.setattr("vigil.scanners.flutter.shutil.which", lambda _name: None)
RELEASES = {
    "current_release": {"stable": "abc"},
    "releases": [
        {
            "channel": "stable",
            "version": "3.47.7",
            "dart_sdk_version": "3.13.5",
            "release_date": "2026-10-08",
        }
    ],
}


def _no_outdated(_repo: Path):
    return [], None


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _requirements() -> dict:
    return {
        "android": {"target_api_min": {"value": 36, "deadline": "2026-08-31"}},
        "ios": {
            "min_deployment_target": {"value": "13.0", "deadline": "2026-09-09"},
            "min_xcode": {"value": "26", "deadline": "2026-04-28"},
        },
        "flutter": {"recommended_stable": {"value": "3.47.7"}},
    }


def _write_repo(root: Path, target_sdk: int = 36) -> Path:
    repo = root / "app"
    (repo / "android" / "app").mkdir(parents=True)
    (repo / "ios" / "Runner.xcodeproj").mkdir(parents=True)
    (repo / "android" / "app" / "build.gradle").write_text(
        "android {\n"
        f"    compileSdk {target_sdk}\n"
        "    defaultConfig {\n"
        f"        minSdkVersion 24\n"
        f"        targetSdkVersion {target_sdk}\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    (repo / "ios" / "Runner.xcodeproj" / "project.pbxproj").write_text(
        "IPHONEOS_DEPLOYMENT_TARGET = 13.0;\n",
        encoding="utf-8",
    )
    (repo / "ios" / "Podfile").write_text("platform :ios, '13.0'\n", encoding="utf-8")
    (repo / "pubspec.yaml").write_text(
        "name: app\n"
        "environment:\n"
        "  sdk: '>=3.5.0 <4.0.0'\n"
        "  flutter: '>=3.47.7'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n",
        encoding="utf-8",
    )
    return repo


def _configure(paths, repo: Path, sources: list[dict], **extras) -> None:
    write_yaml(
        paths.config_dir / "repos.yaml",
        {
            "repos": [
                {
                    "name": "Sample",
                    "path": str(repo),
                    "platforms": ["android", "ios"],
                    "priority": "high",
                }
            ]
        },
    )
    write_yaml(paths.config_dir / "sources.yaml", {"sources": sources})
    write_yaml(paths.config_dir / "requirements.yaml", extras.get("requirements", _requirements()))
    write_yaml(
        paths.config_dir / "settings.yaml",
        {"notify": True, "extractor": "keyword"},
    )
    write_yaml(paths.config_dir / "expiries.yaml", {"expiries": extras.get("expiries", [])})
    write_yaml(
        paths.config_dir / "requirements.pending.yaml",
        {"proposals": extras.get("proposals", [])},
    )


def _json_source() -> dict:
    return {
        "id": "flutter-stable",
        "name": "Flutter stable releases",
        "type": "json",
        "url": "https://example.test/releases.json",
        "keywords": [],
    }


def test_clean_scan_is_ok_and_names_the_verified_date(paths, tmp_path):
    repo = _write_repo(tmp_path)
    body = json.dumps(RELEASES)
    _configure(paths, repo, [_json_source()])
    save_snapshot(paths.snapshots_dir / "flutter-stable.json", json_paragraphs(body))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    notified: list[str] = []
    status = run_scan(
        paths,
        client=_client(handler),
        today=TODAY,
        outdated_runner=_no_outdated,
        notify_fn=notified.append,
        sleeper=lambda _seconds: None,
    )
    assert status["state"] == "ok"
    assert status["errors"] == []
    assert status["action_count"] == 0
    assert notified == []
    report = (paths.reports_dir / "latest.html").read_text(encoding="utf-8")
    assert "Requirements last verified: never" in report
    assert "No action or watch items." in report
    assert (paths.reports_dir / "latest.html").is_symlink()


def test_source_failure_is_degraded_and_visible(paths, tmp_path):
    repo = _write_repo(tmp_path)
    _configure(paths, repo, [_json_source()])

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    status = run_scan(
        paths,
        client=_client(handler),
        today=TODAY,
        outdated_runner=_no_outdated,
        notify_fn=quiet,
        sleeper=lambda _seconds: None,
    )
    assert status["state"] == "degraded"
    assert any("failed (HTTP 503)" in error for error in status["errors"])
    report = Path(status["report_path"]).read_text(encoding="utf-8")
    assert "banner-degraded" in report
    assert "Flutter stable releases: failed (HTTP 503)" in report
    assert "Requirements last verified: never" in report


def test_changed_page_with_no_keywords_warns_and_keeps_the_old_snapshot(paths, tmp_path):
    repo = _write_repo(tmp_path)
    source = {
        "id": "play",
        "name": "Play requirements",
        "type": "html",
        "url": "https://example.test/play",
        "keywords": [],
    }
    _configure(paths, repo, [source])
    html = (
        "<html><body><main><p>"
        "The cafe opens early and serves breakfast until the middle of the afternoon."
        "</p></main></body></html>"
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    status = run_scan(
        paths,
        client=_client(handler),
        today=TODAY,
        outdated_runner=_no_outdated,
        notify_fn=quiet,
        sleeper=lambda _seconds: None,
    )
    assert status["state"] == "degraded"
    assert any("changed but nothing extracted: review manually" in error for error in status["errors"])
    assert load_snapshot(paths.snapshots_dir / "play.json") is None
    report = Path(status["report_path"]).read_text(encoding="utf-8")
    assert "changed but nothing extracted: review manually" in report


def test_keyword_hit_becomes_a_pending_proposal(paths, tmp_path):
    repo = _write_repo(tmp_path)
    source = {
        "id": "play",
        "name": "Play requirements",
        "type": "html",
        "url": "https://example.test/play",
        "keywords": [],
    }
    _configure(paths, repo, [source])
    html = (
        "<html><body><main><p>"
        "Starting August 31, 2026, new apps must target API level 36 for store submission."
        "</p></main></body></html>"
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    status = run_scan(
        paths,
        client=_client(handler),
        today=TODAY,
        outdated_runner=_no_outdated,
        notify_fn=quiet,
        sleeper=lambda _seconds: None,
    )
    proposals = load_proposals(paths.config_dir / "requirements.pending.yaml")
    assert status["pending_count"] == 1
    assert proposals[0].status == "pending"
    assert proposals[0].suggested_value == "36"
    assert "API level 36" in proposals[0].quote


def test_dismissed_quote_is_not_proposed_again(paths, tmp_path):
    repo = _write_repo(tmp_path)
    quote = "Starting August 31, 2026, new apps must target API level 36 for store submission."
    source = {
        "id": "play",
        "name": "Play requirements",
        "type": "html",
        "url": "https://example.test/play",
        "keywords": [],
    }
    _configure(
        paths,
        repo,
        [source],
        proposals=[
            {
                "id": proposal_id("play", quote),
                "source_id": "play",
                "found_at": "2026-10-01",
                "quote": quote,
                "snippet_url": "https://example.test/play",
                "suggested_field": "android.target_api_min",
                "suggested_value": "36",
                "status": "dismissed",
            }
        ],
    )
    html = f"<html><body><main><p>{quote}</p></main></body></html>"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    status = run_scan(
        paths,
        client=_client(handler),
        today=TODAY,
        outdated_runner=_no_outdated,
        notify_fn=quiet,
        sleeper=lambda _seconds: None,
    )
    proposals = load_proposals(paths.config_dir / "requirements.pending.yaml")
    assert status["pending_count"] == 0
    assert [item.status for item in proposals] == ["dismissed"]


def test_one_broken_repo_does_not_drop_the_other(paths, tmp_path):
    good = _write_repo(tmp_path)
    missing = tmp_path / "missing"
    write_yaml(
        paths.config_dir / "repos.yaml",
        {
            "repos": [
                {
                    "name": "Broken",
                    "path": str(missing),
                    "platforms": ["android", "ios"],
                    "priority": "normal",
                },
                {
                    "name": "Sample",
                    "path": str(good),
                    "platforms": ["android", "ios"],
                    "priority": "high",
                },
            ]
        },
    )
    body = json.dumps(RELEASES)
    write_yaml(paths.config_dir / "sources.yaml", {"sources": [_json_source()]})
    write_yaml(paths.config_dir / "requirements.yaml", _requirements())
    write_yaml(paths.config_dir / "settings.yaml", {"notify": False, "extractor": "keyword"})
    write_yaml(paths.config_dir / "expiries.yaml", {"expiries": []})
    save_snapshot(paths.snapshots_dir / "flutter-stable.json", json_paragraphs(body))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    status = run_scan(
        paths,
        client=_client(handler),
        today=TODAY,
        outdated_runner=_no_outdated,
        notify_fn=quiet,
        sleeper=lambda _seconds: None,
    )
    report = Path(status["report_path"]).read_text(encoding="utf-8")
    assert status["state"] == "degraded"
    assert any(error.startswith("Broken:") for error in status["errors"])
    assert "Sample" in report
    assert "Broken" in report


def test_discontinued_package_is_an_action(paths, tmp_path):
    repo = _write_repo(tmp_path)
    pubspec = repo / "pubspec.yaml"
    pubspec.write_text(pubspec.read_text(encoding="utf-8") + "  pedantic: ^1.0.0\n", encoding="utf-8")
    body = json.dumps(RELEASES)
    _configure(paths, repo, [_json_source()])
    save_snapshot(paths.snapshots_dir / "flutter-stable.json", json_paragraphs(body))

    def handler(request: httpx.Request) -> httpx.Response:
        if "pub.dev" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "name": "pedantic",
                    "isDiscontinued": True,
                    "replacedBy": "lints",
                    "latest": {"version": "1.11.1"},
                    "versions": [{"version": "1.11.1"}],
                },
            )
        return httpx.Response(200, text=body)

    status = run_scan(
        paths,
        client=_client(handler),
        today=TODAY,
        outdated_runner=_no_outdated,
        notify_fn=quiet,
        sleeper=lambda _seconds: None,
    )
    assert status["state"] == "action"
    report = Path(status["report_path"]).read_text(encoding="utf-8")
    assert "pedantic is discontinued, replaced by lints" in report


def test_notify_runs_only_when_the_scan_is_not_ok(paths, tmp_path):
    repo = _write_repo(tmp_path, target_sdk=34)
    _configure(
        paths,
        repo,
        [_json_source()],
        requirements={"android": {"target_api_min": {"value": 35, "deadline": "2026-12-01"}}},
    )
    body = json.dumps(RELEASES)
    save_snapshot(paths.snapshots_dir / "flutter-stable.json", json_paragraphs(body))
    notes: list[str] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    status = run_scan(
        paths,
        client=_client(handler),
        today=TODAY,
        outdated_runner=_no_outdated,
        notify_fn=notes.append,
        sleeper=lambda _seconds: None,
    )
    assert status["state"] == "action"
    assert notes and "maintenance actions" in notes[0]
    report = Path(status["report_path"]).read_text(encoding="utf-8")
    assert "due in 41 days" in report


class _Line:
    def __init__(self, tty: bool):
        self.tty = tty
        self.parts: list[str] = []

    def isatty(self) -> bool:
        return self.tty

    def write(self, text: str) -> None:
        self.parts.append(text)

    def flush(self) -> None:
        return None


def test_progress_rewrites_the_same_line_on_a_terminal():
    stream = _Line(True)
    progress = TerminalProgress(stream)
    progress("Checking Apple Developer News (1 of 8)")
    progress("Scanning yetimatch (4 of 10 projects)")
    progress.finish()
    text = "".join(stream.parts)
    assert text.startswith("\rChecking Apple Developer News (1 of 8)")
    assert "\rScanning yetimatch (4 of 10 projects)" in text
    assert text.endswith("\n")
    assert "\nScanning" not in text


def test_scan_names_each_project_as_it_goes(paths, tmp_path):
    first = _write_repo(tmp_path)
    second = _write_repo(tmp_path / "other")
    _configure(paths, first, [_json_source()])
    write_yaml(
        paths.config_dir / "repos.yaml",
        {
            "repos": [
                {"name": "adorate", "path": str(first), "platforms": ["android", "ios"], "priority": "normal"},
                {"name": "yetimatch", "path": str(second), "platforms": ["android", "ios"], "priority": "normal"},
            ]
        },
    )
    body = json.dumps(RELEASES)
    save_snapshot(paths.snapshots_dir / "flutter-stable.json", json_paragraphs(body))
    seen: list[str] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    run_scan(
        paths,
        client=_client(handler),
        today=TODAY,
        outdated_runner=_no_outdated,
        notify_fn=quiet,
        sleeper=lambda _seconds: None,
        progress=seen.append,
    )
    assert seen == [
        "Checking Flutter stable releases (1 of 1)",
        "Scanning adorate (1 of 2 projects)",
        "Scanning yetimatch (2 of 2 projects)",
    ]
