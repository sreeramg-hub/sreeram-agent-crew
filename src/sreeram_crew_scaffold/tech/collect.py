"""Collect recent tech items from RSS/Atom feeds and two JSON APIs. No LLM in here."""
from __future__ import annotations

import html
import json
import pathlib
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
import yaml

PACKAGE_DIR = pathlib.Path(__file__).parents[1]
SOURCES_FILE = PACKAGE_DIR / "config" / "tech_sources.yaml"
SEEN_FILE = pathlib.Path(__file__).parents[3] / "state" / "tech_seen.json"

USER_AGENT = "Mozilla/5.0 (compatible; sreeram-agent-crew daily digest)"
FETCH_ATTEMPTS = 2
SEEN_RETENTION_DAYS = 30
SUMMARY_MAX_CHARS = 500


@dataclass
class Item:
    section: str
    source: str
    title: str
    url: str
    published: datetime
    summary: str = ""
    points: int | None = None
    discuss_url: str | None = None
    id: str = ""


@dataclass
class SourceResult:
    section: str
    name: str
    items: list[Item] = field(default_factory=list)
    error: str | None = None


@dataclass
class SectionCandidates:
    key: str
    title: str
    pick: int
    items: list[Item]


@dataclass
class Collection:
    sections: list[SectionCandidates]
    sources: list[SourceResult]

    @property
    def failed_sources(self) -> list[SourceResult]:
        return [s for s in self.sources if s.error]


# ── small helpers ─────────────────────────────────────────────────────────────

_TRACKING_PARAM = re.compile(r"^(utm_|mc_|ref$|ref_src$|fbclid$|gclid$)")


