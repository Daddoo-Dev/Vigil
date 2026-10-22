import json
from datetime import date
from pathlib import Path

from vigil.scanners.expiries import check_expiries, classify_expiry
from vigil.scanners.packages import parse_lock_versions, parse_outdated

FIXTURES = Path(__file__).parent / "fixtures"


def test_outdated_json_flags_major_discontinued_and_retracted():
    payload = json.loads((FIXTURES / "outdated.json").read_text(encoding="utf-8"))
    rows = {item.name: item for item in parse_outdated(payload)}
    assert rows["http"].is_outdated is True
    assert rows["http"].major_behind is False
    assert rows["old_tool"].discontinued is True
    assert rows["old_tool"].retracted is True
    assert rows["old_tool"].major_behind is True
    assert rows["transitive_one"].kind == "transitive"


def test_lock_versions():
    text = """
packages:
  http:
    dependency: "direct main"
    version: "1.2.0"
"""
    assert parse_lock_versions(text)["http"] == "1.2.0"


def test_expiry_thresholds():
    today = date(2026, 10, 21)
    rows, errors = check_expiries(
        [
            {"app": "a", "item": "cert", "expires": "2026-10-25", "notes": "soon"},
            {"app": "a", "item": "key", "expires": "2026-12-01"},
            {"app": "a", "item": "profile", "expires": "2027-06-01"},
            {"app": "a", "item": "old", "expires": "2026-10-01"},
            {"app": "", "item": "bad"},
        ],
        today,
    )
    assert errors
    by_item = {item.item: item for item in rows}
    assert by_item["cert"].severity == "action"
    assert by_item["cert"].days_left == 4
    assert by_item["key"].severity == "watch"
    assert by_item["profile"].severity == "info"
    assert by_item["old"].severity == "action"
    assert by_item["old"].days_left < 0
    assert classify_expiry(14) == "action"
    assert classify_expiry(15) == "watch"
    assert classify_expiry(60) == "watch"
    assert classify_expiry(61) == "info"
