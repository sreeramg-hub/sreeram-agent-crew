import json
import pathlib
import xml.etree.ElementTree as ET
from typing import Literal, Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

STATE_DIR = pathlib.Path(__file__).parents[3] / "state"

NS_ATOM = "{http://www.w3.org/2005/Atom}"
NS_YT = "{http://www.youtube.com/xml/schemas/2015}"
RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def _load_seen(metal: str) -> set:
    path = STATE_DIR / f"{metal}_seen.json"
    if path.exists():
        return set(json.loads(path.read_text()))
    return set()


def _save_seen(metal: str, seen: set) -> None:
    path = STATE_DIR / f"{metal}_seen.json"
    path.write_text(json.dumps(sorted(seen), indent=2))


def load_pending(metal: str) -> dict:
    """Returns {video_id: {title, url, channel, date, attempts}} for videos awaiting transcription."""
    path = STATE_DIR / f"{metal}_pending.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_pending(metal: str, pending: dict) -> None:
    path = STATE_DIR / f"{metal}_pending.json"
    path.write_text(json.dumps(pending, indent=2))


def remove_from_pending(metal: str, video_id: str) -> None:
    pending = load_pending(metal)
    if video_id in pending:
        del pending[video_id]
        save_pending(metal, pending)


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
        "Checks a list of YouTube channels for videos not yet processed, "
        "and also returns any videos from previous runs where transcription failed. "
        "Returns video titles, URLs, published dates, and whether each is new or a retry. "
        "Inputs: comma-separated channel_ids, metal ('gold' or 'silver')."
    )
    args_schema: Type[BaseModel] = YoutubeNewUploadsInput

    def _run(self, channel_ids: str, metal: str) -> str:
        metal = metal.lower().strip()
        seen = _load_seen(metal)
        pending = load_pending(metal)
        lines = []
        channel_names = []

        # --- New videos from RSS ---
        for channel_id in [c.strip() for c in channel_ids.split(",") if c.strip()]:
            url = RSS_URL.format(channel_id=channel_id)
            try:
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
            except Exception as e:
                channel_names.append(channel_id)
                lines.append(f"[ERROR fetching channel {channel_id}: {e}]")
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
                video_url = f"https://www.youtube.com/watch?v={vid_id}"

                lines.append(
                    f"- [NEW] [{channel_title}] {published} | {title}\n"
                    f"  URL: {video_url}\n  ID: {vid_id}"
                )
                seen.add(vid_id)
                # Add to pending — transcribe_video removes it on success
                pending[vid_id] = {
                    "title": title,
                    "url": video_url,
                    "channel": channel_title,
                    "date": published,
                    "attempts": 0,
                }

        _save_seen(metal, seen)

        # --- Pending retries from previous runs ---
        retry_lines = []
        for vid_id, meta in pending.items():
            retry_lines.append(
                f"- [RETRY — transcript failed previously] [{meta['channel']}] "
                f"{meta['date']} | {meta['title']}\n"
                f"  URL: {meta['url']}\n  ID: {vid_id}"
            )
            pending[vid_id]["attempts"] = meta.get("attempts", 0) + 1

        save_pending(metal, pending)

        if not lines and not retry_lines:
            names = ", ".join(channel_names)
            return f"No new {metal} videos and no pending retries. Channels checked: {names}."

        result = []
        if lines:
            result.append(f"NEW videos ({len(lines)}):\n" + "\n".join(lines))
        if retry_lines:
            result.append(
                f"RETRY videos — transcription failed on a previous run ({len(retry_lines)}):\n"
                + "\n".join(retry_lines)
            )
        return "\n\n".join(result)