def canonical_url(url: str) -> str:
    """Normalise a URL so the same article from two sources dedupes."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAM.match(k)]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def clean_text(raw: str, limit: int = SUMMARY_MAX_CHARS) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = " ".join(html.unescape(text).split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def parse_date(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        dt = None
    if dt is None:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, *names: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def _text(el: ET.Element | None) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _entry_link(entry: ET.Element) -> str:
    fallback = ""
    for c in entry:
        if _local(c.tag) != "link":
            continue
        href = c.get("href")
        if href:  # Atom
            if c.get("rel", "alternate") == "alternate":
                return href.strip()
            fallback = fallback or href.strip()
        elif (c.text or "").strip():  # RSS
            return c.text.strip()
    return fallback


# ── source parsers ────────────────────────────────────────────────────────────

def parse_feed(content: bytes, section: str, source: str) -> list[Item]:
    """Parse an RSS 2.0 or Atom document into Items. Entries missing a title, link or date are skipped."""
    root = ET.fromstring(content)
    items = []
    for entry in root.iter():
        if _local(entry.tag) not in ("item", "entry"):
            continue
        title = clean_text(_text(_child(entry, "title")), 300)
        url = _entry_link(entry)
        published = parse_date(
            _text(_child(entry, "pubDate", "published", "updated", "date"))
        )
        if not (title and url.startswith(("http://", "https://")) and published):
            continue
        summary = clean_text(_text(_child(entry, "description", "summary", "encoded", "content")))
        items.append(Item(section, source, title, url, published, summary))
    return items


def _get(url: str, **kwargs) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(FETCH_ATTEMPTS):
        if attempt:
            time.sleep(2)
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT}, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as e:  # network errors, HTTP errors
            last_error = e
    raise last_error  # type: ignore[misc]


def fetch_hn(src: dict, section: str) -> list[Item]:
    resp = _get(
        "https://hn.algolia.com/api/v1/search",
        params={"tags": "front_page", "hitsPerPage": 100},
    )
    keywords = re.compile(src["keywords"], re.I) if src.get("keywords") else None
    min_points = src.get("min_points", 0)
    items = []
    for hit in resp.json().get("hits", []):
        title, points = hit.get("title") or "", hit.get("points") or 0
        if not title or points < min_points or (keywords and not keywords.search(title)):
            continue
        discuss = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        items.append(
            Item(
                section,
                src["name"],
                title,
                hit.get("url") or discuss,
                datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc),
                points=points,
                discuss_url=discuss,
            )
        )
    return sorted(items, key=lambda i: i.points or 0, reverse=True)


def fetch_hf_papers(src: dict, section: str) -> list[Item]:
    resp = _get("https://huggingface.co/api/daily_papers")
    min_upvotes = src.get("min_upvotes", 0)
    items = []
    for entry in resp.json():
        paper = entry.get("paper", {})
        published = parse_date(entry.get("publishedAt") or paper.get("publishedAt") or "")
        upvotes = paper.get("upvotes") or 0
        title = entry.get("title") or paper.get("title")
        if not (paper.get("id") and title and published) or upvotes < min_upvotes:
            continue
        items.append(
            Item(
                section,
                src["name"],
                clean_text(title, 300),
                f"https://huggingface.co/papers/{paper['id']}",
                published,
                clean_text(entry.get("summary") or paper.get("summary") or ""),
                points=upvotes,
            )
        )
    return sorted(items, key=lambda i: i.points or 0, reverse=True)


def fetch_source(src: dict, section: str) -> list[Item]:
    kind = src.get("type", "feed")
    if kind == "hn":
        return fetch_hn(src, section)
    if kind == "hf_papers":
        return fetch_hf_papers(src, section)
    if kind == "feed":
        return parse_feed(_get(src["url"]).content, section, src["name"])
    raise ValueError(f"unknown source type: {kind}")


# ── seen-state ────────────────────────────────────────────────────────────────

def load_seen(path: pathlib.Path = SEEN_FILE) -> dict[str, str]:
    """{canonical_url: ISO date it was emailed}."""
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_seen(new_urls: list[str], now: datetime, path: pathlib.Path = SEEN_FILE) -> None:
    seen = load_seen(path)
    seen.update({canonical_url(u): now.date().isoformat() for u in new_urls})
    cutoff = (now - timedelta(days=SEEN_RETENTION_DAYS)).date().isoformat()
    seen = {u: d for u, d in seen.items() if d >= cutoff}
    path.write_text(json.dumps(dict(sorted(seen.items())), indent=2))


# ── entry point ───────────────────────────────────────────────────────────────

def collect(
    now: datetime,
    seen: dict[str, str] | None = None,
    sources_file: pathlib.Path = SOURCES_FILE,
) -> Collection:
    config = yaml.safe_load(sources_file.read_text())
    seen = load_seen() if seen is None else seen
    default_window = config.get("window_hours", 72)
    per_source = config.get("max_per_source", 5)
    max_candidates = config.get("max_candidates", 40)

    jobs = [(sec, src) for sec in config["sections"] for src in sec["sources"]]

    def run(job: tuple[dict, dict]) -> SourceResult:
        sec, src = job
        result = SourceResult(sec["key"], src["name"])
        try:
            fetched = fetch_source(src, sec["key"])
            hours = src.get("window_hours", sec.get("window_hours", default_window))
            cutoff = now - timedelta(hours=hours)
            recent = [i for i in fetched if i.published >= cutoff]
            result.items = sorted(recent, key=lambda i: i.published, reverse=True)[:per_source]
        except Exception as e:
            result.error = f"{type(e).__name__}: {str(e)[:100]}"
        return result

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, jobs))

    claimed: set[str] = set()  # a story belongs to the first section that has it
    sections = []
    for sec in config["sections"]:
        items: list[Item] = []
        for r in (r for r in results if r.section == sec["key"]):
            for item in r.items:
                key = canonical_url(item.url)
                if key in seen or key in claimed:
                    continue
                claimed.add(key)
                items.append(item)
        items.sort(key=lambda i: i.published, reverse=True)
        items = items[:max_candidates]
        for n, item in enumerate(items, 1):
            item.id = f"{sec['key']}-{n}"
        sections.append(SectionCandidates(sec["key"], sec["title"], sec["pick"], items))

    return Collection(sections, results)
