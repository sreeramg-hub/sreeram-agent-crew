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
        "Returns new video IDs, titles, URLs, and published dates. "
        "Updates the seen-state so the same video is never returned twice. "
        "Inputs: comma-separated channel_ids, metal ('gold' or 'silver')."
    )
    args_schema: Type[BaseModel] = YoutubeNewUploadsInput

    def _run(self, channel_ids: str, metal: str) -> str:
        metal = metal.lower().strip()
        seen = _load_seen(metal)
        new_videos = []

        for channel_id in [c.strip() for c in channel_ids.split(",") if c.strip()]:
            url = RSS_URL.format(channel_id=channel_id)
            try:
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
            except Exception as e:
                new_videos.append(f"[ERROR fetching channel {channel_id}: {e}]")
                continue

            channel_title = getattr(root.find(f"{NS_ATOM}title"), "text", channel_id)

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

                new_videos.append(
                    f"- [{channel_title}] {published} | {title}\n  URL: {video_url}\n  ID: {vid_id}"
                )
                seen.add(vid_id)

        _save_seen(metal, seen)

        if not new_videos:
            return f"No new {metal} videos found across {len(channel_ids.split(','))} channel(s)."

        header = f"Found {len(new_videos)} new video(s) for {metal}:\n"
        return header + "\n".join(new_videos)
