from pathlib import Path

import pytest

from vigil.config import load_settings, set_schedule
from vigil.schedule import parse_schedule


def test_parse_presets_and_days():
    assert parse_schedule("monthly").describe() == "monthly"
    assert parse_schedule("weekly").describe() == "weekly"
    assert parse_schedule("biweekly").describe() == "every 14 days"
    assert parse_schedule("off").describe().startswith("off")
    assert parse_schedule("days", 45).describe() == "every 45 days"
    with pytest.raises(ValueError):
        parse_schedule("days")
    with pytest.raises(ValueError):
        parse_schedule("hourly")


def test_systemd_timer_bodies():
    monthly = parse_schedule("monthly").systemd_timer()
    assert monthly is not None and "OnCalendar=monthly" in monthly
    weekly = parse_schedule("weekly").systemd_timer()
    assert weekly is not None and "OnCalendar=weekly" in weekly
    biweekly = parse_schedule("biweekly").systemd_timer()
    assert biweekly is not None and "OnUnitActiveSec=14d" in biweekly
    days = parse_schedule("days", 3).systemd_timer()
    assert days is not None and "OnUnitActiveSec=3d" in days
    assert parse_schedule("off").systemd_timer() is None


def test_launchd_and_windows_mappings():
    assert parse_schedule("monthly").launchd_interval()["StartCalendarInterval"]["Day"] == 1
    assert parse_schedule("weekly").launchd_interval()["StartCalendarInterval"]["Weekday"] == 1
    assert parse_schedule("biweekly").launchd_interval()["StartInterval"] == 14 * 86400
    assert parse_schedule("days", 90).launchd_interval()["StartInterval"] == 90 * 86400
    assert parse_schedule("off").launchd_interval() is None

    win = parse_schedule("days", 45).windows_schtasks(r"C:\vigil.exe")
    assert win is not None
    assert "/MO" in win and "45" in win
    assert "/TN" in win and "VigilScan" in win
    assert parse_schedule("off").windows_schtasks(r"C:\vigil.exe") is None


def test_set_schedule_round_trip(tmp_path: Path):
    path = tmp_path / "settings.yaml"
    path.write_text("notify: true\nextractor: keyword\n", encoding="utf-8")
    set_schedule(path, parse_schedule("days", 45))
    settings = load_settings(path)
    assert settings.schedule.kind == "days"
    assert settings.schedule.every_days == 45
    set_schedule(path, parse_schedule("monthly"))
    settings = load_settings(path)
    assert settings.schedule.kind == "monthly"
    assert "every_days" not in path.read_text(encoding="utf-8")
