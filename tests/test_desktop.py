from pathlib import Path

from vigil.desktop import (
    app_desktop_text,
    install_desktop_files,
    latest_report,
    tray_desktop_text,
    write_icon,
)
from vigil.tray import backend_help


def test_latest_report_prefers_status_then_symlink(paths, tmp_path):
    assert latest_report(paths) is None
    report = paths.reports_dir / "report-2026-10-21.html"
    report.write_text("<html></html>", encoding="utf-8")
    latest = paths.reports_dir / "latest.html"
    latest.symlink_to(report.name)
    assert latest_report(paths) == report.resolve()

    other = paths.reports_dir / "other.html"
    other.write_text("<html>other</html>", encoding="utf-8")
    paths.status_path.write_text(
        '{"state":"degraded","report_path":"%s"}' % other,
        encoding="utf-8",
    )
    assert latest_report(paths) == other


def test_desktop_files_and_icons_are_installed(paths, tmp_path):
    from vigil.desktop import icons_root

    binary = tmp_path / "bin" / "vigil"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)

    installed = install_desktop_files(str(binary))
    app = installed["app"].read_text(encoding="utf-8")
    tray = installed["tray"].read_text(encoding="utf-8")
    assert "Name=Vigil\n" in app
    assert f"Exec={binary} open" in app
    assert "Actions=scan;review;tray;folder;" in app
    assert "Name=Vigil Tray\n" in tray
    assert f"Exec={binary} tray" in tray
    assert (icons_root() / "128x128" / "apps" / "vigil.png").is_file()


def test_desktop_text_helpers_name_the_binary():
    assert "Exec=/opt/vigil open" in app_desktop_text("/opt/vigil")
    assert "Exec=/opt/vigil tray" in tray_desktop_text("/opt/vigil")


def test_write_icon_is_a_png(tmp_path):
    path = tmp_path / "vigil.png"
    write_icon(path, 64)
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_backend_help_mentions_fedora_packages():
    message = backend_help("linux")
    assert "gnome-shell-extension-appindicator" in message
    assert "vigil open" in message
    assert "pystray" in backend_help("darwin")
