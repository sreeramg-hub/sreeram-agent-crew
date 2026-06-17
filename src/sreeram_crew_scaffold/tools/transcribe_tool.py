import os
import re
import time
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

# Seconds to wait between transcript fetches to avoid YouTube rate-limiting.
# Increase if you're processing many videos in one run.
_FETCH_DELAY_SECONDS = float(os.getenv("TRANSCRIPT_FETCH_DELAY", "5"))

# Number of times to retry a blocked request before giving up.
_MAX_RETRIES = int(os.getenv("TRANSCRIPT_MAX_RETRIES", "2"))

# Optional: path to a Netscape-format cookies.txt file exported from your browser.
# Required when running on cloud IPs (GitHub Actions) that YouTube blocks by default.
# Export using the "Get cookies.txt LOCALLY" browser extension, save as cookies.txt
# in the repo root, then set YOUTUBE_COOKIES_FILE=cookies.txt in your .env.
# Add cookies.txt to .gitignore — never commit it.
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


class TranscribeVideoTool(BaseTool):
    name: str = "transcribe_video"
    description: str = (
        "Fetches the transcript of a YouTube video using auto-generated captions. "
        "Returns the full transcript as plain text. "
        "Input: a YouTube video URL or video ID."
    )
    args_schema: Type[BaseModel] = TranscribeVideoInput

    def _run(self, video_url: str) -> str:
        video_id = _extract_video_id(video_url.strip())
        if not video_id:
            return f"Could not extract a video ID from: {video_url}"

        kwargs = {}
        if _COOKIES_FILE and os.path.exists(_COOKIES_FILE):
            kwargs["cookies"] = _COOKIES_FILE

        last_error = None
        for attempt in range(_MAX_RETRIES):
            if attempt > 0:
                wait = _FETCH_DELAY_SECONDS * (2 ** attempt)  # exponential backoff
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
                return f"[Transcript — {word_count} words]\n\n{full_text}"

            except TranscriptsDisabled:
                return f"Transcripts are disabled for video {video_id}."
            except NoTranscriptFound:
                return (
                    f"No English transcript found for video {video_id}. "
                    "The video may not have captions yet."
                )
            except Exception as e:
                last_error = e
                continue  # retry

        return (
            f"Failed to fetch transcript for {video_id} after {_MAX_RETRIES} attempts: {last_error}\n"
            "If running on a cloud IP, set YOUTUBE_COOKIES_FILE=cookies.txt in your .env "
            "(export cookies from your browser using the 'Get cookies.txt LOCALLY' extension)."
        )
