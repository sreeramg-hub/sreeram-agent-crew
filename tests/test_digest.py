import json
import pathlib
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import pytest

from sreeram_crew_scaffold.tech import collect as C
from sreeram_crew_scaffold.tech.curate import curate_section
from sreeram_crew_scaffold.tech.render import (
    DISCLAIMER,
    MetalsView,
    render_email,
    sanitize_fragment,
)

NOW = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)

RSS = b"""<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Fresh post</title><link>https://a.example/post?utm_source=x</link>
  <pubDate>Sat, 19 Sep 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;</description></item>
<item><title>No date</title><link>https://a.example/nodate</link></item>
<item><title>Old</title><link>https://a.example/old</link><pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom entry</title><link rel="self" href="https://b.example/feed"/>
  <link rel="alternate" href="https://b.example/entry"/><updated>2026-09-19T08:30:00Z</updated>
  <summary>Short summary</summary></entry></feed>"""


def item(section="ai", source="S", title="T", url="https://x.example/1", hours_ago=5, **kw):
    return C.Item(section, source, title, url, NOW - timedelta(hours=hours_ago), **kw)


# ── collect ───────────────────────────────────────────────────────────────────

def test_canonical_url_strips_tracking_and_trailing_slash():
    assert C.canonical_url("HTTPS://A.example/post/?utm_source=x&id=3#frag") == "https://a.example/post?id=3"


def test_parse_rss_skips_entries_without_date_and_cleans_summary():
    items = C.parse_feed(RSS, "ai", "Blog")
    assert [i.title for i in items] == ["Fresh post", "Old"]
    assert items[0].summary == "Hello & welcome"


def test_parse_atom_prefers_alternate_link():
    (entry,) = C.parse_feed(ATOM, "ui", "Atom")
    assert entry.url == "https://b.example/entry"
    assert entry.published == datetime(2026, 9, 19, 8, 30, tzinfo=timezone.utc)


def _config(tmp_path, body):
    path = tmp_path / "sources.yaml"
    path.write_text(body)
    return path


CONFIG = """
window_hours: 48
max_per_source: 2
sections:
  - {key: ai, title: AI, pick: 3, sources: [{name: A, type: feed, url: "http://a"}, {name: B, type: feed, url: "http://b"}]}
  - {key: ui, title: UI, pick: 2, window_hours: 400, sources: [{name: C, type: feed, url: "http://c"}]}
"""


def fake_fetch(src, section):
    return {
        "A": [item(section, "A", "a-new", "https://x.example/shared"), item(section, "A", "a-old", "https://x.example/a-old", hours_ago=100)],
        "B": [item(section, "B", "b-dup", "https://x.example/shared/?utm_medium=y"), item(section, "B", "b-seen", "https://x.example/seen")],
        "C": [item(section, "C", "c-slow", "https://x.example/c", hours_ago=300)],
    }[src["name"]]


def test_collect_applies_windows_dedup_seen_and_ids(tmp_path):
    seen = {C.canonical_url("https://x.example/seen"): "2026-09-19"}
    with mock.patch.object(C, "fetch_source", side_effect=fake_fetch):
        result = C.collect(NOW, seen=seen, sources_file=_config(tmp_path, CONFIG))
    ai, ui = result.sections
    assert [i.title for i in ai.items] == ["a-new"]          # a-old outside window, b-dup is a duplicate, b-seen already sent
    assert [i.id for i in ai.items] == ["ai-1"]
    assert [i.title for i in ui.items] == ["c-slow"]          # section window (400h) keeps the slow blog
    assert not result.failed_sources


def test_collect_reports_failed_source_but_keeps_going(tmp_path):
    def flaky(src, section):
        if src["name"] == "A":
            raise ConnectionError("boom")
        return fake_fetch(src, section)

    with mock.patch.object(C, "fetch_source", side_effect=flaky):
        result = C.collect(NOW, seen={}, sources_file=_config(tmp_path, CONFIG))
    assert [f.name for f in result.failed_sources] == ["A"]
    assert result.sections[0].items  # B's items still there


def test_seen_state_round_trip_and_pruning(tmp_path):
    path = tmp_path / "tech_seen.json"
    path.write_text(json.dumps({"https://old.example/x": "2026-01-01"}))
    C.save_seen(["https://new.example/y/?utm_source=z"], NOW, path)
    assert json.loads(path.read_text()) == {"https://new.example/y": "2026-09-20"}


# ── curate ───────────────────────────────────────────────────────────────────

def section(n=4, pick=2):
    items = [item(title=f"t{i}", url=f"https://x.example/{i}") for i in range(1, n + 1)]
    for i, it in enumerate(items, 1):
        it.id = f"ai-{i}"
    return C.SectionCandidates("ai", "AI", pick, items)


def client_returning(picks):
    block = SimpleNamespace(type="tool_use", input={"picks": picks})
    client = mock.Mock()
    client.messages.create.return_value = SimpleNamespace(content=[block])
    return client


def test_curate_maps_ids_to_real_items_and_ignores_invented_ones():
    client = client_returning([
        {"id": "ai-3", "blurb": "Third   one."},
        {"id": "ai-99", "blurb": "invented"},
        {"id": "ai-3", "blurb": "repeat"},
        {"id": "ai-1", "blurb": "First."},
        {"id": "ai-2", "blurb": "over the limit"},
    ])
    result = curate_section(section(), client)
    assert result.method == "claude"
    assert [p.item.url for p in result.picks] == ["https://x.example/3", "https://x.example/1"]
    assert result.picks[0].blurb == "Third one."


