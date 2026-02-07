# Engineering Decision Log

This document records key engineering decisions made during the development of the AI Lead Qualification Voice Agent System.

---

## 1. Pre-call Context Building (DSPy)

**Decision**: Run DSPy context building BEFORE the call starts, not during.

**Date**: January 2025

**Context**: Voice AI is extremely latency-sensitive. Users expect immediate responses during phone calls. Any delay degrades the experience significantly.

**Rationale**:
- DSPy modules can take 500ms-2s to execute
- This latency is unacceptable mid-conversation
- Pre-building context gives best of both worlds:
  - Sophisticated AI reasoning for call preparation
  - Fast real-time responses during the call

**Consequences**:
- Context must be built before each call
- Adds a few seconds to call initiation (acceptable)
- Enables complex reasoning without real-time penalty

---

## 2. No DSPy in Call Loop

**Decision**: The voice_agent package has zero DSPy dependency.

**Date**: January 2025

**Context**: We needed to decide where AI reasoning should happen.

**Rationale**:
- Separation of concerns keeps code clean
- Voice agent receives pre-built ContextInstance JSON
- This keeps the agent:
  - Simple to understand
  - Easy to test
  - Fast at runtime
- DSPy complexity is isolated to context_builder

**Consequences**:
- voice_agent has no DSPy import
- All reasoning happens before the call
- Agent code is straightforward LiveKit integration

---

## 3. ContextInstance File Injection (MVP)

**Decision**: Voice agent accepts context via `--context path/to/context.json` flag.

**Date**: January 2025

**Context**: We needed a way to pass pre-built context to the agent.

**Options Considered**:
1. Environment variable (too limited for complex data)
2. API fetch at startup (adds network dependency)
3. File path CLI argument (simple, testable)
4. Embedded in room metadata (LiveKit-specific)

**Rationale**:
- File-based injection is simplest for MVP
- Easy to test (point to fixture files)
- Easy to debug (inspect JSON in editor)
- Decoupled from API (agent can run standalone)

**Future Evolution**:
- Replace with `--call-job-id <id>` to fetch from API
- Enables dynamic context updates if needed

---

## 4. LiveKit Cloud + SIP Trunk (Telephony)

**Decision**: Use LiveKit Cloud with Twilio/Telnyx SIP trunk for phone calls.

**Date**: January 2025

**Context**: The system needs to make real phone calls to leads.

**Rationale**:
- LiveKit provides WebRTC infrastructure
- LiveKit Agents handles voice AI pipeline
- SIP trunk provides PSTN connectivity
- Benefits:
  - Real phone numbers for inbound/outbound
  - WebRTC quality for AI processing
  - Scalable cloud infrastructure
  - No physical infrastructure needed

**Consequences**:
- Need SIP trunk account (Twilio/Telnyx)
- Monthly costs for phone minutes
- Number provisioning required

---

## 5. Provider-Agnostic Schemas

**Decision**: Shared schemas have no hardcoded provider defaults.

**Date**: January 2025

**Context**: The original template had hardcoded model strings like `anthropic/claude-sonnet-4.5-20250929`.

**Rationale**:
- Hardcoded defaults create vendor coupling
- Makes switching providers difficult
- Defaults may become stale/invalid
- Better to fail fast with clear error message

**Implementation**:
- AgentSpec has Optional provider fields
- config.py reads required env vars
- Missing env var → clear error with instructions

**Consequences**:
- Setup requires explicit configuration
- No "it just works" experience
- But: explicit is better than implicit

---

## 6. Monorepo with UV Workspaces

**Decision**: Structure as monorepo with UV workspace support.

**Date**: January 2025

**Context**: The project has multiple components (agent, API, schemas).

**Options Considered**:
1. Single package (too monolithic)
2. Separate repos (coordination overhead)
3. Monorepo with workspaces (balanced)

**Rationale**:
- Single version control for all components
- Shared dependencies via workspace
- Easy cross-package imports
- Atomic commits across components
- UV provides fast, reliable dependency management

**Structure**:
```
packages/
  shared/       # Pydantic schemas
  voice_agent/  # LiveKit agent
  context_builder/  # DSPy
apps/
  api/          # FastAPI
  web/          # Static HTML
```

---

## 7. Evaluation Plan

**Decision**: Evaluate agent quality via transcript analysis and outcome classification.

**Date**: January 2025

**Context**: We need to measure and improve agent performance.

**Metrics**:
- Call completion rate
- Qualification accuracy (vs. human reviewer)
- Average handle time
- User sentiment (from transcript)

**Method**:
1. Record all calls (LiveKit provides this)
2. Run transcripts through classification model
3. Compare predicted qualification status vs. actual outcome
4. A/B test prompt variations

**Tooling**:
- LiveKit Agent testing framework for unit tests
- Custom eval scripts for batch analysis
- Dashboard for metrics (future)

---

## 8. Lead Model Design

**Decision**: Phone is required, name is optional.

**Date**: January 2025

**Context**: Designing the Lead schema.

**Rationale**:
- Real inbound leads often don't have names attached
- Phone number is the only truly required identifier
- Making name optional prevents data entry friction
- Other fields (company, email) also optional

**Implementation**:
```python
class Lead(BaseModel):
    phone: str  # Required
    name: Optional[str] = None
    company: Optional[str] = None
    ...
```

---

## 9. CallJob References Context (Not Embeds)

**Decision**: CallJob stores `context_instance_id`, not embedded ContextInstance.

**Date**: January 2025

**Context**: Designing the relationship between CallJob and ContextInstance.

**Options Considered**:
1. Embed full ContextInstance in CallJob
2. Reference by ID only
3. Reference by ID + optional file path

**Rationale**:
- Embedded approach bloats records
- Context can be large (questions, handlers)
- Separating allows independent storage
- File path enables MVP file-based approach

**Implementation**:
```python
class CallJob(BaseModel):
    context_instance_id: UUID  # Reference
    context_instance_path: Optional[str] = None  # File path for MVP
```

---

## 10. Compatibility Shim for Entrypoints

**Decision**: Preserve `python src/agent.py dev` command after restructure.

**Date**: January 2025

**Context**: Moving agent code to packages/voice_agent/ would break existing commands.

**Rationale**:
- Users expect original command to work
- Documentation references original path
- Smooth transition for existing users

**Implementation**:
- `packages/voice_agent/src/agent.py` is a shim
- Imports and forwards to `voice_agent.agent`
- Both entry points work:
  - `python src/agent.py dev` (original)
  - `python -m voice_agent.agent dev` (new)
