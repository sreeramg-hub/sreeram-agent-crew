# sreeram-agent-crew

A personal multi-agent automation built on [CrewAI](https://github.com/crewaiinc/crewai) (open-source) and Anthropic Claude. Three AI agents collaborate daily to research gold and silver markets, summarise new YouTube analysis with full attribution, and deliver a consolidated digest email — automatically, every morning.

A companion repo ([sreeram-agent-skills](https://github.com/sreeramg-hub/sreeram-agent-skills)) extracts the reusable patterns from this project for anyone building similar agentic automations.

---

## What it does

**Daily digest (runs every morning)**
- Fetches live gold and silver spot prices
- Checks tracked YouTube channels for new uploads since the last run
- Transcribes new videos and summarises key analyst opinions — always attributed to the person who said them, never stated as fact
- Composes a structured HTML email and delivers it via [Resend](https://resend.com)

**Hourly price alerts**
- Checks gold and silver prices every hour
- Sends an immediate alert email if either metal drops more than $75 from the previous close

Everything runs on GitHub Actions free tier. No servers, no databases, no CrewAI cloud platform — just your own API keys running on GitHub's runners.

---

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         GitHub Actions (cron)        │
                    └──────────────┬──────────────────────┘
                                   │
              ┌────────────────────▼────────────────────┐
              │              CrewAI Crew                 │
              │                                          │
              │  Gold Agent ──┐                          │
              │               ├──► Final Agent ──► Email │
              │  Silver Agent ┘                          │
              └──────────────────────────────────────────┘
```

**Gold Agent** — price lookup → YouTube new-upload check → transcript → attributed summary

**Silver Agent** — identical pattern, independent state

**Final Agent** — editorial consolidation only. Receives both research outputs, writes an HTML digest, sends it. Does not add new opinions or claims.

**Price Alert** — standalone script (no LLM), runs hourly, fires an email if price drops >$75 from previous close.

---

## Tech stack

| Component | Choice | Why |
|---|---|---|
| Agent framework | CrewAI (open-source) | Role/goal/backstory model fits this project's shape naturally |
| LLM | Anthropic Claude Sonnet | Strong instruction-following; explicit attribution in prompts |
| Price data | Yahoo Finance (no key) | Free, reliable, no quota |
| YouTube monitoring | Public RSS feed (no key) | No API key, no quota; 15 most recent videos per channel |
| Transcription | YouTube auto-captions | Free, instant; no audio download needed for captioned videos |
| Email delivery | Resend | Simple API, generous free tier |
| Scheduling | GitHub Actions cron | Free tier covers daily + hourly runs comfortably |
| Package management | uv | CrewAI's default; fast dependency resolution |

---

## Project structure

```
sreeram-agent-crew/
├── .github/workflows/
│   ├── daily-digest.yml          Runs the full crew every morning
│   └── price-alert.yml           Hourly price drop check (no LLM)
├── src/sreeram_crew_scaffold/
│   ├── config/
│   │   ├── agents.yaml           Agent role/goal/backstory definitions
│   │   └── tasks.yaml            Task descriptions and expected outputs
│   ├── tools/
│   │   ├── price_tool.py         Live spot price via Yahoo Finance
│   │   ├── youtube_tool.py       RSS-based new-upload detection with dedup
│   │   ├── transcribe_tool.py    YouTube caption fetcher with retry/backoff
│   │   └── email_tool.py         Resend-based HTML email sender
│   ├── price_alert.py            Standalone hourly alert script
│   ├── crew.py                   Crew assembly (agents + tasks + LLM config)
│   └── main.py                   Entry point
├── state/
│   ├── gold_seen.json            Video IDs already processed (committed each run)
│   └── silver_seen.json
├── .env.example                  Template for local development
├── pyproject.toml
└── uv.lock
```

---

## Running locally

**Prerequisites:** Python 3.10–3.13, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/sreeramg-hub/sreeram-agent-crew.git
cd sreeram-agent-crew

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env and fill in your API keys and channel IDs

# Run the full digest crew
uv run crewai run

# Run the price alert check
uv run python -m sreeram_crew_scaffold.price_alert
```

---

## Configuration

Copy `.env.example` to `.env` for local development. For GitHub Actions, add these as repo secrets and variables.

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `RESEND_API_KEY` | Your [Resend](https://resend.com) API key |
| `DIGEST_RECIPIENT_EMAIL` | Delivery address (comma-separated for multiple) |
| `YOUTUBE_COOKIES` | *(Optional)* Full contents of a Netscape `cookies.txt` exported from your browser — bypasses YouTube IP blocks on cloud runners |

**Variables** (Settings → Secrets and variables → Actions → Variables):

| Variable | Example value |
|---|---|
| `GOLD_CHANNEL_IDS` | `UC9ijza42jVR3T6b8bColgvg,UCE_edD0qJd_EyfwGCfLHSeQ` |
| `SILVER_CHANNEL_IDS` | `UC9ijza42jVR3T6b8bColgvg` |

**Finding a YouTube channel ID:** run `yt-dlp --dump-single-json "https://www.youtube.com/@ChannelName/videos" --playlist-items 1 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('channel_id'))"` or search for `"channelId"` in the channel page's source.

---

## Scheduling

| Workflow | Schedule | What it does |
|---|---|---|
| `daily-digest.yml` | 11:00 UTC daily | Full crew — price + YouTube + digest email |
| `price-alert.yml` | Every hour | Price check only — alert email if drop > $75 |

Adjust the `cron:` line in each workflow file to change the timing. [crontab.guru](https://crontab.guru) is useful for testing cron expressions.

To trigger either workflow manually: **Actions → workflow name → Run workflow**.

---

## Design decisions

**Attribution over synthesis** — every price target or opinion in the digest is attributed to whoever said it ("Jordan Roy-Byrne of TheDailyGold said..."), never stated as a fact. The Final Agent is explicitly an editor, not an analyst. The digest includes a disclaimer that it is compiled from public sources for personal research and does not constitute financial advice.

**No CrewAI cloud platform** — this uses the open-source `crewai` Python package only. All execution happens on GitHub Actions runners calling the Anthropic API directly. No CrewAI execution quota, no hosted infrastructure dependency.

**RSS over YouTube Data API** — YouTube's public RSS feed (`youtube.com/feeds/videos.xml?channel_id=...`) requires no API key and has no quota. It returns the 15 most recent videos per channel, which is enough for daily monitoring of active channels.

**Seen-state in git** — processed video IDs are stored in `state/*.json` and committed back to the repo after each run (`[skip ci]` prevents re-triggering). No database needed; git history doubles as an audit log.

**Captions over audio transcription** — YouTube auto-generated captions are fetched directly via `youtube-transcript-api` (no download, no cost, instant). `yt-dlp` + a transcription API would be the fallback for videos without captions, but the channels tracked here all have captions.

---

## Known limitations

- **YouTube caption rate limiting** — making many transcript requests in quick succession from the same IP can trigger a temporary block. The tool retries with exponential backoff and falls back to a title-only summary if all retries fail. On cloud runners, adding a `YOUTUBE_COOKIES` secret resolves persistent blocks.
- **RSS feed depth** — the YouTube RSS feed only returns the 15 most recent videos. If more than 15 videos are published between runs (unlikely for the channels tracked), older ones will be missed.
- **Resend free tier** — without a verified custom domain, Resend restricts sending to your own email address only. See [resend.com/domains](https://resend.com/domains) to add a domain and lift this restriction.
- **Price alert is daily-delta only** — the `$75 drop` threshold compares current price to the previous day's close, not to an intraday peak. A recovery followed by a drop won't re-trigger unless it crosses the threshold vs. the original close.

---

## Companion repo

**[sreeram-agent-skills](https://github.com/sreeramg-hub/sreeram-agent-skills)** extracts the reusable patterns from this project — YouTube RSS watching, caption transcription, CrewAI tool patterns, GitHub Actions scheduling with state commit-back, and attributed-sentiment prompting. If you want to adapt any of these for your own use case, start there.

---

## License

MIT
