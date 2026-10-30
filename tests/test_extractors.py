from pathlib import Path

from vigil.config import Source
from vigil.extractors import KeywordExtractor

FIXTURES = Path(__file__).parent / "fixtures"


def test_keyword_extractor_returns_the_matching_paragraph():
    source = Source(
        id="play",
        name="Play",
        type="html",
        url="https://example.test/play",
        keywords=[],
    )
    text = (FIXTURES / "sources" / "added.txt").read_text(encoding="utf-8")
    found = KeywordExtractor().extract(text, source)
    assert len(found) == 1
    assert "API level 36" in found[0].quote
    assert "picnic" not in found[0].quote
    assert found[0].snippet_url == source.url
    assert found[0].suggested_field == "android.target_api_min"
    assert found[0].suggested_value == "36"


def test_entry_link_becomes_the_snippet_url():
    source = Source(id="feed", name="Feed", type="rss", url="https://example.test/rss", keywords=[])
    text = "Apps must be built with Xcode 26 before the deadline.\nLink: https://example.test/item"
    found = KeywordExtractor().extract(text, source)
    assert len(found) == 1
    assert found[0].snippet_url == "https://example.test/item"
    assert "Link:" not in found[0].quote
    assert found[0].suggested_field == "ios.min_xcode"
    assert found[0].suggested_value == "26"


def test_play_deadline_rows_suggest_api_and_deadline():
    source = Source(
        id="play-policy-deadlines",
        name="Google Play Policy Deadlines",
        type="html",
        url="https://support.google.com/googleplay/android-developer/table/12921780",
        keywords=["iso-deadline-row", "permission"],
    )
    text = (
        "2027-08-25: Local Network Permission: Apps targeting Android 17 or higher "
        "(API 37+) must submit a Play Console declaration to use this permission.\n\n"
        "We regularly update the Developer Program Policies for a trusted experience on Google Play.\n\n"
        "2027-01-27: Contacts Permissions policy: apps that need broad access must "
        "submit a Play Console declaration; others must use the Contact Picker."
    )
    found = KeywordExtractor().extract(text, source)
    assert len(found) == 2
    assert found[0].suggested_deadline == "2027-08-25"
    assert found[0].suggested_field == "android.target_api_min"
    assert found[0].suggested_value == "37"
    assert found[1].suggested_deadline == "2027-01-27"
    assert found[1].suggested_field is None
