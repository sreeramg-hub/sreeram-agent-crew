# sreeram-agent-crew

## What this repo is

This is the **working implementation** of a multi-agent system built on the
open-source **CrewAI** Python framework. Three agents run on a daily
schedule via GitHub Actions, research gold/silver markets, and email a
consolidated daily digest.

This repo contains the actual runnable code, secrets configuration, and
GitHub Actions workflows. It is the "does the thing" repo.

For the companion repo that documents and extracts reusable patterns from
this code for others to learn from/fork, see **`sreeram-agent-skills`**
(separate repo, separate purpose — see its own README for the distinction).

---

## Why this exists (context for whoever/whatever is building this)

Primary goals, in order:

1. **Learn and upskill** in agentic AI architecture by building something real, not a toy tutorial.
2. **Automate a genuine daily task** — tracking gold/silver prices and watching specific YouTube channels/experts for new analysis, normally done manually.
3. Use a current, resume-relevant framework (CrewAI) rather than rolling bespoke orchestration code, so the build itself is a learning exercise in the framework.
4. Eventually link this project from a personal portfolio site as a case study.

This is a **personal project**, not a commercial product. No enterprise
infra. Runs for free (or near-zero cost) using GitHub Actions' free tier +
Anthropic API usage + a transcription API + a free-tier email API.

---

## Architecture

```
Gold Agent ──┐
             ├──> Final Agent (manager/editor) ──> Daily email
Silver Agent ┘
```

- **Gold Agent**: checks today's gold price + % change, checks tracked
  YouTube channels for new uploads, transcribes any new videos, summarizes
  with attributed sentiment (bullish/bearish/neutral, always tied to who
  said it — never stated as fact).
- **Silver Agent**: identical pattern, for silver.
- **Final Agent**: consolidates both reports into one HTML email. Acts as
  an editor, not an analyst — it organizes and clarifies, it does not add
  new claims or flatten attributed opinions into unattributed "facts."

**Why CrewAI**: each agent maps naturally to a role-playing team member
(role, goal, backstory) with its own tools, coordinated through Tasks and a
Crew. This is the framework's core mental model and matches this project's
shape closely. We're using the **open-source `crewai` Python package**,
not CrewAI's hosted Studio/cloud platform — there's no execution quota,
because nothing runs on CrewAI's infrastructure. All execution happens in
our own GitHub Actions runners, calling our own Anthropic API key directly.

**Important framing on "sentiment analysis":** this system is built to be
an aggregator with labeled synthesis, not a source of financial advice.
Every price target or prediction is attributed to whoever said it. The
Final Agent's job is editorial consolidation, not generating new opinions.
The output email includes a disclaimer that this is synthesized from
public sources for personal research, not financial advice. This is a
deliberate design constraint, not an afterthought — preserve it through
any changes to prompts or task descriptions.

---

## Tech stack

- Python 3.10–3.13 (CrewAI's supported range)
- `crewai` + `crewai-tools` (core framework, open-source, MIT licensed)
- LLM: Anthropic Claude via CrewAI's LiteLLM integration (confirm current
  model alias at build time, e.g. `anthropic/claude-sonnet-4-6`)
- Transcription: a separate provider — Claude does not natively transcribe
  audio. OpenAI Whisper API or equivalent (confirm current model
  name/pricing at build time)
- `yt-dlp` for YouTube audio download
- Email: Resend or equivalent (confirm current free tier at build time)
- Scheduling: GitHub Actions scheduled workflows (`cron`), free tier
- Package management: `uv` + `pyproject.toml` (CrewAI's CLI scaffolds this
  way by default — don't fight it)

---

## Project structure

```
sreeram-agent-crew/
├── .github/workflows/
│   └── daily-digest.yml          Scheduled workflow, runs the full crew
├── src/
│   └── sreeram_crew/
│       ├── config/
│       │   ├── agents.yaml       Gold/Silver/Final agent definitions
│       │   └── tasks.yaml        Task descriptions per agent
│       ├── tools/
│       │   ├── price_tool.py     PriceLookupTool
│       │   ├── youtube_tool.py   YoutubeNewUploadsTool
│       │   ├── transcribe_tool.py TranscribeVideoTool
│       │   └── email_tool.py     SendEmailTool
│       ├── crew.py               Crew assembly
│       └── main.py               Entry point
├── state/
│   ├── gold_seen.json            Tracked video IDs (committed back each run)
│   └── silver_seen.json
├── .env.example
├── pyproject.toml
└── README.md                     This file
```

---

## Agent / Task design (reference — full YAML lives in config/)

**gold_agent**: role "Gold Market Research Analyst." Tools: price lookup,
YouTube new-uploads checker, video transcriber. Backstory emphasizes never
stating a prediction as fact, always attributing it, flagging disagreement
between sources rather than picking a side.

**silver_agent**: identical pattern, silver.

**final_agent**: role "Daily Digest Editor." Tool: send email. Backstory:
"You are an editor, not an analyst. You don't add new claims — you
organize and clarify what the specialist agents already found."
`allow_delegation: false` on all three agents to avoid delegation loops
(per CrewAI's own troubleshooting guidance — only a true manager agent in
a hierarchical process should have delegation enabled, and we're not using
a hierarchical process for v1).

**Process**: `Process.sequential`. Gold and Silver tasks run, then
`compose_digest_task` runs with `context: [gold_research_task,
silver_research_task]` — this is CrewAI's native way of passing both
agents' outputs into the Final Agent's task, replacing any need for manual
JSON file handoff between agents.

---

## Tools (custom BaseTool subclasses)

Each tool lives in `tools/` as a `BaseTool` subclass with a Pydantic
`args_schema` for its inputs (current CrewAI convention — see CrewAI docs
for the exact base pattern if unsure).

- **PriceLookupTool**: takes `metal` ("gold" or "silver"), returns current
  price + % change from previously recorded price (stored in `state/`).
  Free price API, e.g. gold-api.com (no key needed) — confirm reliability
  at build time, swap if needed.
- **YoutubeNewUploadsTool**: takes comma-separated channel IDs, checks each
  channel's public RSS feed (`https://www.youtube.com/feeds/videos.xml?channel_id=...`
  — no API key, no quota) against `state/{agent}_seen.json`, returns any
  videos not yet seen, updates seen-state.
