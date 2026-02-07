# Project Guide

## Overview

AI-powered outbound voice agent system for lead qualification via phone calls. Built with LiveKit Agents (Python), Stanford DSPy, and FastAPI.

**How it works:**
1. User submits leads via web form
2. DSPy builds personalized call context per lead (before the call)
3. LiveKit dispatches outbound SIP call
4. 4-agent workflow qualifies the lead (Greeting → Discovery → Pitch → Close)
5. Post-call emails sent to owner and lead

## Architecture

```
Web Form (apps/web)
    ↓ POST /calls
FastAPI (apps/api)
    ├─ Validate + rate limit
    ├─ DSPy context builder (packages/context_builder)
    └─ LiveKit SIP dispatch (apps/api/dispatch.py)
         ↓
Voice Agent (packages/voice_agent)
    ├─ GreetingAgent  →  build rapport
    ├─ DiscoveryAgent →  ask qualification questions
    ├─ PitchAgent     →  present value, handle objections
    └─ CloseAgent     →  book meeting / close sale / collect info
         ↓
Post-Call
    ├─ Owner summary email
    └─ Lead email (booking link / payment link)
```

## Project Structure

```
livekit-voice-agent/
├── src/
│   └── agent.py                          # Production agent (SIP, email, scraping)
│
├── apps/
│   ├── api/src/api/
│   │   ├── main.py                       # FastAPI (POST /calls, GET /calls/{id})
│   │   └── dispatch.py                   # LiveKit SIP dispatch
│   └── web/
│       └── index.html                    # Lead submission form
│
├── packages/
│   ├── shared/src/shared/
│   │   ├── schemas.py                    # All data models (Lead, CallRequest, etc.)
│   │   ├── email.py                      # Post-call email (Resend API)
│   │   └── scraper.py                    # Website scraping (Firecrawl)
│   │
│   ├── voice_agent/src/voice_agent/
│   │   ├── agent.py                      # Package agent (provider-agnostic)
│   │   └── config.py                     # Provider config from env vars
│   │
│   └── context_builder/src/context_builder/
│       └── builder.py                    # DSPy context generation
│
├── docs/
│   ├── RESEARCH_BASED_UPGRADES.md        # Roadmap and implementation tracker
│   ├── architecture.md                   # System architecture
│   ├── decision-log.md                   # Engineering decisions
│   └── LOGIC_REVIEW_METHODOLOGY.md       # Code review anti-patterns
│
├── pyproject.toml                        # UV workspace config
├── taskfile.yaml                         # Task runner
└── .env.example                          # Required environment variables
```

## Key Design Decisions

### No DSPy in Real-Time Loop

Voice AI is latency-sensitive. DSPy modules take 500ms-2s. Therefore:
- `context_builder` runs **before** the call starts (in the API layer)
- `voice_agent` receives pre-built `ContextInstance` JSON
- Agent code is simple, fast, and DSPy-free

### Multi-Agent Handoff Workflow

Each conversation phase is a separate agent with focused instructions and 1-3 tools. This minimizes LLM context per turn, reducing latency. State flows through `session.userdata` (`CallState` dataclass).

```
GreetingAgent → DiscoveryAgent → PitchAgent → CloseAgent
```

### Per-Lead Data Model

Each phone number is a distinct person (`Lead` class with name, phone, company, email, title). The API builds separate context and dispatches separate calls for each lead.

### Provider-Agnostic Schemas

The `shared` package has no hardcoded model strings. Provider config lives in environment variables via `config.py`.

### Ephemeral Storage

No persistent database. CallJob records expire after 10 minutes. Background cleanup removes expired records every 60 seconds.

## Data Models (packages/shared/src/shared/schemas.py)

| Model | Purpose |
|-------|---------|
| `Lead` | One person: phone (E.164), name, company, email, title |
| `CallRequest` | Form submission: owner_email, leads (1-5), product, goal |
| `ContextInstance` | Pre-built by DSPy: opening_line, questions, objection_handlers |
| `CallJob` | Ephemeral call record (10 min TTL) |
| `CallResult` | Post-call outcome: goal, outcome, collected_data |
| `Submission` | Batch of calls for one form submission |

| Enum | Values |
|------|--------|
| `CallGoal` | `book_meeting`, `qualify_interest`, `collect_info`, `close_sale` |
| `AgentStyle` | `professional`, `friendly`, `assertive`, `luxury`, `concise` |

## Commands

```bash
task install           # Install all packages
task test              # Run all tests
task lint              # Lint (ruff check)
task format            # Format (ruff format)
task agent:dev         # Run agent in dev mode
task agent:console     # Talk to agent in terminal
task api:dev           # Run API (port 8000)
task web:dev           # Run web form (port 3000)
```

## Running the Full Stack

```bash
# Terminal 1
task agent:dev

# Terminal 2
task api:dev

# Terminal 3
task web:dev
```

Then open http://localhost:3000 to submit leads.

## Environment Setup

Copy `.env.example` to `.env.local` and fill in credentials:

```bash
# LiveKit Cloud
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
SIP_OUTBOUND_TRUNK_ID=

# Provider APIs
DEEPGRAM_API_KEY=
OPENAI_API_KEY=
ELEVEN_API_KEY=
ELEVENLABS_VOICE_ID=

# Optional
RESEND_API_KEY=          # Post-call emails
FIRECRAWL_API_KEY=       # Website scraping
```

## Testing

```bash
task test              # All tests
task test:agent        # Voice agent tests only
task test:shared       # Schema tests only
```

Test locations:
- `packages/shared/tests/` — Pydantic model validation, email logic
- `packages/voice_agent/tests/` — Agent behavior evals (LLM-judged)
- `packages/context_builder/tests/` — Context generation

## Two Agent Implementations

| File | Purpose | Providers |
|------|---------|-----------|
| `src/agent.py` | Production — SIP dialing, email, scraping | Deepgram, OpenAI, ElevenLabs |
| `packages/voice_agent/src/voice_agent/agent.py` | Package — testable, provider-agnostic | Via `inference` module |

Both share the same 4-agent workflow.

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/RESEARCH_BASED_UPGRADES.md` | Roadmap, research findings, implementation status |
| `docs/architecture.md` | System architecture diagram |
| `docs/decision-log.md` | Engineering decision rationale |
| `docs/LOGIC_REVIEW_METHODOLOGY.md` | Code review anti-patterns |
