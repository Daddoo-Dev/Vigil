from pathlib import Path

from vigil.host import default_path_roots, system_name


def test_linux_roots_follow_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr("vigil.host.sys.platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    roots = default_path_roots(tmp_path / "home")
    assert roots.config == tmp_path / "cfg"
    assert roots.state == tmp_path / "state"
    assert roots.data == tmp_path / "data"


def test_macos_roots_use_library(monkeypatch, tmp_path):
    monkeypatch.setattr("vigil.host.sys.platform", "darwin")
    home = tmp_path / "home"
    roots = default_path_roots(home)
    assert roots.config == home / "Library" / "Application Support"
    assert roots.state == home / "Library" / "Caches"
    assert roots.data == home / "Library" / "Application Support"


def test_windows_roots_use_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr("vigil.host.sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    roots = default_path_roots(tmp_path / "home")
    assert roots.config == tmp_path / "roaming"
    assert roots.state == tmp_path / "local"
    assert roots.data == tmp_path / "local"


def test_paths_from_env_uses_host_roots(monkeypatch, tmp_path):
    from vigil.config import Paths
    from vigil.host import PathRoots

    monkeypatch.delenv("VIGIL_CONFIG_DIR", raising=False)
    monkeypatch.delenv("VIGIL_STATE_DIR", raising=False)
    monkeypatch.delenv("VIGIL_REPORTS_DIR", raising=False)
    monkeypatch.setattr(
        "vigil.config.default_path_roots",
        lambda: PathRoots(
            config=tmp_path / "support",
            state=tmp_path / "caches",
            data=tmp_path / "support",
        ),
    )
    paths = Paths.from_env()
    assert paths.config_dir == tmp_path / "support" / "vigil"
    assert paths.state_dir == tmp_path / "caches" / "vigil"
    assert paths.reports_dir == tmp_path / "support" / "vigil" / "reports"


def test_system_name_normalization(monkeypatch):
    monkeypatch.setattr("vigil.host.sys.platform", "linux2")
    assert system_name() == "linux"
    monkeypatch.setattr("vigil.host.sys.platform", "darwin")
    assert system_name() == "darwin"
    monkeypatch.setattr("vigil.host.sys.platform", "win32")
    assert system_name() == "windows"
