import os
import re
import time
from typing import Literal, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

_FETCH_DELAY_SECONDS = float(os.getenv("TRANSCRIPT_FETCH_DELAY", "5"))
_MAX_RETRIES = int(os.getenv("TRANSCRIPT_MAX_RETRIES", "2"))
_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", "")


def _extract_video_id(url: str) -> str | None:
    for pattern in [r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})"]:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
        return url.strip()
    return None


class TranscribeVideoInput(BaseModel):
    video_url: str = Field(
        ..., description="YouTube video URL or video ID to transcribe."
    )
    metal: Optional[Literal["gold", "silver"]] = Field(
        None,
        description=(
            "Which metal this video belongs to ('gold' or 'silver'). "
            "Pass this so successful transcriptions are removed from the retry queue."
        ),
    )


class TranscribeVideoTool(BaseTool):
    name: str = "transcribe_video"
    description: str = (
        "Fetches the transcript of a YouTube video using auto-generated captions. "
        "Returns the full transcript as plain text, or TRANSCRIPT_UNAVAILABLE if "
        "captions are not ready yet. Always pass metal='gold' or metal='silver' "
        "so the retry queue stays accurate."
    )
    args_schema: Type[BaseModel] = TranscribeVideoInput

    def _run(self, video_url: str, metal: Optional[str] = None) -> str:
        # Import here to avoid circular import
        from sreeram_crew_scaffold.tools.youtube_tool import remove_from_pending

        video_id = _extract_video_id(video_url.strip())
        if not video_id:
            return f"Could not extract a video ID from: {video_url}"

        kwargs = {}
        if _COOKIES_FILE and os.path.exists(_COOKIES_FILE):
            kwargs["cookies"] = _COOKIES_FILE

        last_error = None
        for attempt in range(_MAX_RETRIES):
            if attempt > 0:
                wait = _FETCH_DELAY_SECONDS * (2 ** attempt)
                time.sleep(wait)
            else:
                time.sleep(_FETCH_DELAY_SECONDS)

            try:
                api = YouTubeTranscriptApi(**kwargs)
                transcript_list = api.list(video_id)
                try:
                    transcript = transcript_list.find_manually_created_transcript(["en"])
                except Exception:
                    transcript = transcript_list.find_generated_transcript(["en"])
                snippets = transcript.fetch()
                full_text = " ".join(s.text for s in snippets)
                word_count = len(full_text.split())

                # Success — remove from pending retry queue
                if metal:
                    remove_from_pending(metal.lower(), video_id)

                return f"[Transcript — {word_count} words]\n\n{full_text}"

            except TranscriptsDisabled:
                return f"TRANSCRIPT_UNAVAILABLE: Transcripts are disabled for video {video_id}."
            except NoTranscriptFound:
                return (
                    f"TRANSCRIPT_UNAVAILABLE: No captions found for video {video_id}. "
                    "The video was likely published recently — will retry next run."
                )
            except Exception as e:
                last_error = e
                continue

        return (
            f"TRANSCRIPT_UNAVAILABLE: Could not fetch transcript for {video_id} "
            f"after {_MAX_RETRIES} attempts ({last_error}). Will retry next run."
        )
