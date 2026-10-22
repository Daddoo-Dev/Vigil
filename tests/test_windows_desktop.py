from pathlib import Path

from vigil.windows_desktop import path_needs, vigil_scripts_dir


def test_path_needs_detects_missing_and_existing(tmp_path: Path):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    assert path_needs(scripts, []) is True
    assert path_needs(scripts, [str(scripts)]) is False


def test_vigil_scripts_dir_uses_which(monkeypatch, tmp_path: Path):
    exe = tmp_path / "Scripts" / "vigil.exe"
    exe.parent.mkdir()
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr("vigil.windows_desktop.shutil.which", lambda _name: str(exe))
    assert vigil_scripts_dir() == exe.parent.resolve()


def test_install_windows_integration_is_selected_on_windows(monkeypatch):
    calls: list[bool] = []

    def fake_install(*, quiet: bool = False) -> int:
        calls.append(quiet)
        return 0

    monkeypatch.setattr("vigil.host.system_name", lambda: "windows")
    monkeypatch.setattr(
        "vigil.windows_desktop.install_windows_integration",
        fake_install,
    )
    from vigil.desktop import install_desktop_integration

    assert install_desktop_integration(quiet=True) == 0
    assert calls == [True]