- **TranscribeVideoTool**: takes a video URL, downloads audio via `yt-dlp`,
  sends to a transcription API, returns full transcript text, cleans up
  the audio file afterward.
- **SendEmailTool**: takes subject + HTML body, sends via the chosen email
  API. Used only by `final_agent`.

---

## State management

`state/gold_seen.json` and `state/silver_seen.json` track which video IDs
have already been processed, so the same upload is never summarized twice.
On first run, seed these files with whatever's currently in each channel's
feed — there is no backlog processing; only genuinely new uploads going
forward should be picked up. The GitHub Actions workflow commits updated
state back to the repo at the end of each run (with `[skip ci]` in the
commit message to avoid re-triggering itself).

---

## Secrets and variables (GitHub repo settings)

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

```
ANTHROPIC_API_KEY
TRANSCRIPTION_API_KEY
RESEND_API_KEY
DIGEST_RECIPIENT_EMAIL
```

**Variables** (same location, Variables tab — not sensitive, so variables not secrets):

```
GOLD_CHANNEL_IDS      (comma-separated YouTube channel IDs)
SILVER_CHANNEL_IDS    (comma-separated YouTube channel IDs)
```

For local development, copy `.env.example` to `.env` and fill in the same
values.

---

## Build checkpoints (work through in order; test before moving on)

1. **Scaffold via CrewAI CLI** — `crewai create crew sreeram-agent-crew` (or
   equivalent within this existing repo), confirm the default example crew
   runs successfully before customizing anything.
2. **Price tool standalone** — build and test `PriceLookupTool._run()` directly, no agent involved yet.
3. **YouTube tool standalone** — build and test `YoutubeNewUploadsTool._run()` directly with 1-2 real channel IDs; verify new-vs-seen detection by clearing state and re-running.
4. **Transcribe tool standalone** — test against one real video URL, spot-check transcript accuracy.
5. **Gold Agent alone** — minimal single-agent crew, no Final Agent yet. Run and inspect output structure/attribution/sentiment tagging.
6. **Add Silver Agent** — both research agents running sequentially, each producing correct independent output.
7. **Email tool + Final Agent** — full three-agent crew, end-to-end run, confirm email arrives correctly composed with attribution preserved and disclaimer present.
8. **GitHub Actions** — workflow YAML, secrets/variables configured, trigger via `workflow_dispatch`, confirm successful run + state commit-back + email delivery.
9. **Schedule + soak test** — finalize cron timing, let it run unattended for 2-3 real days, confirm no duplicate processing and consistent delivery.

Each checkpoint should be reviewed and confirmed working before proceeding
to the next — don't let the build run ahead through multiple checkpoints
unsupervised.

---

## Open items to confirm during build (don't assume — verify at build time)

- Current CrewAI LiteLLM model string format for Claude
- Current transcription API model name and pricing
- Current Resend (or chosen email provider) free tier limits
- Gold/Silver YouTube channel IDs to track (provided separately, not yet finalized)
- Preferred cron time in UTC for desired local delivery time

---

## Relationship to sreeram-agent-skills

Once tools/patterns here are proven stable (roughly after checkpoint 7),
extract generalized, documented versions into the `sreeram-agent-skills`
repo for others to learn from or reuse. That repo is documentation- and
education-first; this repo is execution-first. Don't let the skills repo's
structure dictate this repo's code shape — extract and generalize after
the fact, not before.
