# sreeram-agent-crew

A personal daily digest, delivered as one morning email: the latest in **AI, front end and UI/UX** (with links), followed by **gold & silver** prices and new videos. Built on Python, [Anthropic Claude](https://www.anthropic.com) and [CrewAI](https://github.com/crewaiinc/crewai), running free on GitHub Actions.

**The pattern is general.** Swap the feeds in one YAML file and the channel IDs in the environment and you have a daily briefing on any topic.

A companion repo ([sreeram-agent-skills](https://github.com/sreeramg-hub/sreeram-agent-skills)) extracts the reusable patterns from this project.

---

## What it does

Every morning it sends one email, tech first:

1. **AI · Front end · UI/UX** — recent items from ~23 sources (Hacker News, Hugging Face papers, official blogs and release notes), de-duplicated, ranked by Claude, each with a link and a one-line blurb. Nothing is ever repeated: emailed links are remembered.
2. **Gold & Silver** — futures prices, plus new videos from tracked YouTube channels as links with the channel's own description (videos are not transcribed, so nothing is claimed about what was said in them).
3. **Footer** — the disclaimer and a health line (sources reachable, how each section was curated), so a silent failure shows up in the email itself.

Everything runs on the GitHub Actions free tier. No servers or databases, just your own API keys.

---

## Architecture

```
GitHub Actions (cron, daily)
        │
        ▼
   main.py ──► tech/collect.py   fetch feeds + HN + HF papers, filter by date, drop repeats   (no LLM)
        │      tech/curate.py    Claude picks item IDs + writes blurbs; links come from the data
        │
        ├────► CrewAI crew       gold & silver video agents ──► editor ──► metals.html fragment
        │      tools/price_tool  futures prices, fetched directly                             (no LLM)
        │
        ▼
   tech/render.py  ──►  tools/email_tool.py (Resend)      then remember what was sent (state/)
```

**"LLM decides, scripts act."** Fetching, filtering, de-duplication, links, HTML, the disclaimer and sending are plain Python. Claude only chooses which items matter and writes short blurbs. It returns item IDs, never URLs, so a link in the email cannot be invented, and if the API fails the section falls back to the newest items with titles only.

---

## Tech stack

| Component | Choice | Why |
|---|---|---|
| LLM | Anthropic Claude Sonnet | Curation and short blurbs; forced tool-use gives structured output |
| Agent framework | CrewAI (open-source) | Runs the gold & silver video crew |
| Tech sources | RSS/Atom, Hacker News (Algolia), Hugging Face papers | No keys, no quotas; edited in `config/tech_sources.yaml` |
| Price data | Yahoo Finance futures (no key) | Free, no quota |
| YouTube monitoring | Public RSS feed (no key) | 15 most recent videos per channel |
| Email delivery | Resend | Simple API, generous free tier |
| Scheduling | GitHub Actions cron | Free tier covers the daily run |
| Package management | uv | Fast, reproducible installs |

---

## Project structure

```
sreeram-agent-crew/
├── .github/workflows/
│   ├── daily-digest.yml          Sends the digest every morning, commits state back
│   └── tests.yml                 Runs the test suite on every PR
├── src/sreeram_crew_scaffold/
│   ├── config/
│   │   ├── tech_sources.yaml     Tech feeds per section, look-back windows, picks per section
│   │   ├── agents.yaml           Gold/silver video crew: roles
│   │   └── tasks.yaml            Gold/silver video crew: tasks
│   ├── tech/
│   │   ├── collect.py            Fetch, parse, date-filter and de-duplicate sources
│   │   ├── curate.py             Claude picks + blurbs, with a no-LLM fallback
│   │   └── render.py             HTML email (escaped, phone-friendly) + sanitiser
│   ├── tools/
│   │   ├── youtube_tool.py       RSS new-upload detection with dedup + descriptions
│   │   ├── price_tool.py         Gold/silver futures prices
│   │   └── email_tool.py         Resend sender
│   ├── crew.py                   Gold & silver video crew
│   └── main.py                   Orchestrates the whole digest
├── state/                        Already-seen video IDs and links (committed back each run)
├── tests/
├── .env.example
├── pyproject.toml
└── uv.lock
```

---

## Adapting this to your own use case

The tools and agent structure are intentionally general:

- **Different tech topics or sources** — edit `config/tech_sources.yaml`: add a feed URL, change how many items each section shows (`pick`) or how far back it looks (`window_hours`)
- **Different YouTube channels** — add channel IDs to the environment variables (see [how to find a channel ID](#finding-a-channel-id) below)
- **Different assets** — update `GOLD_CHANNEL_IDS` / `SILVER_CHANNEL_IDS`, the tickers in `price_tool.py`, and the agent names in `agents.yaml` and `tasks.yaml`
- **More or fewer video agents** — add or remove `@agent` and `@task` blocks in `crew.py`

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

# Preview the digest without sending anything: writes digest.html (open it in a browser)
DIGEST_DRY_RUN=1 uv run crewai run

# Send it for real
uv run crewai run

# Run the tests
uv run --with pytest pytest
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
| `daily-digest.yml` | 14:00 UTC daily | Builds and sends the full digest |
| `tests.yml` | Every PR / push to main | Runs the test suite |

Adjust the `cron:` line in each workflow file to change timing. [crontab.guru](https://crontab.guru) is useful for testing expressions. To trigger manually: **Actions → workflow name → Run workflow**.

---

## Design decisions

**Say only what is known** — videos are listed with their link and channel-written description, never with claims about what was said in them. The Editor Agent is explicitly an editor, not an analyst. The digest includes a disclaimer that it is compiled from public sources for personal research and does not constitute financial advice.

**No CrewAI cloud platform** — uses the open-source `crewai` Python package only. All execution happens on GitHub Actions runners calling the Anthropic API directly. No CrewAI execution quota, no hosted infrastructure dependency.

**RSS over YouTube Data API** — YouTube's public RSS feed requires no API key and has no quota. Returns the 15 most recent videos per channel, enough for daily monitoring.

**Seen-state in git** — processed video IDs and emailed tech links are stored in `state/*.json` and committed back after each run (`[skip ci]` prevents re-triggering). Tech links are recorded only after the email is actually sent, so a failed run offers the same items again tomorrow rather than dropping them. No database needed; git history doubles as an audit log.

**Claude picks, code links** — Claude sees numbered candidates and returns IDs plus a short blurb; titles and URLs come from the fetched data. Blurbs may only restate what the item's own text says. Feed text is treated as untrusted (escaped in the email, never followed as instructions).

**Failures are visible** — one broken source never blocks the digest, and the footer reports what failed. A failed send fails the workflow run.

**Links over transcripts** — Caption requests from cloud servers can be blocked by YouTube, so the digest does not depend on transcripts. Transcript-based summaries (for example by handing the video URL to Gemini) are a planned option.

---

## Known limitations

- **Source coverage** — only sources with a public feed or API are included. Anthropic's news page has no RSS feed, so it is not covered yet. Front-end blogs post rarely, so that section uses a two-week look-back and can be thin on quiet days.
- **Prices are futures** — gold and silver prices are front-month COMEX futures (Yahoo `GC=F` / `SI=F`), close to but not identical to spot.
- **RSS feed depth** — the YouTube RSS feed only returns the 15 most recent videos per channel. If more than 15 are published between runs, older ones will be missed.
- **Resend free tier** — without a verified custom domain, Resend restricts sending to your own email address only. See [resend.com/domains](https://resend.com/domains) to lift this restriction.

---

## Companion repo

**[sreeram-agent-skills](https://github.com/sreeramg-hub/sreeram-agent-skills)** extracts the reusable patterns from this project — YouTube RSS watching, CrewAI tool patterns, GitHub Actions scheduling with state commit-back, and attributed-sentiment prompting. If you want to adapt any of these for your own use case, start there.

---

## License

MIT
