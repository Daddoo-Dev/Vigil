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
                    "action_count": 1,
                    "watch_count": 0,
                    "anchor": "sample",
                    "lines": [
                        {
                            "severity": "action",
                            "message": "Sample: target SDK 34 is below Play minimum 35, due in 41 days",
                            "text": "target SDK 34 is below Play minimum 35, due in 41 days",
                        }
                    ],
                }
            ],
        )
    )
    assert 'class="banner banner-degraded"' in html
    assert "Requirements verified" in html
    assert "2026-09-01" in html
    assert "Apple Upcoming Requirements: failed (HTTP 503)" in html
    assert "target SDK 34 is below Play minimum 35, due in 41 days" in html
    assert 'href="#sample"' in html
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
                    "name": "sample_app",
                    "priority": "normal",
                    "action_count": 2,
                    "watch_count": 0,
                    "anchor": "sample-app",
                    "lines": [
                        {
                            "severity": "action",
                            "message": "sample_app: target SDK 34 is below Play minimum 36",
                            "text": "target SDK 34 is below Play minimum 36",
                        },
                        {
                            "severity": "action",
                            "message": "sample_app: Flutter pin is behind recommended stable",
                            "text": "Flutter pin is behind recommended stable",
                        },
                    ],
                }
            ],
        )
    )
    assert ">Actions</span>2<" in html.replace("\n", "") or "Actions</span>2" in html
    assert "Affecting proposals" in html
    assert "Other proposals" in html
    assert "suggested: android.target_api_min = 36" in html
    assert "Apps must target API level 36" in html
    assert '<details class="proposals">' in html
    assert "collapsed" in html
    assert html.index("<h2>To-do</h2>") < html.index('<details class="proposals">')
    assert html.index("<h2>Drift</h2>") < html.index('<details class="proposals">')
    assert html.index("<h2>Package health</h2>") < html.index('<details class="proposals">')
    assert '<details class="awareness">' in html
    assert "1 other proposal worth knowing" in html
    assert "iPhone Duo" in html
    assert "target SDK 34 is below Play minimum 36" in html
    assert "Flutter pin is behind recommended stable" in html
    assert 'href="#sample-app"' in html
    assert "<script" not in html


def test_todo_groups_add_anchors_and_short_text():
    from vigil.report import todo_groups
    from vigil.requirements import Finding

    groups = todo_groups(
        [
            Finding("action", "PeekPersonalFinance: flutter_gemma is discontinued", "PeekPersonalFinance"),
            Finding("watch", "PeekPersonalFinance: cupertino_icons is a major behind", "PeekPersonalFinance"),
            Finding("watch", "alpha: no Flutter version pin", "alpha"),
        ]
    )
    assert groups[0]["name"] == "PeekPersonalFinance"
    assert groups[0]["action_count"] == 1
    assert groups[0]["watch_count"] == 1
    assert groups[0]["anchor"] == "peekpersonalfinance"
    assert groups[0]["lines"][0]["text"] == "flutter_gemma is discontinued"
    assert groups[1]["name"] == "alpha"
