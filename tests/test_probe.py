from datetime import date
from pathlib import Path

from vigil.config import Repo
from vigil.probe import (
    ProbeCandidate,
    _companion_hints,
    collect_probe_candidates,
    run_canary_probes,
    set_dependency_constraint,
)
from vigil.scan import RepoScan
from vigil.scanners.flutter import FlutterInfo
from vigil.scanners.packages import OutdatedPackage


def test_companion_hints_from_pub_output():
    text = (
        "You can try one of the following suggestions to make the pubspec resolve:\n"
        "* Try upgrading your constraint on package_info_plus: "
        "flutter pub add package_info_plus:^10.2.2\n"
        "* Consider downgrading your constraint on file_picker: "
        "flutter pub add file_picker:^10.3.10\n"
    )
    assert _companion_hints(text) == [("package_info_plus", "^10.2.2")]


def test_set_dependency_constraint_rewrites_caret_line():
    text = """name: app
dependencies:
  flutter:
    sdk: flutter
  file_picker: ^10.3.10
  http: ^1.2.0
"""
    out = set_dependency_constraint(text, "file_picker", "^13.3.0")
    assert "file_picker: ^13.3.0" in out
    assert "http: ^1.2.0" in out
    assert "sdk: flutter" in out


def test_canary_build_failure_writes_global_hold(tmp_path: Path):
    repo = tmp_path / "Peek"
    repo.mkdir()
    (repo / "pubspec.yaml").write_text(
        "name: peek\ndependencies:\n  file_picker: ^10.3.10\n",
        encoding="utf-8",
    )
    (repo / "pubspec.lock").write_text("packages: {}\n", encoding="utf-8")

    def fake_build(_path: Path):
        return False, "Extension with name 'flutter' does not exist"

    # Avoid real flutter pub get by patching inside probe via monkey… use build failure
    # after mocking pub get through a custom flow: rewrite only, intercept by
    # replacing module functions in the test via run path that hits build_runner
    # once pub succeeds. Patch _pub_get by temporarily writing a probe helper.
    from vigil import probe as probe_mod

    original_pub = probe_mod._pub_get

    def fake_pub(_path: Path):
        return True, "ok"

    probe_mod._pub_get = fake_pub
    try:
        results = run_canary_probes(
            [
                ProbeCandidate(
                    package="file_picker",
                    latest="13.3.0",
                    current="10.3.10",
                    repo_name="Peek",
                    repo_path=repo,
                    apps=("Peek", "Conclavium"),
                )
            ],
            held_packages=set(),
            today=date(2026, 10, 29),
            budget=1,
            build_runner=fake_build,
        )
    finally:
        probe_mod._pub_get = original_pub

    assert len(results) == 1
    assert results[0].hold is not None
    assert results[0].hold.scope == "global"
    assert results[0].hold.is_blocked
    assert results[0].hold.package == "file_picker"
    assert "Extension with name" in results[0].hold.reason
    # restored
    assert "^10.3.10" in (repo / "pubspec.yaml").read_text(encoding="utf-8")


def test_canary_success_writes_ready(tmp_path: Path):
    repo = tmp_path / "App"
    repo.mkdir()
    (repo / "pubspec.yaml").write_text(
        "name: app\ndependencies:\n  csv: ^7.2.0\n",
        encoding="utf-8",
    )
    (repo / "pubspec.lock").write_text("packages: {}\n", encoding="utf-8")
    from vigil import probe as probe_mod

    original_pub = probe_mod._pub_get
    probe_mod._pub_get = lambda _path: (True, "ok")
    try:
        results = run_canary_probes(
            [
                ProbeCandidate(
                    package="csv",
                    latest="8.0.0",
                    current="7.2.0",
                    repo_name="App",
                    repo_path=repo,
                    apps=("App",),
                )
            ],
            held_packages=set(),
            today=date(2026, 10, 29),
            budget=0,
            build_runner=lambda _path: (True, "ok"),
        )
    finally:
        probe_mod._pub_get = original_pub
    assert results[0].hold is not None
    assert results[0].hold.is_ready


def test_signing_failure_is_inconclusive(tmp_path: Path):
    repo = tmp_path / "App"
    repo.mkdir()
    (repo / "pubspec.yaml").write_text(
        "name: app\ndependencies:\n  purchases_flutter: ^10.0.0\n",
        encoding="utf-8",
    )
    (repo / "pubspec.lock").write_text("packages: {}\n", encoding="utf-8")
    from vigil import probe as probe_mod

    original_pub = probe_mod._pub_get
    probe_mod._pub_get = lambda _path: (True, "ok")
    try:
        results = run_canary_probes(
            [
                ProbeCandidate(
                    package="purchases_flutter",
                    latest="11.0.0",
                    current="10.0.0",
                    repo_name="App",
                    repo_path=repo,
                    apps=("App",),
                )
            ],
            held_packages=set(),
            today=date(2026, 10, 29),
            budget=1,
            build_runner=lambda _path: (
                False,
                'SigningConfig "release" is missing required property "storeFile".',
            ),
        )
    finally:
        probe_mod._pub_get = original_pub
    assert results[0].hold is None
    assert "inconclusive" in results[0].detail


def test_collect_prefers_multi_app_packages():
    def row(name, latest="13.3.0"):
        return OutdatedPackage(
            name=name,
            kind="direct",
            current="10.0.0",
            upgradable="10.0.0",
            resolvable=latest,
            latest=latest,
            discontinued=False,
            retracted=False,
            advisory=False,
            major_behind=True,
        )

    scans = [
        RepoScan(
            repo=Repo("Peek", Path("/tmp/peek"), ["android"], "normal"),
            flutter=FlutterInfo(direct_dependencies={"file_picker": "^10.0.0", "csv": "^7.0.0"}),
            outdated=[row("file_picker"), row("csv", "8.0.0")],
        ),
        RepoScan(
            repo=Repo("Conclavium", Path("/tmp/conc"), ["android"], "normal"),
            flutter=FlutterInfo(direct_dependencies={"file_picker": "^10.0.0"}),
            outdated=[row("file_picker")],
        ),
    ]
    candidates = collect_probe_candidates(scans)
    assert candidates[0].package == "file_picker"
    assert candidates[0].apps == ("Conclavium", "Peek")
