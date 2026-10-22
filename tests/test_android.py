from pathlib import Path

from vigil.scanners.android import parse_gradle, read_android, resolve_inherited
from vigil.scanners.flutter import parse_flutter_sdk_versions

FIXTURES = Path(__file__).parent / "fixtures"


def test_groovy_literal_sdk_versions():
    sdk = parse_gradle((FIXTURES / "android" / "literal.gradle").read_text())
    assert sdk.compile_sdk is not None and sdk.compile_sdk.number == 34
    assert sdk.min_sdk is not None and sdk.min_sdk.number == 21
    assert sdk.target_sdk is not None and sdk.target_sdk.number == 34
    assert sdk.target_sdk.inherited is False


def test_groovy_flutter_refs_are_unresolved_until_a_sdk_is_supplied():
    sdk = parse_gradle((FIXTURES / "android" / "inherited.gradle").read_text())
    assert sdk.compile_sdk is not None
    assert sdk.compile_sdk.number is None
    assert sdk.compile_sdk.inherited is True
    assert sdk.compile_sdk.unresolved is True
    assert "99" not in (sdk.compile_sdk.raw or "")
    assert sdk.target_sdk is not None and sdk.target_sdk.inherited


def test_kotlin_script_flutter_refs():
    sdk = parse_gradle((FIXTURES / "android" / "inherited.gradle.kts").read_text())
    assert sdk.compile_sdk is not None and sdk.compile_sdk.inherited
    assert sdk.min_sdk is not None and sdk.min_sdk.inherited
    assert sdk.target_sdk is not None and sdk.target_sdk.label.startswith("inherited")


def test_resolve_inherited_from_flutter_sdk_fixture():
    versions = parse_flutter_sdk_versions(FIXTURES / "flutter_sdk")
    assert versions == {"compile": 35, "min": 24, "target": 36}
    sdk = parse_gradle((FIXTURES / "android" / "inherited.gradle.kts").read_text())
    resolved = resolve_inherited(sdk, versions)
    assert resolved.target_sdk is not None
    assert resolved.target_sdk.number == 36
    assert resolved.target_sdk.inherited is True
    assert resolved.target_sdk.unresolved is False
    assert "inherited from Flutter SDK" in resolved.target_sdk.label


def test_missing_sdk_does_not_invent_a_number(tmp_path: Path):
    app = tmp_path / "android" / "app"
    app.mkdir(parents=True)
    (app / "build.gradle.kts").write_text(
        (FIXTURES / "android" / "inherited.gradle.kts").read_text(),
        encoding="utf-8",
    )
    sdk, problem = read_android(tmp_path, None)
    assert problem is None
    assert sdk is not None and sdk.target_sdk is not None
    assert sdk.target_sdk.number is None
    assert sdk.target_sdk.unresolved is True
