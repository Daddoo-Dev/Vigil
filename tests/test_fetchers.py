import httpx

from vigil.fetchers import fetch_source, html_to_paragraphs, json_paragraphs
from vigil.config import Source
from vigil.scanners.pubdev import PubDevClient, parse_pub_payload


def _source(kind: str = "html") -> Source:
    return Source(id="sample", name="Sample", type=kind, url="https://example.test/item", keywords=[])


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_http_error_is_a_failed_result_not_an_exception():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    result = fetch_source(_source(), _client(handler), sleeper=lambda _seconds: None)
    assert result.status == "failed"
    assert result.detail == "HTTP 404"
    assert result.paragraphs == []


def test_retries_then_succeeds_without_sleeping_in_the_test():
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503, text="busy")
        body = (
            '{"current_release":{"stable":"abc"},"releases":[{"channel":"stable",'
            '"version":"3.47.7","dart_sdk_version":"3.13.5","release_date":"2026-10-08"}]}'
        )
        return httpx.Response(200, text=body)

    slept: list[int] = []
    result = fetch_source(
        _source("json"),
        _client(handler),
        sleeper=lambda seconds: slept.append(seconds),
    )
    assert result.status == "ok"
    assert calls["count"] == 3
    assert slept == [1, 2]
    assert "3.47.7" in result.paragraphs[0]


def test_empty_html_is_unexpected():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body><p>Hi</p></body></html>")

    result = fetch_source(_source(), _client(handler), sleeper=lambda _seconds: None)
    assert result.status == "unexpected"
    assert result.paragraphs == []


def test_html_paragraphs_keep_requirement_text():
    html = """
    <html><body>
      <nav><p>Skip to content and other chrome that is long enough to notice.</p></nav>
      <main>
        <p>Starting August 31, 2026, new apps must target API level 36.</p>
      </main>
    </body></html>
    """
    paragraphs = html_to_paragraphs(html)
    assert len(paragraphs) == 1
    assert "API level 36" in paragraphs[0]


def test_html_table_rows_keep_deadline_with_policy_text():
    html = """
    <html><body><main>
      <table>
        <tr><th>Deadline (YYYY-MM-DD)</th><th>Policy change</th><th>Resources</th></tr>
        <tr>
          <td>2027-08-25</td>
          <td>Local Network Permission: Apps targeting Android 17 or higher (API 37+) must submit a Play Console declaration.</td>
          <td>PolicyBytes video</td>
        </tr>
        <tr>
          <td>2027-01-27</td>
          <td>Location Permissions policy requires the location button for infrequent precise location.</td>
          <td>Help Center</td>
        </tr>
      </table>
      <p>Intro text that is long enough to survive as its own paragraph after tables are removed.</p>
    </main></body></html>
    """
    paragraphs = html_to_paragraphs(html)
    assert paragraphs[0].startswith("2027-08-25: Local Network Permission")
    assert "API 37+" in paragraphs[0]
    assert paragraphs[1].startswith("2027-01-27: Location Permissions")
    assert any("Intro text" in item for item in paragraphs)


def test_flutter_json_ignores_artifact_hashes():
    body = """
    {"current_release":{"stable":"abc"},"releases":[
      {"hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","channel":"stable",
       "version":"3.47.7","dart_sdk_version":"3.13.5","release_date":"2026-10-08",
       "sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}
    ]}
    """
    paragraphs = json_paragraphs(body)
    assert paragraphs == ["Flutter SDK stable 3.47.7 (Dart SDK 3.13.5) released 2026-10-08."]


def test_pubdev_discontinued_and_retracted_payload():
    info = parse_pub_payload(
        "pedantic",
        {
            "name": "pedantic",
            "isDiscontinued": True,
            "replacedBy": "lints",
            "latest": {"version": "1.11.1"},
            "versions": [
                {"version": "1.11.1"},
                {"version": "1.10.0", "retracted": True},
            ],
        },
    )
    assert info is not None
    assert info.discontinued is True
    assert info.replaced_by == "lints"
    assert info.retracted == frozenset({"1.10.0"})


def test_pubdev_stops_on_rate_limit():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    client = PubDevClient(_client(handler), delay_seconds=5, sleeper=lambda _seconds: None)
    found, errors = client.lookup(["http", "path"])
    assert found == {}
    assert errors == ["pub.dev rate limit reached; remaining packages were not checked"]
