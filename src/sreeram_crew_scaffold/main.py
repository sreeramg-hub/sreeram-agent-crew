#!/usr/bin/env python
import os
import pathlib
import sys
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

from sreeram_crew_scaffold.crew import SreeramCrewScaffold
from sreeram_crew_scaffold.tech import collect as tech_collect
from sreeram_crew_scaffold.tech.curate import CuratedSection, curate_section
from sreeram_crew_scaffold.tech.render import MetalsView, render_email
from sreeram_crew_scaffold.tools.email_tool import send_email
from sreeram_crew_scaffold.tools import youtube_tool
from sreeram_crew_scaffold.tools.price_tool import fetch_price

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

TIMEZONE = ZoneInfo("America/Chicago")
METALS_FILE = pathlib.Path("metals.html")
DIGEST_PREVIEW_FILE = pathlib.Path("digest.html")


def _crew_inputs(now: datetime) -> dict:
    return {
        "gold_channel_ids": os.getenv("GOLD_CHANNEL_IDS", ""),
        "silver_channel_ids": os.getenv("SILVER_CHANNEL_IDS", ""),
        "today_date": now.strftime("%B %d, %Y"),
    }


def _short(e: Exception) -> str:
    return f"{type(e).__name__}: {str(e)[:120]}"


def build_tech(now: datetime) -> tuple[list[CuratedSection], list[str], bool]:
    """Collect and curate the tech sections. Returns (sections, health lines, collected_ok)."""
    try:
        collection = tech_collect.collect(now)
    except Exception as e:
        failed = CuratedSection("tech", "Tech", [], "error", _short(e))
        return [failed], [f"Tech: collection failed ({_short(e)})"], False

    sections = [curate_section(s) for s in collection.sections]
    total = len(collection.sources)
    health = [f"Tech sources: {total - len(collection.failed_sources)}/{total} reachable"]
    if collection.failed_sources:
        health[0] += " (failed: " + ", ".join(
            f"{s.name} [{s.section}]" for s in collection.failed_sources
        ) + ")"
    health.append(
        "Curation: " + ", ".join(f"{s.title} {s.method}" for s in sections)
    )
    return sections, health, True


def build_metals(now: datetime) -> tuple[MetalsView, list[str]]:
    view = MetalsView()
    price_errors = []
    for metal in ("gold", "silver"):
        try:
            view.prices.append(fetch_price(metal))
        except Exception as e:
            price_errors.append(f"{metal} ({_short(e)})")
    view.price_error = "; ".join(price_errors)

    youtube_tool.FETCH_ERRORS.clear()
    try:
        METALS_FILE.unlink(missing_ok=True)
        SreeramCrewScaffold().crew().kickoff(inputs=_crew_inputs(now))
        fragment = METALS_FILE.read_text(encoding="utf-8").strip()
        if not fragment:
            raise RuntimeError("the crew produced no output")
        view.videos_html = fragment
    except Exception as e:
        view.videos_error = _short(e)

    if not view.videos_html:
        videos = f"failed ({view.videos_error})"
    elif youtube_tool.FETCH_ERRORS:
        videos = f"partial ({len(youtube_tool.FETCH_ERRORS)} channel fetch(es) failed)"
    else:
        videos = "ok"
    health = [f"Metals: prices {'ok' if not price_errors else 'failed'}, video list {videos}"]
    return view, health


def run():
    now = datetime.now(TIMEZONE)
    tech, tech_health, tech_ok = build_tech(now)
    metals, metals_health = build_metals(now)

    email_html = render_email(
        now=now,
        tech=tech,
        metals=metals,
        health=tech_health + metals_health + [f"Generated {now:%Y-%m-%d %H:%M %Z}"],
    )

    if os.getenv("DIGEST_DRY_RUN"):
        DIGEST_PREVIEW_FILE.write_text(email_html, encoding="utf-8")
        print(f"Dry run: wrote {DIGEST_PREVIEW_FILE}; nothing sent, tech state not updated.")
        return

    print(send_email(f"Daily Digest — {now:%B %-d, %Y}", email_html))

    # Remember what was emailed only after the email really went out, so a failed
    # run re-offers the same items tomorrow instead of silently dropping them.
    if tech_ok:
        tech_collect.save_seen(
            [p.item.url for section in tech for p in section.picks], now
        )


def train():
    now = datetime.now(TIMEZONE)
    try:
        SreeramCrewScaffold().crew().train(
            n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=_crew_inputs(now)
        )
    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def replay():
    try:
        SreeramCrewScaffold().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")


def test():
    now = datetime.now(TIMEZONE)
    try:
        SreeramCrewScaffold().crew().test(
            n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=_crew_inputs(now)
        )
    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")
