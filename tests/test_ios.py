from pathlib import Path

from vigil.scanners.ios import build_ios_targets, parse_pbxproj, parse_podfile, read_ios

FIXTURES = Path(__file__).parent / "fixtures"


def test_pbxproj_and_podfile_use_the_lower_target():
    pbx = parse_pbxproj((FIXTURES / "ios" / "project.pbxproj").read_text())
    platform = parse_podfile((FIXTURES / "ios" / "Podfile").read_text())
    targets = build_ios_targets(pbx, platform)
    assert pbx == ["12.0", "13.0"]
    assert platform == "12.0"
    assert targets.minimum == "12.0"


def test_non_numeric_target_is_unresolved():
    targets = build_ios_targets(["min_ios_version_supported"], None)
    assert targets.minimum is None
    assert targets.unresolved == ["min_ios_version_supported"]


def test_read_ios_from_a_repo(tmp_path: Path):
    project = tmp_path / "ios" / "Runner.xcodeproj"
    project.mkdir(parents=True)
    (project / "project.pbxproj").write_text(
        (FIXTURES / "ios" / "project.pbxproj").read_text(),
        encoding="utf-8",
    )
    (tmp_path / "ios" / "Podfile").write_text(
        (FIXTURES / "ios" / "Podfile").read_text(),
        encoding="utf-8",
    )
    targets, problem = read_ios(tmp_path)
    assert problem is None
    assert targets is not None and targets.minimum == "12.0"
