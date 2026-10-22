from vigil.report import overall_state, render_report, split_proposals


def _context(**overrides) -> dict:
    context = {
        "state": "ok",
        "state_label": "OK",
        "last_verified": "never",
        "action_count": 0,
        "pending_count": 0,
        "affects_apps": [],
        "worth_knowing": [],
        "errors": [],
        "todo_groups": [],
        "proposals": [],
        "drift": {"columns": [], "rows": []},
        "packages": [],
        "expiries": [],
        "fetches": [],
        "generated": "2026-10-21T08:00:00-06:00",
    }
    context.update(overrides)
    return context


def test_degraded_report_shows_the_failure_and_the_verified_date():
    html = render_report(
        _context(
            state="degraded",
            state_label="Degraded",
            last_verified="2026-09-01",
            errors=["Apple Upcoming Requirements: failed (HTTP 503)"],
            action_count=1,
            todo_groups=[
                {
                    "name": "Sample",
                    "priority": "high",
                    "lines": [
                        {
                            "severity": "action",
                            "message": "Sample: target SDK 34 is below Play minimum 35, due in 41 days",
                        }
                    ],
                }
            ],
        )
    )
    assert 'class="banner banner-degraded"' in html
    assert "Requirements last verified: 2026-09-01" in html
    assert "Apple Upcoming Requirements: failed (HTTP 503)" in html
    assert "target SDK 34 is below Play minimum 35, due in 41 days" in html
    assert "<script" not in html


def test_report_escapes_untrusted_source_text():
    html = render_report(_context(errors=["<b>boom</b>"]))
    assert "<b>boom</b>" not in html
    assert "&lt;b&gt;boom&lt;/b&gt;" in html


def test_overall_state_prefers_degraded_over_action():
    assert overall_state(["source down"], 3) == "degraded"
    assert overall_state([], 2) == "action"
    assert overall_state([], 0) == "ok"


def test_proposals_with_a_concrete_requirement_affect_apps():
    affects, awareness = split_proposals(
        [
            {
                "source_id": "play",
                "quote": "Target API level 36",
                "snippet_url": "https://example.test/play",
                "suggested_field": "android.target_api_min",
                "suggested_value": "36",
            },
            {
                "source_id": "apple-news",
                "quote": "Prepare apps for iPhone Duo",
                "snippet_url": "https://example.test/duo",
                "suggested_field": "ios.min_xcode",
                "suggested_value": None,
            },
            {
                "source_id": "apple-news",
                "quote": "License Agreement updated",
                "snippet_url": "https://example.test/license",
                "suggested_field": None,
                "suggested_value": None,
            },
        ]
    )
    assert [row["suggested_value"] for row in affects] == ["36"]
    assert len(awareness) == 2


def test_report_shows_affecting_proposals_and_collapses_the_rest():
    html = render_report(
        _context(
            action_count=2,
            affects_apps=[
                {
                    "source_id": "play-target-api",
                    "quote": "Apps must target API level 36",
                    "snippet_url": "https://example.test/play",
                    "suggested_field": "android.target_api_min",
                    "suggested_value": "36",
                }
            ],
            worth_knowing=[
                {
                    "source_id": "apple-news",
                    "quote": "Prepare and submit your apps for iPhone Duo",
                    "snippet_url": "https://example.test/duo",
                    "suggested_field": "ios.min_xcode",
                    "suggested_value": None,
                }
            ],
            todo_groups=[
                {
                    "name": "yetimatch",
                    "priority": "normal",
                    "lines": [
                        {"severity": "action", "message": "yetimatch: target SDK 34 is below Play minimum 36"},
                        {"severity": "action", "message": "yetimatch: Flutter pin is behind recommended stable"},
                    ],
                }
            ],
        )
    )
    assert "2 action items" in html
    assert "1 proposal that affects your apps" in html
    assert "1 other" in html
    assert "suggested: android.target_api_min = 36" in html
    assert "Apps must target API level 36" in html
    assert "<details class=\"awareness\">" in html
    assert "1 other proposal worth knowing" in html
    assert "iPhone Duo" in html
    assert "yetimatch: target SDK 34 is below Play minimum 36" in html
    assert "yetimatch: Flutter pin is behind recommended stable" in html
    assert "<script" not in html
