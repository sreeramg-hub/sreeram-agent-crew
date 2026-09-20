# sreeram-agent-crew

A personal AI crew that automates daily research tasks — monitors markets, watches YouTube channels, summarises expert opinions with full attribution, and delivers a morning digest email. Built on [CrewAI](https://github.com/crewaiinc/crewai) (open-source) and Anthropic Claude, running free on GitHub Actions.

**The pattern is general.** This repo tracks gold and silver as a concrete example, but the same architecture applies to any domain where you want to monitor sources, synthesise what's new, and get a daily briefing: crypto, stocks, news, sports, research papers, podcasts — anything with a YouTube presence or a price feed.

A companion repo ([sreeram-agent-skills](https://github.com/sreeramg-hub/sreeram-agent-skills)) extracts the reusable patterns from this project for anyone building similar personal automations.

---

## What it does

**Daily digest (runs every morning)**
- Fetches live spot prices for the tracked assets
- Checks tracked YouTube channels for new uploads since the last run
- Lists new videos as links with the channel-written description (videos are not transcribed, so nothing is claimed about what was said in them)
- Composes a structured HTML email and delivers it via [Resend](https://resend.com)

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
              │  Research Agent A ──┐                    │
              │                     ├──► Editor Agent ──► Email │
              │  Research Agent B ──┘                    │
              └──────────────────────────────────────────┘
```

**Research Agents** — each covers one topic: price lookup → YouTube new-upload check → linked list of new videos

**Editor Agent** — consolidation only. Receives all research outputs, writes an HTML digest, sends it. Does not add new opinions or claims.

*In this repo: Research Agent A = Gold, Research Agent B = Silver. Swap in your own topics by updating `agents.yaml`, `tasks.yaml`, and the channel IDs in your environment config.*

---

## Tech stack

| Component | Choice | Why |
|---|---|---|
| Agent framework | CrewAI (open-source) | Role/goal/backstory model fits research-and-summarise tasks naturally |
| LLM | Anthropic Claude Sonnet | Strong instruction-following; reliable attribution in prompts |
| Price data | Yahoo Finance (no key) | Free, reliable, no quota |
| YouTube monitoring | Public RSS feed (no key) | No API key, no quota; 15 most recent videos per channel |
| Email delivery | Resend | Simple API, generous free tier |
| Scheduling | GitHub Actions cron | Free tier covers the daily run comfortably |
| Package management | uv | CrewAI's default; fast dependency resolution |

---

## Project structure

```
sreeram-agent-crew/
├── .github/workflows/
│   ├── daily-digest.yml          Runs the full crew every morning
├── src/sreeram_crew_scaffold/
│   ├── config/
│   │   ├── agents.yaml           Agent role/goal/backstory definitions
│   │   └── tasks.yaml            Task descriptions and expected outputs
│   ├── tools/
│   │   ├── price_tool.py         Live spot price via Yahoo Finance
│   │   ├── youtube_tool.py       RSS-based new-upload detection with dedup + descriptions
│   │   └── email_tool.py         Resend-based HTML email sender
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

## Adapting this to your own use case

The tools and agent structure are intentionally general:

- **Different assets** — update `GOLD_CHANNEL_IDS` / `SILVER_CHANNEL_IDS` variables and the agent names in `agents.yaml` and `tasks.yaml`
- **Different YouTube channels** — add channel IDs to the environment variables (see [how to find a channel ID](#finding-a-channel-id) below)
- **Different price sources** — swap out `price_tool.py` with any API that returns a number; the agent doesn't care what the number represents
- **More or fewer research agents** — add or remove `@agent` and `@task` blocks in `crew.py`; the Editor Agent's `context:` list ties them all together

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

**Variables** (Settings → Secrets and variables → Actions → Variables):

| Variable | Example value |
|---|---|
| `GOLD_CHANNEL_IDS` | `UC9ijza42jVR3T6b8bColgvg,UCE_edD0qJd_EyfwGCfLHSeQ` |
| `SILVER_CHANNEL_IDS` | `UC9ijza42jVR3T6b8bColgvg` |

### Finding a channel ID

Channel IDs start with `UC` and are 24 characters long. Easiest way:

```bash
uvx yt-dlp --dump-single-json "https://www.youtube.com/@ChannelHandle/videos" \
  --playlist-items 1 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('channel_id'))"
```

---

## Scheduling

| Workflow | Schedule | What it does |
|---|---|---|
| `daily-digest.yml` | 14:00 UTC daily | Full crew — price + YouTube links + digest email |

Adjust the `cron:` line in each workflow file to change timing. [crontab.guru](https://crontab.guru) is useful for testing expressions. To trigger manually: **Actions → workflow name → Run workflow**.

---

## Design decisions

**Say only what is known** — videos are listed with their link and channel-written description, never with claims about what was said in them. The Editor Agent is explicitly an editor, not an analyst. The digest includes a disclaimer that it is compiled from public sources for personal research and does not constitute financial advice.

**No CrewAI cloud platform** — uses the open-source `crewai` Python package only. All execution happens on GitHub Actions runners calling the Anthropic API directly. No CrewAI execution quota, no hosted infrastructure dependency.

**RSS over YouTube Data API** — YouTube's public RSS feed requires no API key and has no quota. Returns the 15 most recent videos per channel, enough for daily monitoring.

**Seen-state in git** — processed video IDs are stored in `state/*.json` and committed back after each run (`[skip ci]` prevents re-triggering). No database needed; git history doubles as an audit log.

**Links over transcripts** — Caption requests from cloud servers can be blocked by YouTube, so the digest does not depend on transcripts. Transcript-based summaries (for example by handing the video URL to Gemini) are a planned option.

---

## Known limitations

- **RSS feed depth** — the YouTube RSS feed only returns the 15 most recent videos per channel. If more than 15 are published between runs, older ones will be missed.
- **Resend free tier** — without a verified custom domain, Resend restricts sending to your own email address only. See [resend.com/domains](https://resend.com/domains) to lift this restriction.

---

## Companion repo

**[sreeram-agent-skills](https://github.com/sreeramg-hub/sreeram-agent-skills)** extracts the reusable patterns from this project — YouTube RSS watching, CrewAI tool patterns, GitHub Actions scheduling with state commit-back, and attributed-sentiment prompting. If you want to adapt any of these for your own use case, start there.

---

## License

MIT
