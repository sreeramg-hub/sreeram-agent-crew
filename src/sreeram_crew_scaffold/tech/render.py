"""Render the daily digest email: tech sections first, then gold & silver.

Everything that reaches the HTML is escaped here, and the one piece of
LLM-written HTML (the metals video list) is passed through a tag whitelist.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser

from sreeram_crew_scaffold.tech.curate import CuratedSection

DISCLAIMER = (
    "This digest is compiled from public sources for personal research only. "
    "Links point to third-party content that has not been reviewed here, and "
    "nothing in this email is financial advice."
)

# Palette: light theme only — email clients disagree on dark mode, so we stay readable everywhere.
INK, MUTED, LINK, RULE, BAND = "#111827", "#6b7280", "#1d4ed8", "#e5e7eb", "#0f172a"
UP, DOWN = "#15803d", "#b91c1c"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


@dataclass
class MetalsView:
    prices: list[dict] = field(default_factory=list)  # from tools.price_tool.fetch_price
    price_error: str = ""
    videos_html: str = ""  # LLM-written fragment; sanitised on render
    videos_error: str = ""


# ── sanitising the LLM-written fragment ───────────────────────────────────────

_ALLOWED = {"p", "ul", "ol", "li", "a", "strong", "em", "b", "i", "br", "h3", "h4"}
_DROP_CONTENT = {"script", "style", "iframe", "object"}


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_CONTENT:
            self._skip += 1
        elif not self._skip and tag in _ALLOWED:
            if tag == "a":
                href = dict(attrs).get("href") or ""
                if href.startswith(("http://", "https://")):
                    self.out.append(f'<a href="{html.escape(href, quote=True)}" style="color:{LINK}">')
                else:
                    self.out.append("<a>")
            elif tag == "br":
                self.out.append("<br>")
            else:
                self.out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in _DROP_CONTENT:
            self._skip = max(0, self._skip - 1)
        elif not self._skip and tag in _ALLOWED and tag != "br":
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(html.escape(data))


def sanitize_fragment(fragment: str) -> str:
    parser = _Sanitizer()
    parser.feed(fragment)
    parser.close()
    return "".join(parser.out)


# ── building blocks ───────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _url(url: str) -> str:
    """Escaped href; anything that is not http(s) is neutralised."""
    return _esc(url) if url.startswith(("http://", "https://")) else "#"


def _section_heading(label: str) -> str:
    return (
        f'<h2 style="margin:32px 0 14px;padding-bottom:8px;border-bottom:2px solid {INK};'
        f'font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:{INK}">{_esc(label)}</h2>'
    )


def _muted(text: str) -> str:
    return f'<p style="margin:0 0 12px;font-size:14px;color:{MUTED}">{_esc(text)}</p>'


def _render_pick(pick) -> str:
    item = pick.item
    meta = [_esc(item.source), f"{item.published:%b %-d}"]
    if item.points is not None:
        meta.append(f"▲ {item.points}")
    if item.discuss_url and item.discuss_url != item.url:
        meta.append(f'<a href="{_url(item.discuss_url)}" style="color:{MUTED}">discussion</a>')
    blurb = (
        f'<div style="margin-top:4px;font-size:15px;line-height:1.5;color:#374151">{_esc(pick.blurb)}</div>'
        if pick.blurb
        else ""
    )
    return (
        '<div style="margin:0 0 18px">'
        f'<a href="{_url(item.url)}" style="font-size:17px;line-height:1.35;font-weight:600;'
        f'color:{LINK};text-decoration:none">{_esc(item.title)}</a>'
        f'<div style="margin-top:3px;font-size:13px;color:{MUTED}">{" · ".join(meta)}</div>'
        f"{blurb}</div>"
    )


def _render_tech_section(section: CuratedSection) -> str:
    parts = [_section_heading(section.title)]
    if section.method == "error":
        return "".join(parts) + _muted(f"Unavailable today: {section.note}")
    if section.picks:
        parts += [_render_pick(p) for p in section.picks]
    else:
        parts.append(_muted("Nothing new since the last digest."))
    if section.method == "fallback" and section.note:
        parts.append(_muted(section.note))
    return "".join(parts)


def _render_price(quote: dict) -> str:
    label = quote["metal"].capitalize()
    pct = quote["pct_change"]
    if pct is None:
        change, color = "change unavailable", MUTED
    else:
        arrow, color = ("▲", UP) if pct >= 0 else ("▼", DOWN)
        change = f"{arrow} {abs(pct):.2f}%"
    return (
        f'<td style="width:50%;padding:12px 14px;border:1px solid {RULE};border-radius:6px" valign="top">'
        f'<div style="font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.06em">{label} futures</div>'
        f'<div style="font-size:22px;font-weight:700;color:{INK}">${quote["price"]:,.2f}</div>'
        f'<div style="font-size:14px;color:{color}">{change}</div></td>'
    )


def _render_metals(metals: MetalsView) -> str:
    parts = [_section_heading("Gold & Silver")]
    if metals.prices:
        cells = '<td style="width:12px"></td>'.join(_render_price(q) for q in metals.prices)
        parts.append(f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>{cells}</tr></table>')
    if metals.price_error:
        parts.append(_muted(f"Prices unavailable: {metals.price_error}"))
    parts.append('<div style="margin-top:16px;font-size:15px;line-height:1.5;color:#374151">')
    if metals.videos_html:
        parts.append(sanitize_fragment(metals.videos_html))
    else:
        parts.append(_muted(f"Video links unavailable today: {metals.videos_error or 'no data'}"))
    parts.append("</div>")
    return "".join(parts)


def render_email(
    *,
    now: datetime,
    tech: list[CuratedSection],
    metals: MetalsView,
    health: list[str],
) -> str:
    shown = sum(len(s.picks) for s in tech)
    tagline = f"{shown} tech links · gold &amp; silver"
    body = "".join(_render_tech_section(s) for s in tech) + _render_metals(metals)
    health_html = "<br>".join(_esc(line) for line in health)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily Digest — {now:%B %-d, %Y}</title></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:{FONT};color:{INK}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6"><tr><td align="center" style="padding:16px 8px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#ffffff;border-radius:8px;overflow:hidden">
<tr><td style="background:{BAND};padding:22px 24px;color:#ffffff">
<div style="font-size:22px;font-weight:700">Daily Digest</div>
<div style="margin-top:4px;font-size:14px;color:#cbd5e1">{now:%A, %B %-d, %Y} · {tagline}</div>
</td></tr>
<tr><td style="padding:4px 24px 24px">{body}</td></tr>
<tr><td style="padding:16px 24px 24px;border-top:1px solid {RULE};font-size:12px;line-height:1.5;color:{MUTED}">
<p style="margin:0 0 10px">{_esc(DISCLAIMER)}</p>
<p style="margin:0">{health_html}</p>
</td></tr>
</table></td></tr></table>
</body></html>"""
