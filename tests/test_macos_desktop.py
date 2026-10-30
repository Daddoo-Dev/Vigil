from pathlib import Path

from vigil.macos_desktop import (
    path_export_line,
    profile_needs_path,
    render_profile,
    scan_launch_agent_plist,
    write_app_bundle,
)


def test_profile_path_block_is_idempotent(tmp_path: Path):
    bin_dir = tmp_path / "venv" / "bin"
    first = render_profile("", bin_dir)
    assert path_export_line(bin_dir) in first
    assert profile_needs_path(first, bin_dir) is False
    second = render_profile(first, bin_dir)
    assert second.count("Vigil PATH") == 1


def test_write_app_bundle_creates_executable(tmp_path: Path):
    vigil = tmp_path / "vigil"
    vigil.write_text("#!/bin/sh\n", encoding="utf-8")
    vigil.chmod(0o755)
    app = tmp_path / "Vigil.app"
    write_app_bundle(app, vigil=vigil, arguments="open", display_name="Vigil")
    script = app / "Contents" / "MacOS" / "Vigil"
    assert script.is_file()
    assert "exec" in script.read_text(encoding="utf-8")
    assert (app / "Contents" / "Info.plist").is_file()


def test_scan_launch_agent_runs_monthly(tmp_path: Path):
    from vigil.schedule import parse_schedule

    vigil = tmp_path / "vigil"
    payload = scan_launch_agent_plist(vigil, parse_schedule("monthly"))
    assert payload is not None
    assert payload["Label"] == "com.vigil.scan"
    assert payload["ProgramArguments"] == [str(vigil), "scan"]
    assert payload["StartCalendarInterval"]["Day"] == 1
    assert scan_launch_agent_plist(vigil, parse_schedule("off")) is None


def test_install_desktop_selects_macos(monkeypatch):
    calls: list[bool] = []

    def fake(*, quiet: bool = False) -> int:
        calls.append(quiet)
        return 0

    monkeypatch.setattr("vigil.host.system_name", lambda: "darwin")
    monkeypatch.setattr("vigil.macos_desktop.install_macos_integration", fake)
    from vigil.desktop import install_desktop_integration

    assert install_desktop_integration(quiet=True) == 0
    assert calls == [True]
