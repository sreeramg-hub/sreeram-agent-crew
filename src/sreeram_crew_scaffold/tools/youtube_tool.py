import json
import pathlib
import re
import time
import xml.etree.ElementTree as ET
from typing import Literal, Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

STATE_DIR = pathlib.Path(__file__).parents[3] / "state"

NS_ATOM = "{http://www.w3.org/2005/Atom}"
NS_YT = "{http://www.youtube.com/xml/schemas/2015}"
NS_MEDIA = "{http://search.yahoo.com/mrss/}"
RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

FETCH_ATTEMPTS = 3

# Channels that could not be fetched during this run; main.py reads this for the health line.
FETCH_ERRORS: list[str] = []
DESCRIPTION_MAX_CHARS = 400


def _load_seen(metal: str) -> set:
    path = STATE_DIR / f"{metal}_seen.json"
    if path.exists():
        return set(json.loads(path.read_text()))
    return set()


def _save_seen(metal: str, seen: set) -> None:
    path = STATE_DIR / f"{metal}_seen.json"
    path.write_text(json.dumps(sorted(seen), indent=2))


def _fetch_feed(channel_id: str) -> ET.Element:
    """Fetch a channel's RSS feed, retrying briefly — YouTube's feed endpoint is occasionally flaky."""
    last_error = None
    for attempt in range(FETCH_ATTEMPTS):
        if attempt:
            time.sleep(2 * attempt)
        try:
            resp = requests.get(
                RSS_URL.format(channel_id=channel_id),
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            return ET.fromstring(resp.text)
        except Exception as e:
            last_error = e
    raise last_error


def _short_description(entry: ET.Element) -> str:
    """Channel-written description, flattened, with links removed and length capped."""
    el = entry.find(f"{NS_MEDIA}group/{NS_MEDIA}description")
    text = (el.text or "") if el is not None else ""
    text = re.sub(r"https?://\S+", "", text)
    text = " ".join(text.split())
    if len(text) > DESCRIPTION_MAX_CHARS:
        text = text[:DESCRIPTION_MAX_CHARS].rstrip() + "…"
    return text


class YoutubeNewUploadsInput(BaseModel):
    channel_ids: str = Field(
        ..., description="Comma-separated YouTube channel IDs to check for new uploads."
    )
    metal: Literal["gold", "silver"] = Field(
        ..., description="Which metal's seen-state to use: 'gold' or 'silver'."
    )


class YoutubeNewUploadsTool(BaseTool):
    name: str = "youtube_new_uploads"
    description: str = (
        "Checks a list of YouTube channels for videos not yet processed. "
        "Returns each new video's channel, title, published date, link and the "
        "channel-written description. Videos are not transcribed, so only the "
        "title and description are known. "
        "Inputs: comma-separated channel_ids, metal ('gold' or 'silver')."
    )
    args_schema: Type[BaseModel] = YoutubeNewUploadsInput

    def _run(self, channel_ids: str, metal: str) -> str:
        metal = metal.lower().strip()
        seen = _load_seen(metal)
        lines = []
        errors = []
        channel_names = []

        for channel_id in [c.strip() for c in channel_ids.split(",") if c.strip()]:
            try:
                root = _fetch_feed(channel_id)
            except Exception as e:
                errors.append(f"[ERROR fetching channel {channel_id}: {e}]")
                FETCH_ERRORS.append(channel_id)
                continue

            channel_title = getattr(root.find(f"{NS_ATOM}title"), "text", channel_id)
            channel_names.append(channel_title)

            for entry in root.findall(f"{NS_ATOM}entry"):
                vid_id_el = entry.find(f"{NS_YT}videoId")
                if vid_id_el is None:
                    continue
                vid_id = vid_id_el.text
                if vid_id in seen:
                    continue

                title = getattr(entry.find(f"{NS_ATOM}title"), "text", "Unknown title")
                published = getattr(entry.find(f"{NS_ATOM}published"), "text", "")[:10]
                description = _short_description(entry)

                lines.append(
                    f"- [{channel_title}] {published} | {title}\n"
                    f"  URL: https://www.youtube.com/watch?v={vid_id}\n"
                    f"  Description (written by the channel, unverified): "
                    f"{description or '(none provided)'}"
                )
                seen.add(vid_id)

        _save_seen(metal, seen)

        parts = []
        if lines:
            parts.append(f"NEW {metal} videos ({len(lines)}):\n" + "\n".join(lines))
        else:
            parts.append(
                f"No new {metal} videos. "
                f"Channels checked: {', '.join(channel_names) or 'none'}."
            )
        if errors:
            parts.append(
                "Some channels could not be checked this time — add one short neutral line saying so, with no advice:\n"
                + "\n".join(errors)
            )
        return "\n\n".join(parts)
