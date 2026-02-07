# System Architecture

## AI Lead Qualification Voice Agent System

This document describes the architecture of the AI Lead Qualification Voice Agent System.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AI Lead Qualification Voice Agent System                  │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────┐
                              │   apps/web   │
                              │  (Web Form)  │
                              └──────┬───────┘
                                     │ Submit Lead
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              apps/api (FastAPI)                              │
│  ┌─────────────┐   ┌─────────────────┐   ┌──────────────────────────────┐   │
│  │ POST /leads │ → │ Context Builder │ → │ Trigger Call (LiveKit SIP)   │   │
│  └─────────────┘   └─────────────────┘   └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ packages/shared │       │   packages/     │       │   packages/     │
│   (Schemas)     │◄──────│ context_builder │       │  voice_agent    │
│                 │       │    (DSPy)       │       │  (LiveKit)      │
│ • Lead          │       │                 │       │                 │
│ • AgentSpec     │       │ Builds context  │       │ Receives:       │
│ • ContextInst.  │       │ BEFORE call     │       │ --context JSON  │
│ • CallJob       │       │ starts          │──────►│                 │
└─────────────────┘       └─────────────────┘       │ No DSPy here!   │
                                                    │ Real-time only  │
                                                    └────────┬────────┘
                                                             │
                                                             ▼
                                                    ┌─────────────────┐
                                                    │  LiveKit Cloud  │
                                                    │  (Voice Call)   │
                                                    └─────────────────┘
```

## Component Details

### packages/shared

**Purpose**: Pure Pydantic schemas with no logic. Provider-agnostic.

**Key Schemas**:
- `Lead`: Lead data model (phone required, name optional)
- `AgentSpec`: Agent configuration (instructions, style, objective)
- `ContextInstance`: Pre-built context for calls
- `CallJob`: Call orchestration record

**Design Principle**: No vendor-specific strings or defaults. All provider configuration is handled elsewhere.

### packages/context_builder

**Purpose**: DSPy-based context building that runs BEFORE calls start.

**Key Components**:
- `ContextBuilder`: Class that builds ContextInstance objects
- `build_context()`: Convenience function for quick context building

**Technology**: Stanford DSPy for declarative prompting and AI reasoning.

**Design Principle**: Not latency-sensitive. Can take 500ms-2s to run. Never runs during real-time call loop.

### packages/voice_agent

**Purpose**: Real-time voice agent using LiveKit Agents.

**Key Components**:
- `agent.py`: Main agent with `Assistant` class
- `config.py`: Provider configuration (from env vars, no defaults)
- Compatibility shim at `src/agent.py`

**Context Injection**:
- MVP: `--context ./context.json` CLI flag
- Future: `--call-job-id <id>` to fetch from API

**Design Principle**: No DSPy in the real-time loop. Receives pre-built context. Fast, simple, testable.

### apps/api

**Purpose**: FastAPI orchestration layer.

**Endpoints**:
- `POST /leads`: Create new lead
- `GET /leads/{id}`: Get lead status
- `POST /calls/trigger`: Trigger qualification call
- `GET /calls/{id}`: Get call status

**Workflow**:
1. Receive lead data
2. Build context using context_builder
3. Save context to file
4. Trigger call via LiveKit SIP

### apps/web

**Purpose**: Minimal web form for lead submission.

**Technology**: Plain HTML/CSS/JS (no build step).

**Features**:
- Lead form with phone (required), name, company, email, notes
- Submits to API and triggers call
- Displays success/error messages

## Data Flow

### Lead Qualification Flow

```
1. User submits lead via web form
   ↓
2. API creates Lead record
   ↓
3. API calls context_builder.build_context(lead, agent_spec)
   ↓
4. DSPy generates:
   - Business context
   - Qualification questions
   - Objection handlers
   - Call objective
   ↓
5. API saves ContextInstance to JSON file
   ↓
6. API triggers call via LiveKit SIP with --context flag
   ↓
7. Voice agent loads context and conducts call
   ↓
8. Call outcome recorded back to CallJob
```

### Context Injection Contract

**MVP (File-based)**:
```bash
python src/agent.py dev --context ./contexts/abc123.json
```

**Future (API-based)**:
```bash
python src/agent.py dev --call-job-id abc123
```

## Technology Stack

| Component | Technology |
|-----------|------------|
| Voice Agent | LiveKit Agents (Python) |
| LLM | Anthropic Claude (via LiveKit Inference) |
| STT | AssemblyAI (via LiveKit Inference) |
| TTS | Cartesia (via LiveKit Inference) |
| Context Building | Stanford DSPy |
| API | FastAPI |
| Schemas | Pydantic v2 |
| Package Manager | UV |
| Telephony | LiveKit SIP |

## Separation of Concerns

| Package | Responsibility | Latency Sensitivity |
|---------|---------------|---------------------|
| shared | Data models only | N/A |
| context_builder | AI reasoning | Low (pre-call) |
| voice_agent | Real-time voice | High (real-time) |
| api | Orchestration | Medium |
| web | User interface | N/A |

## Configuration

### Environment Variables (Required)

```bash
# LiveKit
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=

# Voice Agent Provider Config (no defaults)
VOICE_AGENT_LLM_MODEL=
VOICE_AGENT_STT_MODEL=
VOICE_AGENT_TTS_MODEL=
VOICE_AGENT_VOICE_ID=
VOICE_AGENT_LANGUAGE=en
```

### Why No Defaults?

Provider configuration has no hardcoded defaults to:
1. Avoid vendor coupling in the codebase
2. Force explicit configuration
3. Make the system provider-agnostic
4. Produce clear error messages when misconfigured
