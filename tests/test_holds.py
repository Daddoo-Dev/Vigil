from datetime import date
from pathlib import Path

from vigil.holds import (
    clear_stale_holds,
    extract_blocked_by,
    is_held,
    is_ready,
    load_holds,
    make_hold,
    make_ready,
    save_holds,
    suppresses,
    upsert_hold,
)


def test_global_hold_suppresses_same_major_across_repos():
    hold = make_hold(
        package="file_picker",
        latest="13.3.0",
        reason="Extension with name 'flutter' does not exist",
        source="build",
        scope="global",
        discovered_in="PeekPersonalFinance",
        today=date(2026, 10, 29),
    )
    assert hold.is_blocked
    assert suppresses(hold, package="file_picker", latest="13.3.0", repo="Conclavium")
    assert suppresses(hold, package="file_picker", latest="13.0.1", repo="Daily Company")
    assert not suppresses(hold, package="file_picker", latest="14.0.0", repo="Conclavium")


def test_ready_matches_and_is_not_blocked():
    ready = make_ready(
        package="csv",
        latest="8.0.0",
        discovered_in="ridewealth_assistant",
        today=date(2026, 10, 29),
        apps=("ridewealth_assistant",),
    )
    assert ready.is_ready
    assert not ready.is_blocked
    assert is_ready([ready], package="csv", latest="8.0.0", repo="ridewealth_assistant")
    assert is_held([ready], package="csv", latest="8.0.0", repo="ridewealth_assistant") is None


def test_repo_hold_only_matches_that_app():
    hold = make_hold(
        package="flutter_secure_storage",
        latest="11.2.0",
        reason="resolvable cannot reach latest",
        source="solver",
        scope="repo",
        discovered_in="PeekPersonalFinance",
        today=date(2026, 10, 29),
        repo="PeekPersonalFinance",
    )
    assert is_held(
        [hold],
        package="flutter_secure_storage",
        latest="11.2.0",
        repo="PeekPersonalFinance",
    )
    assert (
        is_held(
            [hold],
            package="flutter_secure_storage",
            latest="11.2.0",
            repo="Conclavium",
        )
        is None
    )


def test_stale_clears_when_own_latest_moves(tmp_path: Path):
    hold = make_hold(
        package="file_picker",
        latest="13.3.0",
        reason="broken",
        source="build",
        scope="global",
        discovered_in="Peek",
        today=date(2026, 10, 29),
    )
    holds = [hold]
    clear_stale_holds(holds, {"file_picker": "13.4.0"})
    assert holds[0].status == "cleared"
    path = tmp_path / "holds.yaml"
    save_holds(path, holds)
    assert load_holds(path)[0].status == "cleared"


def test_unchanged_blocked_stays_put():
    hold = make_hold(
        package="file_picker",
        latest="13.3.0",
        reason=(
            "Because PeekPersonalFinance depends on both file_picker ^13.3.0 "
            "and package_info_plus ^9.0.0, version solving failed."
        ),
        source="solver",
        scope="repo",
        discovered_in="Peek",
        today=date(2026, 10, 29),
        repo="Peek",
    )
    assert hold.blocked_by_package == "package_info_plus"
    assert hold.blocked_by_version == "9.0.0"
    holds = [hold]
    clear_stale_holds(
        holds,
        {"file_picker": "13.3.0", "package_info_plus": "9.0.0"},
    )
    assert holds[0].is_blocked


def test_blocked_wakes_when_blocker_latest_moves():
    hold = make_hold(
        package="file_picker",
        latest="13.3.0",
        reason=(
            "Because PeekPersonalFinance depends on both file_picker ^13.3.0 "
            "and package_info_plus ^9.0.0, version solving failed."
        ),
        source="solver",
        scope="repo",
        discovered_in="Peek",
        today=date(2026, 10, 29),
        repo="Peek",
    )
    holds = [hold]
    clear_stale_holds(
        holds,
        {"file_picker": "13.3.0", "package_info_plus": "10.2.2"},
    )
    assert holds[0].status == "cleared"


def test_ready_unchanged_stays_put():
    ready = make_ready(
        package="csv", latest="8.0.0", discovered_in="app", today=date(2026, 10, 29)
    )
    holds = [ready]
    clear_stale_holds(holds, {"csv": "8.0.0"})
    assert holds[0].is_ready


def test_extract_blocked_by_either_order():
    left = extract_blocked_by(
        "depends on both file_picker ^13.3.0 and package_info_plus ^9.0.0",
        "file_picker",
    )
    assert left == ("package_info_plus", "9.0.0")
    right = extract_blocked_by(
        "depends on both package_info_plus ^9.0.0 and file_picker ^13.3.0",
        "file_picker",
    )
    assert right == ("package_info_plus", "9.0.0")


def test_upsert_replaces_blocked_with_ready():
    first = make_hold(
        package="file_picker",
        latest="13.3.0",
        reason="old",
        source="build",
        scope="global",
        discovered_in="Peek",
        today=date(2026, 10, 1),
    )
    second = make_ready(
        package="file_picker",
        latest="13.3.0",
        discovered_in="Peek",
        today=date(2026, 10, 29),
    )
    holds = upsert_hold([first], second)
    assert len(holds) == 1
    assert holds[0].is_ready


def test_legacy_active_status_loads_as_blocked():
    from vigil.holds import PackageHold

    legacy = PackageHold.from_dict(
        {
            "id": "x",
            "package": "pkg",
            "blocked_major": 2,
            "latest_when_held": "2.0.0",
            "reason": "x",
            "source": "solver",
            "scope": "global",
            "discovered_in": "a",
            "found_at": "2026-10-29",
            "status": "active",
        }
    )
    assert legacy.is_blocked


def test_blocked_by_roundtrips_yaml(tmp_path: Path):
    hold = make_hold(
        package="file_picker",
        latest="13.3.0",
        reason=(
            "Because Peek depends on both file_picker ^13.3.0 "
            "and package_info_plus ^9.0.0, version solving failed."
        ),
        source="solver",
        scope="repo",
        discovered_in="Peek",
        today=date(2026, 10, 29),
        repo="Peek",
    )
    path = tmp_path / "holds.yaml"
    save_holds(path, [hold])
    loaded = load_holds(path)[0]
    assert loaded.blocked_by_package == "package_info_plus"
    assert loaded.blocked_by_version == "9.0.0"
