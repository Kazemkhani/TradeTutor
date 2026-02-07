# AI Lead Qualification Voice Agent

An autonomous voice agent system that qualifies sales leads through real phone calls. Built as a Final Year Project at the University of Birmingham.

The system conducts multi-phase sales conversations using a 4-agent workflow architecture, with DSPy-generated call context and per-lead personalization.

## How It Works

```
Web Form → API → DSPy Context Builder → LiveKit Voice Agent → Phone Call
```

1. **Submit leads** via the web form (name, phone, company, goal)
2. **Context builder** generates personalized call scripts using Stanford DSPy
3. **Voice agent** places outbound calls via SIP telephony
4. **Multi-agent workflow** conducts the conversation through 4 phases:

| Phase | Agent | Purpose |
|-------|-------|---------|
| 1 | GreetingAgent | Opens call, builds rapport |
| 2 | DiscoveryAgent | Asks qualification questions, records answers |
| 3 | PitchAgent | Presents value proposition, handles objections |
| 4 | CloseAgent | Books meeting / closes sale / collects info |

## Architecture

```
apps/
  api/             FastAPI orchestration (POST /calls dispatches to all leads)
  web/             Web form for lead submission

packages/
  shared/          Pydantic schemas (Lead, ContextInstance, CallJob)
  context_builder/ DSPy-based context generation (runs BEFORE calls)
  voice_agent/     LiveKit voice agent (multi-agent workflow)

src/
  agent.py         Production agent with SIP dialing + email sending

docs/              Architecture, decision log, research, methodology
```

See [docs/architecture.md](docs/architecture.md) for the full system diagram.

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| **No DSPy in real-time loop** | Voice AI is latency-sensitive; context is built before calls |
| **Provider-agnostic schemas** | No hardcoded model strings; config via environment variables |
| **Multi-agent handoffs** | Each conversation phase has focused instructions and tools |
| **Per-lead context** | Each lead gets personalized opening lines, questions, objection handlers |
| **ElevenLabs TTS + Deepgram Nova-3 STT** | Best-in-class voice quality and transcription accuracy |
| **Background audio** | Office ambience + keyboard typing during thinking for natural feel |

See [docs/decision-log.md](docs/decision-log.md) for the full decision log.

## Tech Stack

- **Voice AI**: [LiveKit Agents](https://docs.livekit.io/agents/) (Python SDK) + LiveKit Cloud
- **LLM**: OpenAI GPT-4o-mini (via LiveKit inference gateway)
- **STT**: Deepgram Nova-3
- **TTS**: ElevenLabs Turbo v2.5
- **Context Generation**: [Stanford DSPy](https://github.com/stanfordnlp/dspy)
- **API**: FastAPI with ephemeral storage (10-min TTL)
- **Web**: Static HTML/CSS/JS (no framework)
- **Telephony**: SIP outbound via LiveKit
- **Package Management**: [UV](https://docs.astral.sh/uv/) workspaces
- **Testing**: pytest (182 tests across 4 packages)

## Quick Start

### Prerequisites

- Python 3.10-3.13
- [UV](https://docs.astral.sh/uv/) package manager
- [LiveKit Cloud](https://cloud.livekit.io/) account
- [Task](https://taskfile.dev/) runner

### Setup

```bash
# Install all packages
task install

# Set up LiveKit credentials
lk cloud auth
lk app env -w -d .env.local

# Download ML models (VAD, turn detector)
task agent:download
```

Add provider configuration to `.env.local` (see [.env.example](.env.example) for all variables).

### Run

```bash
# Terminal 1: API server
task api:dev

# Terminal 2: Web form
task web:dev

# Terminal 3: Voice agent
task agent:dev
```

Open http://localhost:3000 to submit leads.

### Test

```bash
task test     # Run all 182 tests
task lint     # Lint with ruff
task format   # Format with ruff
```

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System design and data flow diagram |
| [Decision Log](docs/decision-log.md) | Engineering decisions and trade-offs |
| [Research-Based Upgrades](docs/RESEARCH_BASED_UPGRADES.md) | Voice AI research and implementation plan |
| [Logic Review Methodology](docs/LOGIC_REVIEW_METHODOLOGY.md) | Framework for preventing data model flaws |
| [UX Analysis](docs/WORLD_CLASS_UX_ANALYSIS.md) | Voice UX research and heuristic audit |

## License

MIT License - see [LICENSE](LICENSE).