def test_curate_falls_back_when_api_fails():
    client = mock.Mock()
    client.messages.create.side_effect = RuntimeError("api down")
    result = curate_section(section(), client)
    assert result.method == "fallback" and len(result.picks) == 2 and "RuntimeError" in result.note


def test_curate_falls_back_when_no_pick_is_usable():
    result = curate_section(section(), client_returning([{"id": "nope", "blurb": "x"}]))
    assert result.method == "fallback"


def test_curate_empty_section_makes_no_api_call():
    client = mock.Mock()
    result = curate_section(C.SectionCandidates("ai", "AI", 3, []), client)
    assert result.method == "empty" and not client.messages.create.called


# ── render ───────────────────────────────────────────────────────────────────

def curated(picks, method="claude", note=""):
    from sreeram_crew_scaffold.tech.curate import CuratedSection, Pick

    return CuratedSection("ai", "AI", [Pick(i, b) for i, b in picks], method, note)


def test_render_escapes_feed_text_and_neutralises_bad_links():
    evil = item(title='<script>alert(1)</script> & "quotes"', url="javascript:alert(1)", source="<b>S</b>")
    page = render_email(
        now=NOW, tech=[curated([(evil, '<img src=x onerror=alert(1)>')])],
        metals=MetalsView(), health=[],
    )
    assert "<script>" not in page and "<img" not in page and "javascript:" not in page
    assert "&lt;script&gt;" in page


def test_render_always_has_disclaimer_and_metals_placeholders():
    page = render_email(now=NOW, tech=[curated([])], metals=MetalsView(videos_error="crew failed"), health=["Tech sources: 1/1"])
    assert DISCLAIMER.split(",")[0] in page
    assert "Nothing new since the last digest." in page
    assert "Video links unavailable today: crew failed" in page
    assert "Tech sources: 1/1" in page


def test_render_puts_tech_before_metals():
    page = render_email(now=NOW, tech=[curated([(item(title="Story"), "")])], metals=MetalsView(), health=[])
    assert page.index("Story") < page.index("Gold &amp; Silver")


def test_render_error_section_and_price_strip():
    from sreeram_crew_scaffold.tech.curate import CuratedSection

    quote = {"metal": "gold", "price": 3456.789, "prev_close": 3400.0, "pct_change": 1.67}
    page = render_email(
        now=NOW, tech=[CuratedSection("tech", "Tech", [], "error", "ValueError: bad")],
        metals=MetalsView(prices=[quote]), health=[],
    )
    assert "Unavailable today: ValueError: bad" in page
    assert "$3,456.79" in page and "Gold futures" in page


def test_sanitizer_keeps_safe_markup_and_drops_the_rest():
    dirty = ('<h3>Gold</h3><ul><li><a href="https://y.example/v">Vid</a> — ok</li></ul>'
             '<script>steal()</script><a href="javascript:evil()">bad</a><iframe src="x">z</iframe><p onclick="x()">hi</p>')
    clean = sanitize_fragment(dirty)
    assert 'href="https://y.example/v"' in clean and "<h3>Gold</h3>" in clean
    assert "steal" not in clean and "javascript:" not in clean and "iframe" not in clean and "onclick" not in clean


# ── youtube tool ─────────────────────────────────────────────────────────────

YT_FEED = """<?xml version="1.0"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
<title>Chan</title>
<entry><yt:videoId>AAAAAAAAAAA</yt:videoId><title>New</title><published>2026-09-18T12:00:00+00:00</published>
<media:group><media:description>Up. See https://spam.example/x now</media:description></media:group></entry>
<entry><yt:videoId>BBBBBBBBBBB</yt:videoId><title>Seen</title><published>2026-09-17T12:00:00+00:00</published></entry>
</feed>"""


def test_youtube_tool_lists_new_videos_with_clean_descriptions_and_saves_state(tmp_path):
    from sreeram_crew_scaffold.tools import youtube_tool as yt

    (tmp_path / "gold_seen.json").write_text('["BBBBBBBBBBB"]')
    response = mock.Mock(text=YT_FEED, raise_for_status=lambda: None)
    with mock.patch.object(yt, "STATE_DIR", tmp_path), mock.patch.object(yt.requests, "get", return_value=response):
        out = yt.YoutubeNewUploadsTool()._run("UCx", "gold")
        again = yt.YoutubeNewUploadsTool()._run("UCx", "gold")
    assert "NEW gold videos (1)" in out and "watch?v=AAAAAAAAAAA" in out and "spam.example" not in out
    assert again.startswith("No new gold videos")


def test_youtube_tool_reports_unreachable_channel_without_counting_it(tmp_path):
    from sreeram_crew_scaffold.tools import youtube_tool as yt

    with mock.patch.object(yt, "STATE_DIR", tmp_path), mock.patch.object(yt.requests, "get", side_effect=RuntimeError("404")), mock.patch.object(yt.time, "sleep"):
        out = yt.YoutubeNewUploadsTool()._run("UCbad", "gold")
    assert "No new gold videos" in out and "could not be checked" in out
    assert yt.FETCH_ERRORS == ["UCbad"]
    yt.FETCH_ERRORS.clear()
