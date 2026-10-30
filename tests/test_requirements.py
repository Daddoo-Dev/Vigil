from datetime import date

from vigil.requirements import RepoFacts, compare_repo, global_findings, merge_proposals, proposal_id
from vigil.requirements import Proposal

TODAY = date(2026, 10, 21)


def _facts(**overrides) -> RepoFacts:
    base = dict(
        name="Sample",
        priority="high",
        platforms=["android", "ios"],
        target_sdk=36,
        target_sdk_unresolved=False,
        ios_deployment="13.0",
        ios_unresolved=False,
        flutter_pin="3.47.7",
        flutter_constraint=None,
        fvm_channel=None,
    )
    base.update(overrides)
    return RepoFacts(**base)


def test_below_play_minimum_is_action_with_the_deadline():
    requirements = {
        "android": {"target_api_min": {"value": 35, "deadline": "2026-12-01"}},
    }
    findings = compare_repo(_facts(target_sdk=34), requirements, TODAY)
    assert len(findings) == 1
    assert findings[0].severity == "action"
    assert findings[0].message == (
        "Sample: target SDK 34 is below Play minimum 35, due in 41 days"
    )


def test_meeting_a_close_deadline_is_still_action():
    requirements = {
        "android": {"target_api_min": {"value": 35, "deadline": "2026-11-20"}},
    }
    findings = compare_repo(_facts(target_sdk=35), requirements, TODAY)
    assert findings[0].severity == "action"
    assert "meets Play minimum 35" in findings[0].message
    assert "due in 30 days" in findings[0].message


def test_meeting_a_far_or_passed_deadline_adds_nothing():
    far = {"android": {"target_api_min": {"value": 35, "deadline": "2027-06-01"}}}
    passed = {"android": {"target_api_min": {"value": 35, "deadline": "2026-08-31"}}}
    assert compare_repo(_facts(target_sdk=35), far, TODAY) == []
    assert compare_repo(_facts(target_sdk=36), passed, TODAY) == []


def test_overdue_and_still_behind_says_overdue():
    requirements = {
        "android": {"target_api_min": {"value": 35, "deadline": "2026-10-11"}},
    }
    findings = compare_repo(_facts(target_sdk=34), requirements, TODAY)
    assert findings[0].severity == "action"
    assert "overdue by 10 days" in findings[0].message


def test_unresolved_inherited_target_is_watch():
    requirements = {"android": {"target_api_min": {"value": 35}}}
    findings = compare_repo(
        _facts(target_sdk=None, target_sdk_unresolved=True),
        requirements,
        TODAY,
    )
    assert findings[0].severity == "watch"
    assert "could not be resolved" in findings[0].message


def test_older_flutter_pin_is_action():
    requirements = {"flutter": {"recommended_stable": {"value": "3.47.7"}}}
    findings = compare_repo(_facts(flutter_pin="3.24.0"), requirements, TODAY)
    assert findings[0].severity == "action"
    assert "3.24.0 is below recommended stable 3.47.7" in findings[0].message


def test_missing_flutter_pin_names_the_recommended_target():
    requirements = {"flutter": {"recommended_stable": {"value": "3.47.7"}}}
    findings = compare_repo(
        _facts(flutter_pin=None, flutter_constraint=None),
        requirements,
        TODAY,
    )
    assert findings[0].severity == "watch"
    assert "no Flutter pin — set FVM or pubspec to 3.47.7" in findings[0].message


def test_loose_flutter_constraint_names_the_pin_target():
    requirements = {"flutter": {"recommended_stable": {"value": "3.47.7"}}}
    findings = compare_repo(
        _facts(flutter_pin=None, flutter_constraint=">=3.22.1"),
        requirements,
        TODAY,
    )
    assert findings[0].severity == "watch"
    assert "pin FVM or pubspec to 3.47.7" in findings[0].message


def test_ios_below_minimum_is_action():
    requirements = {"ios": {"min_deployment_target": {"value": "13.0"}}}
    findings = compare_repo(_facts(ios_deployment="12.0"), requirements, TODAY)
    assert findings[0].severity == "action"
    assert "12.0 is below minimum 13.0" in findings[0].message


def test_xcode_requirement_is_only_surfaced_before_its_deadline():
    soon = {"ios": {"min_xcode": {"value": "26", "deadline": "2026-11-01"}}}
    passed = {"ios": {"min_xcode": {"value": "26", "deadline": "2026-04-28"}}}
    upcoming = global_findings(soon, TODAY)
    assert upcoming and upcoming[0].severity == "action"
    assert "Xcode 26" in upcoming[0].message
    assert global_findings(passed, TODAY) == []


def test_dismissed_proposal_ids_are_not_added_again():
    quote = "Must target API level 36."
    dismissed = Proposal(
        id=proposal_id("play", quote),
        source_id="play",
        found_at="2026-10-01",
        quote=quote,
        snippet_url="https://example.test",
        suggested_field=None,
        suggested_value=None,
        status="dismissed",
    )
    fresh = Proposal(
        id=proposal_id("play", quote),
        source_id="play",
        found_at="2026-10-21",
        quote=quote,
        snippet_url="https://example.test",
        suggested_field="android.target_api_min",
        suggested_value="36",
        status="pending",
    )
    merged = merge_proposals([dismissed], [fresh])
    assert merged == [dismissed]
