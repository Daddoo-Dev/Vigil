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
