# Research-Based Upgrades: Master Overview

A single-page overview of ALL researched improvements, upgrades, and changes — completed, in-progress, and planned. Each section links to the deeper detail document where applicable.

**Last Updated:** February 4, 2026

---

## How to Use This Document

This is the **big picture checklist**. For deep details on any item, see the linked document. Items are grouped by domain and marked with status:

- [x] **DONE** — Implemented and verified
- [ ] **TODO** — Researched, agreed upon, not yet implemented
- [ ] ~~**DEFERRED**~~ — Considered but intentionally postponed

---

## 1. Conversational Intelligence Architecture

> Research: Exhaustive deep-dive across Bland AI, Retell AI, Vapi, Air AI, Synthflow, Hume AI, Sierra AI, Reddit, HN, arXiv papers, LiveKit docs (Feb 2026)
>
> **Core insight**: Interruption handling is table stakes. The goal is making the call *indistinguishable from a human*. This requires conversational intelligence across multiple dimensions — not just good TTS and low latency.

### 1.1 Multi-Agent Workflow Architecture

**Status:** DONE — Implemented in both package agent and production agent

**Problem:** Current agent uses one monolithic prompt with all instructions. This means the LLM carries irrelevant context for each conversation phase (closing instructions during greeting, pricing during discovery, etc.)

**Solution:** LiveKit handoffs/tasks — split into specialized agents per conversation phase:

```
GreetingAgent → DiscoveryAgent → PitchAgent → CloseAgent
```

Each agent has:
- Tightly scoped instructions (only what's relevant to its phase)
- Phase-specific tools (only what it needs)
- Handoff conditions (when to transfer to the next phase)

**Why this matters for naturalness:** Smaller, focused prompts produce better responses. The agent doesn't get confused by instructions for phases that haven't happened yet. Bland AI's "Conversational Pathways" and Sierra AI's "Constellation of Models" both follow this pattern.

**LiveKit features available:**
- `Agent` with `on_enter()` for phase transitions
- `@function_tool()` returning another Agent for handoffs
- `chat_ctx` preservation across handoffs (conversation history flows through)
- `session.userdata` (typed dataclass) for structured state across all agents
- `AgentTask` for discrete data collection (email, name, budget)
- `TaskGroup` for multi-step ordered flows with regression support

**File to change:** `packages/voice_agent/src/voice_agent/agent.py` — replace single `Assistant` class

- [x] Design agent graph: GreetingAgent → DiscoveryAgent → PitchAgent → CloseAgent
- [x] Implement each agent with scoped instructions and tools
- [ ] Use `AgentTask` for discrete data collection (email capture, meeting booking)
- [x] Pass `chat_ctx` on handoffs for context continuity
- [x] Use `session.userdata` dataclass for lead info across agents
- [x] Write TDD tests for each handoff transition
- [ ] Test: seamless transitions (no voice change, no delay, no visible handoff)

### 1.2 Spoken-Language Prompting

**Status:** DONE — VOICE_RULES constant applied to all agent prompts

**Problem:** LLM responses sound *written*, not *spoken*. Perfect grammar, formal structure, lists, long sentences — all unnatural on a phone call.

**Techniques from Vapi, Retell, ElevenLabs prompting guides:**

| Written (Bad) | Spoken (Good) |
|---------------|---------------|
| "I would be happy to assist you with that." | "Sure, I can help with that." |
| "Do not hesitate to ask." | "Just let me know." |
| "Here are three options: 1) ... 2) ... 3) ..." | "So the main option is... and there's also..." |
| "I will" | "I'll" |
| "Cannot" | "Can't" |

**Rules to add to all agent prompts:**
- Use simple vocabulary and short sentences (1-3 sentences max per turn)
- Never use bullet points, numbered lists, or formatted text
- Use contractions ("don't" not "do not", "I'll" not "I will")
- Start responses with acknowledgments: "Got it", "Okay", "Sure"
- Use transitions: "So", "Actually", "Well"
- Ask ONE question at a time
- Spell out numbers, phone numbers, email addresses
- No acronyms or words with unclear pronunciation
- Voice-optimized prompts should be 60-70% shorter than text equivalents

- [x] Rewrite all agent instructions using spoken-language rules
- [x] Add system-level "voice output rules" to every agent prompt (`VOICE_RULES` constant)
- [ ] Test: read all generated responses aloud — if it sounds weird, rewrite

### 1.3 Backchanneling & Active Listening

**Status:** TODO — Major naturalness improvement

**Problem:** Current agent is silent while the caller speaks. Real humans say "mmhmm", "right", "I see", "yeah" to signal they're listening. Without these, callers feel like they're talking into a void.

**Research findings:**
- 40%+ of human conversation turns involve overlapping speech (backchannels)
- Sentiment-matched backchannels ("oh wow!", "oh no...") make speakers feel more understood than neutral ones ("mmhmm")
- Academic research (arXiv 2025) shows timing prediction via LSTM/RL for when to backchannel

**LiveKit implementation approach:**
- Use `BackgroundAudioPlayer` to play pre-recorded backchannel clips
- Trigger on `user_state_changed` events during user speech
- Map detected sentiment to backchannel type (positive → "oh nice!", negative → "I understand", neutral → "mmhmm")

**Also: Paraphrasing before responding:**
- "So what you're saying is..." / "Let me make sure I've got this right..."
- Add instruction to agents: acknowledge what the caller said before giving your own response

- [ ] Record/source backchannel audio clips ("mmhmm", "right", "I see", "oh nice", "I understand")
- [ ] Implement `BackgroundAudioPlayer` with on-demand backchannel playback
- [ ] Build backchannel timing logic (trigger during natural pauses in caller speech)
- [ ] Add paraphrasing instruction to discovery/qualification agents
- [ ] Test: does the caller feel heard? Does it interrupt or help?

### 1.4 Prosody & Speech Pattern Control

**Status:** TODO — Avoids the "AI cadence" problem

**Problem:** AI voices fail when they're *too smooth*. Human speech has variable pacing, emphasis, micro-pauses, pitch shifts. When AI is perfectly consistent, it enters uncanny valley.

**Techniques:**
- **Variable pacing**: Slower for important info, faster for acknowledgments (human avg 150 WPM, AI tends to 180 WPM — slow down)
- **Strategic pausing**: Non-uniform pauses between sentences (uniform pauses = dead giveaway)
- **Pitch variation**: Excitement raises pitch, seriousness lowers it
- **SSML controls**: `<break>`, `<prosody rate>`, `<emphasis>` tags for specific phrases
- **Filler words**: "umm", "so", "well" at response starts — masks processing delay and sounds natural (ACM study confirms shorter perceived wait time). But don't overdo it.
- **Speed matching**: Adapt speech rate to match the caller's pace — mismatched speed is a top cue that reveals AI

**What TTS providers support:**
- ElevenLabs: Stability parameter for dynamic range, voice cloning
- Cartesia Sonic 3: Speed/volume float, emotion control (beta), SSML
- Hume OCTAVE: Full natural-language emotion description, speed 0.25-3.0x
- Azure: Full SSML prosody control

- [ ] Add SSML `<break>` tags for natural pauses in key phrases (greetings, closings)
- [ ] Tune TTS speed slightly slower than default (closer to 150 WPM)
- [ ] Add filler words to LLM prompts for response starts ("So," "Well," "Hmm,")
- [ ] Test speed matching: detect caller's pace and adjust
- [ ] Use `tts_node` override for custom pronunciation dictionary

### 1.5 Emotional Intelligence

**Status:** TODO — Differentiator for sales calls

**Problem:** Current agent responds the same way regardless of caller's emotional state. A frustrated caller gets the same energy as an enthusiastic one.

**Research findings:**
- Hume AI detects 48+ emotional dimensions (not just positive/negative/neutral)
- Vocal cues: tone, pitch, speed, pauses, sighs, laughs — "how something is said, not just what"
- Hume's OCTAVE TTS model generates emotionally-aware speech via natural language description

**Implementation approach:**
1. **Input-side**: Detect caller emotion from speech patterns (pitch tracking, pace changes, volume)
   - Rapid speech + high pitch = excitement or stress
   - Slow speech + low volume = disinterest or sadness
   - Sighs = frustration
2. **Response adaptation**:
   - Frustration detected → empathize, slow down, simplify
   - Interest/enthusiasm → match energy, advance the pitch
   - Confusion → rephrase, break into smaller steps
3. **Output-side**: Control TTS emotion
   - Hume TTS: `description="The voice is warm, enthusiastic, and encouraging."`
   - Can update mid-session: `session.tts.update_options(description="...")`

- [ ] Evaluate Hume TTS as primary or secondary TTS (vs ElevenLabs quality)
- [ ] Implement basic emotion detection from speech patterns (pace, pitch, volume)
- [ ] Add emotion-adaptive instructions to agents ("If the caller sounds frustrated, empathize first")
- [ ] Test: does emotional adaptation improve call outcomes?

### 1.6 Turn-Taking Intelligence

**Status:** DONE — Tuned in both agents with sales-optimized thresholds

**Current setup:** Silero VAD + MultilingualModel turn detector. This is solid.

**What we can improve:**

| Approach | Description | Source |
|----------|-------------|--------|
| **Tune endpointing delays** | `min_endpointing_delay=0.5`, `max_endpointing_delay=3.0` — adjust for your caller population | LiveKit docs |
| **False interruption handling** | `resume_false_interruption=True`, `false_interruption_timeout=2.0` — auto-resume after noise/coughs | LiveKit v1.3.7 |
| **Non-interruptible greetings** | `allow_interruptions=False` on initial greeting | LiveKit v1.3.7 |
| **Wait for user silence** | Agent waits for user to fully finish before speaking | LiveKit v1.3.7 |

**Community thresholds:**
- 100ms: Too aggressive for conversation
- 255ms: Sweet spot for English speakers (tested across 50k+ calls)
- 800ms: Definitive completion signal

**Research (Stanford):** Instead of "can I speak now?", continuously predict "in how many seconds can I speak?" — allows pre-generating responses before the speaker finishes.

- [x] Tune `min_endpointing_delay=0.6` for sales conversation (conservative to avoid cutting people off)
- [x] Enable `resume_false_interruption=True` with `false_interruption_timeout=1.5`
- [x] Set `min_interruption_words=2` to avoid reacting to noise/coughs
- [x] Set `min_interruption_duration=0.8` for additional noise filtering
- [x] Tune VAD `activation_threshold=0.6` and `min_silence_duration=0.6` for telephony
- [ ] Set greeting to `allow_interruptions=False` (for outbound calls)
- [ ] Test turn-taking on actual phone calls with various speaker styles

### 1.7 Speculative Pre-Generation

**Status:** PARTIAL — `preemptive_generation=True` + `FlushSentinel` imported, ready for external API tools

**What's already working:** LiveKit's `preemptive_generation=True` starts LLM before end-of-turn is confirmed.

**What we can add:**

1. **FlushSentinel** (LiveKit v1.3.3) — Emit a quick acknowledgment before the full response:
   ```python
   yield "Let me check on that for you."
   yield FlushSentinel()  # Flush to TTS immediately
   # Continue generating the full response...
   ```

2. **Speculative tool calling** — Run tool calls in parallel while speaking a filler:
   - Track A: "Let me look that up" → TTS immediately
   - Track B: Tool execution in background, result woven into next sentence

3. **TTS caching** — Pre-compute frequent phrases (greetings, "one moment please", "great question") for zero-latency playback

- [ ] Implement `FlushSentinel` for tool-call responses ("Let me check..." then actual answer)
- [ ] Cache common greeting/closing TTS audio
- [ ] Consider speculative tool calling for lookup-heavy conversations

### 1.8 Background Audio & Thinking States

**Status:** DONE — BackgroundAudioPlayer with office ambience + keyboard typing in both agents

**Problem:** Silence during LLM processing feels like a dead line. Callers wonder if the call dropped.

**LiveKit provides:**
- `BackgroundAudioPlayer` with built-in clips:
  - `OFFICE_AMBIENCE` — subtle background office noise
  - `KEYBOARD_TYPING` / `KEYBOARD_TYPING2` — operator typing sounds
- Automatically plays "thinking sounds" during tool calls and LLM inference

- [x] Add `BackgroundAudioPlayer` with ambient office sound (volume=0.15 for subtlety)
- [x] Enable keyboard typing sounds during thinking states (70/30 probability split)
- [ ] Test: does it help or distract on phone calls? Adjust volume if needed

### 1.9 Memory & Context Compression

**Status:** TODO — Prevents instruction drift in long calls

**Problem:** After 5-7 conversation turns, the context window fills up and the LLM loses adherence to system instructions. The original prompt gets pushed out of attention.

**Techniques:**
- **Structured dialogue state tracking** — JSON object tracking: what's been collected, what remains, current phase
- **Context compression** — Summarize earlier conversation while preserving key facts and emotional context
- **Explicit state in `session.userdata`** — Typed dataclass persisting across all agents
- **Refer back naturally** — "Since you mentioned you prefer mornings..." rather than re-asking

- [ ] Implement `session.userdata` dataclass for call state (collected info, current phase, lead sentiment)
- [ ] Add context compression for conversations exceeding 5-7 turns
- [ ] Add "no repetition" instruction — don't re-ask questions already answered
- [ ] Test: 10-minute call maintains instruction adherence

---

## 2. Voice AI Stack Upgrades

> Research: Voice stack deep-dive across forums, Reddit, articles, LiveKit docs (Feb 2026)

### 2.1 TTS: Deepgram Aura → ElevenLabs Turbo v2.5

**Status:** DONE — Production uses ElevenLabs plugin; package agent uses inference module (config-driven)

| Aspect | Current | Upgrade |
|--------|---------|---------|
| Provider | Deepgram Aura (`aura-asteria-en`) | ElevenLabs Turbo v2.5 |
| Latency | ~200ms TTFB | ~200ms TTFB (comparable) |
| Quality | Robotic on phone audio | Best-in-class: natural prosody, emotional range, most human-sounding |
| Plugin | `livekit-plugins-deepgram` | `livekit-plugins-elevenlabs` |
| Voice cloning | No | Yes — custom brand voice possible |

**Why:** ElevenLabs has the highest perceived voice quality of any TTS provider. Multiple independent confirmations place it as the #1 TTS for natural-sounding voice AI.

**Alternatives considered:**
- Cartesia Sonic 3 — Lowest latency (~130ms TTFB), good quality, cheaper. Best if latency is the primary bottleneck.
- Hume OCTAVE — Most expressive (natural language emotion control). Consider as secondary for emotion-heavy phases.
- Rime Arcana v2 — Dark horse for telephony/sales calls, natural cadence

**File to change:** `packages/voice_agent/src/voice_agent/agent.py` line 152

- [x] Install `livekit-plugins-elevenlabs`
- [x] Update TTS in agent pipeline to ElevenLabs Turbo v2.5
- [x] Select voice ID ("Chris" — natural American male, ID: `iP95p4xoKVk53GoZ742B`)
- [x] Update `.env.example` with ElevenLabs env vars (API key, voice ID)
- [x] Package agent uses `inference.TTS(model=config.tts_model, voice=config.voice_id)` — fully config-driven
- [ ] Test voice quality on actual phone call
- [ ] Compare latency vs Cartesia Sonic 3 on real calls (fallback if latency is too high)

### 2.2 STT: Deepgram Nova-2 → Deepgram Nova-3

**Status:** DONE — Updated in production agent; package agent uses config-driven inference

| Aspect | Current | Upgrade |
|--------|---------|---------|
| Model | `nova-2` | `nova-3` |
| Accuracy | Good | ~7% lower WER |
| Change | One line | One line |

- [x] Change `model="nova-2"` to `model="nova-3"` in production agent
- [x] Package agent uses `inference.STT(model=config.stt_model)` — set via `VOICE_AGENT_STT_MODEL` env var
- [ ] Verify streaming still works correctly
- [ ] Test with accented speech

### 2.3 LLM: GPT-4o-mini (Keep or Evaluate)

**Status:** TODO — Evaluate alternatives

| Option | Speed | Quality | Cost | Notes |
|--------|-------|---------|------|-------|
| GPT-4o-mini (current) | Good | Good | Low | Solid default |
| Claude 3.5 Haiku | Comparable | Better instruction following | Low | Better for structured sales scripts |
| Groq Llama 3.3 70B | ~241 tok/s | Good | Low | Fastest, less capable |
| Cerebras | ~450 tok/s | Good | Varies | Fastest available, limited models |

- [ ] Benchmark GPT-4o-mini vs Claude Haiku on sales call transcripts
- [ ] Measure actual LLM latency in production calls
- [ ] Decide based on benchmarks

### 2.4 Speech-to-Speech (S2S)

**Status:** TODO — Evaluate Gemini Live for GreetingAgent phase

S2S models bypass the STT→LLM→TTS pipeline entirely. For structured sales calls (discovery, pitch, close), the cascading pipeline gives more control. However, for unstructured phases (greeting, small talk), S2S models offer significantly lower latency.

**Gemini Live API** (strongest candidate): LiveKit has a mature [Gemini plugin](https://docs.livekit.io/agents/models/realtime/plugins/gemini/) with:
- Native VAD and turn detection (built-in, no separate model needed)
- **Affective dialog** — emotional awareness in conversation (`enable_affective_dialog=True`)
- **Proactivity** — model decides when to respond vs. stay silent (`proactivity=True`)
- **Half-cascade mode** — Gemini for listening + separate TTS (ElevenLabs) for output quality
- **Tool calling** — supports function tools within the realtime session
- **Thinking mode** — `thinking_config` for complex reasoning
- Docs: https://ai.google.dev/gemini-api/docs/live

**Recommended approach:** Use Gemini Live for GreetingAgent (unstructured, latency-sensitive) and keep STT-LLM-TTS pipeline for DiscoveryAgent, PitchAgent, CloseAgent (structured, tool-heavy).

```python
# Half-cascade: Gemini listens + ElevenLabs speaks
from google.genai.types import Modality
session = AgentSession(
    llm=google.realtime.RealtimeModel(modalities=[Modality.TEXT]),
    tts="elevenlabs/turbo-v2.5",
)
```

- [ ] Install `livekit-agents[google]~=1.3` and set `GOOGLE_API_KEY`
- [ ] Prototype GreetingAgent with Gemini Live (half-cascade: Gemini + ElevenLabs TTS)
- [ ] Test affective dialog and proactivity features
- [ ] Compare latency vs current STT→LLM→TTS pipeline
- [ ] ~~Experiment with OpenAI Realtime~~ (less control, higher cost)
- [ ] ~~Test PersonaPlex 7B~~ (not yet production-ready)

---

## 3. What Doesn't Work (Anti-Patterns)

> From community research: Reddit, HN, production experience from Bland/Retell/Vapi

| Anti-Pattern | Why It Fails |
|-------------|-------------|
| **"Faster = better" obsession** | Below ~300ms, speed improvements are invisible. A 1.5s delay was rated *better* than shorter delays in studies. Rhythm matters more than raw speed. |
| **Over-engineering multi-agent** | Adding agents that don't provide meaningful specialization creates coordination complexity for no gain |
| **Too-perfect speech** | No pauses, no hesitations, no pitch variation = uncanny valley. Sounds *close* to human but every imperfection becomes hyper-noticeable |
| **Formal/written language** | "I would be happy to assist" instead of "Sure, I can help" — dead giveaway |
| **Overusing fillers** | Too many "uh"s sound more scripted than none at all |
| **Uniform pauses** | Equal spacing between all sentences = instant AI detection |
| **Vague base prompts** | Generic instructions produce generic (bad) responses |
| **US-only testing** | EMEA carrier paths have higher latency — test internationally |
| **Over-indexing on model intelligence** | "Latency, turn-taking, barge-in, state handling end up mattering more than prompt quality once you put traffic on a phone line" (HN) |

---

## 4. UX Heuristic Audit Findings

> Detail: `docs/UX_HEURISTIC_AUDIT.md`
> Overall Score: 2.59/5.0 (52%) — Needs Significant Improvement

### 4.1 Critical (Must Fix Before Launch)

- [ ] **Create privacy policy & terms of service** — Legal/trust (AI-4, AI-5)
- [x] **Add help/documentation section** — FAQ section with 6 questions on landing page
- [x] **Rewrite error messages in conversational language** — Already uses "International format: +1 555 123 4567"

### 4.2 High Priority

- [ ] **Real-time validation feedback** — Green checkmarks on valid input (H1, H5)
- [ ] **Call monitoring/stop capability** — Users can't stop call once submitted (AI-2)
- [ ] **Post-call feedback mechanism** — "How did the AI perform?" (AI-2)
- [ ] **FAQ section** — "What happens after I submit?" (H10)
- [ ] **Data retention information** (AI-4)
- [ ] **Cancel call option** — After submission, before call starts (H3)
- [ ] **Click progress dots to jump to any step** (H3)
- [ ] **Edit links in summary step** (H3)
- [ ] **Tooltips on complex fields** (H10)
- [ ] **Disclose third-party services** — LiveKit, Deepgram, OpenAI (AI-4)

### 4.3 Medium Priority

- [ ] Phone number auto-formatting (H5)
- [ ] Skeleton loading states (H1)
- [ ] Confirmation modal before submission (H5)
- [ ] Mini-summary sidebar (H6)
- [ ] Content moderation for product context (AI-6)
- [ ] Multi-language support (AI-3)
- [ ] Do Not Call list integration (AI-7)
- [ ] Recipient opt-out mechanism (AI-7)

### 4.4 Low Priority

- [ ] CSV import for leads (H7)
- [ ] Keyboard shortcuts (H7)
- [ ] Template saving (H7)
- [ ] AI confidence indicators (AI-1)

---

## 5. World-Class UX Analysis

> Detail: `docs/WORLD_CLASS_UX_ANALYSIS.md`

### 5.1 Critical — First Impression

- [ ] Hero section with clear value proposition
- [ ] Trust signals (logos, testimonials, security badges)
- [ ] Success metrics ("X calls made")
- [ ] Hero visual (product demo, animated preview)

### 5.2 High Priority — Form & Visual

- [ ] Improved error messages (human-readable)
- [ ] Success feedback (green checkmarks)
- [ ] Glassmorphism depth & layering
- [ ] Skeleton loading states
- [ ] Success celebration animation
- [ ] Loading state with progress ("Building your AI agent...")
- [ ] ARIA labels, screen reader support, 44px touch targets

### 5.3 Advanced

- [ ] Product demo video/animation
- [ ] Dashboard for call history
- [ ] A/B testing framework
- [ ] Multi-language support

---

## 6. Architecture & Data Model

> Detail: `docs/LOGIC_REVIEW_METHODOLOGY.md`, `docs/architecture.md`, `docs/decision-log.md`

### 6.1 Completed

- [x] Per-lead architecture (Lead model, per-lead context, API validation, web form)
- [x] Logic review methodology document
- [x] API processes ALL leads with BatchCallResponse (was critical bug: only first lead processed)
- [x] Batch success UI in web form (per-lead call results)
- [x] lead_title personalization in GreetingAgent
- [x] All 182 tests passing, lint/format clean

### 6.2 Remaining

- [ ] **Batch submission endpoint** — `POST /submissions`
- [ ] **Context injection via API** — Replace `--context file.json` with `--call-job-id <id>`
- [ ] **Idempotency key enforcement**
- [ ] **Outcome enum standardization**
- [ ] **localStorage TTL** (30 min expiry)

---

## 7. Agent Testing (TDD)

> Per AGENTS.md: "Never just guess what will work. Always use test-driven development."

LiveKit provides a built-in testing framework:

```python
@pytest.mark.asyncio
async def test_greeting():
    async with AgentSession(llm=llm) as session:
        result = await session.run(user_input="Hello")
        await result.expect.next_event().is_message(role="assistant").judge(
            llm, intent="Makes a friendly introduction"
        )
```

- [ ] Write tests for each agent phase (greeting, discovery, pitch, close)
- [ ] Write tests for handoff transitions
- [ ] Write tests for objection handling paths
- [ ] Write tests for emotion-adaptive responses
- [ ] Use `mock_tools()` for tool-dependent tests
- [ ] Set up `LIVEKIT_EVALS_VERBOSE=1` for debugging

---

## 8. Legal & Compliance

- [ ] **TCPA compliance** — Verify against FCC requirements
- [ ] **GDPR compliance** — Data export, deletion, retention policy
- [ ] **Terms of service**
- [ ] **Do Not Call list** integration
- [ ] **Recipient complaint mechanism**

---

## 9. Infrastructure & DevOps

- [ ] WebSocket real-time call status
- [ ] Call recording storage (LiveKit recordings via API)
- [ ] Monitoring dashboard (call volumes, success rates, latency)
- [ ] Error alerting
- [ ] Docker production deployment (docker-compose for full stack)
- [ ] CI/CD pipeline

---

## 10. Metrics to Track

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Form completion rate | >70% | Analytics |
| End-to-end voice latency | <500ms | LiveKit metrics |
| Turn-taking accuracy | >90% correct | Transcript analysis |
| Call completion rate | >80% | Call outcome tracking |
| "AI detection" rate | <20% | Blind test with humans |
| Caller satisfaction | >4/5 | Post-call survey |
| Objection handling success | >50% | Transcript classification |
| NPS | >50 | Post-call survey |

---

## Document Map

| Document | Purpose | Status |
|----------|---------|--------|
| `docs/RESEARCH_BASED_UPGRADES.md` | **This file** — Master overview | Living document |
| `docs/UX_HEURISTIC_AUDIT.md` | Nielsen's 10 + AI ethics deep audit | Complete |
| `docs/WORLD_CLASS_UX_ANALYSIS.md` | Comparison vs world-class UX standards | Complete |
| `docs/LOGIC_REVIEW_METHODOLOGY.md` | Anti-patterns and review process | Complete |
| `docs/architecture.md` | System architecture diagram | Complete |
| `docs/decision-log.md` | Engineering decision rationale | Complete |
| `docs/MIGRATION.md` | Migration notes | Complete |

---

## Implementation Priority Order

1. ~~**Multi-agent workflow** (1.1)~~ — DONE
2. ~~**Spoken-language prompting** (1.2)~~ — DONE
3. ~~**ElevenLabs TTS + Nova-3 STT** (2.1, 2.2)~~ — DONE
4. ~~**Turn-taking tuning** (1.6)~~ — DONE
5. **Speculative pre-generation / FlushSentinel** (1.7) — Hide latency behind speech
7. **Backchanneling** (1.3) — "mmhmm", "right" during caller speech
8. ~~**Background audio / thinking states** (1.8)~~ — DONE
9. **Prosody control** (1.4) — Variable pacing, filler words, SSML breaks
10. **Emotional intelligence** (1.5) — Detect and adapt to caller mood
11. **Memory & context compression** (1.9) — Long call stability
12. **UX critical fixes** (4.1) — Error messages, help section, validation feedback
13. **Hero section + trust signals** (5.1) — Web conversion
14. **Agent TDD tests** (7) — Quality assurance for all above changes

---

## 11. Engineering Commit & Release Discipline

> This section codifies the exact commit workflow followed on every change. It is the standard this project holds itself to — no exceptions.

### 11.1 Pre-Commit Checklist

Before staging any files, **always** run through this checklist:

| # | Check | Command / Method | Severity |
|---|-------|------------------|----------|
| 1 | **No secrets in repo** — API keys, private keys, tokens, .env files, SSH keys, credentials.json | `git diff --cached --name-only` — scan for `.env`, `*.pem`, `*.key`, `id_rsa*`, `credentials*`, `secret*` | **CRITICAL** |
| 2 | **No large binaries** — model weights, audio files, images not in .gitignore | Check for files > 1MB: `find . -size +1M -not -path './.git/*'` | HIGH |
| 3 | **Linter passes** — zero warnings, zero errors | `task lint` or `uv run ruff check .` | HIGH |
| 4 | **Formatter applied** — consistent style | `task format` or `uv run ruff format .` | HIGH |
| 5 | **Tests pass** — all unit/eval tests green | `task test` or `uv run pytest` | HIGH |
| 6 | **Type check** (if applicable) | `uv run mypy .` or type-checked by IDE | MEDIUM |
| 7 | **No debug artifacts** — print statements, TODO hacks, commented-out code blocks | Manual review of `git diff --cached` | MEDIUM |
| 8 | **Lock file in sync** — if dependencies changed | `uv lock` → verify `uv.lock` is current | MEDIUM |
| 9 | **.gitignore coverage** — new file types properly ignored | Review `.gitignore` for new patterns | LOW |
| 10 | **No unintended file changes** — only stage what's relevant to this commit | `git status` → review every file | LOW |

### 11.2 Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/) strictly:

```
<type>(<scope>): <short description in imperative mood>

<optional body — what changed and WHY>

<optional footer — breaking changes, issue refs>

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

**Types:**
| Type | When to Use |
|------|-------------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code restructuring (no behavior change) |
| `test` | Adding or updating tests |
| `docs` | Documentation only |
| `chore` | Dependencies, config, tooling |
| `perf` | Performance improvement |
| `ci` | CI/CD pipeline changes |
| `style` | Formatting only (no logic change) |
| `security` | Security fix or hardening |

**Scopes (this project):** `agent`, `api`, `web`, `shared`, `context-builder`, `docs`, `infra`, `deps`

**Examples:**
```
feat(agent): implement multi-agent workflow with 4-phase handoffs
refactor(agent): replace monolithic Assistant with GreetingAgent → CloseAgent pipeline
fix(api): process all leads instead of only the first
test(agent): add eval tests for multi-agent greeting and discovery phases
docs: add engineering commit discipline to master plan
chore(deps): upgrade livekit-agents to 1.3.12
security: exclude SSH keys from repo, add to .gitignore
```

### 11.3 Atomic Commits

Each commit should be a **single logical change**. Never bundle unrelated changes.

**Good:**
- Commit 1: `feat(agent): implement multi-agent workflow`
- Commit 2: `test(agent): add eval tests for multi-agent`
- Commit 3: `docs: update master plan with commit methodology`

**Bad:**
- One commit: "implemented multi-agent, updated tests, fixed API, added docs"

### 11.4 Security Scanning

**Before every commit:**

1. **Scan for secrets:**
   - No `.env`, `.env.local`, `.env.production` files
   - No SSH keys (`id_rsa`, `id_ed25519`, `*.pem`, `*.key`)
   - No API keys or tokens in source code (search for `sk-`, `AKIA`, `Bearer `)
   - No credentials files (`credentials.json`, `service-account.json`)

2. **Verify .gitignore:**
   ```gitignore
   # Must always be present:
   .env
   .env.*
   *.pem
   *.key
   id_rsa*
   id_ed25519*
   credentials*.json
   ```

3. **If secrets were accidentally committed:**
   - Rotate the credentials IMMEDIATELY
   - Use `git filter-branch` or BFG Repo Cleaner to purge from history
   - Force push only after confirming no one has pulled

### 11.5 Branching & Push Strategy

| Branch | Purpose | Push Rules |
|--------|---------|------------|
| `main` | Production-ready code | Protected. Only via PR or verified pushes. Never force push. |
| `feat/*` | Feature development | Push freely. Rebase before merge. |
| `fix/*` | Bug fixes | Push freely. Rebase before merge. |
| `chore/*` | Maintenance | Push freely. |

**Push checklist:**
- [ ] All pre-commit checks pass
- [ ] Commit messages follow convention
- [ ] No force push to `main` without explicit agreement
- [ ] Remote is correct (`git remote -v` — don't push to wrong remote)

### 11.6 When to Commit

Commit at these natural boundaries:

1. **After completing a logical unit of work** — one feature, one fix, one refactor
2. **After tests pass** — never commit broken tests
3. **Before switching context** — save your work before moving to a different task
4. **After major research/documentation** — capture knowledge immediately
5. **Before risky changes** — create a known-good checkpoint

### 11.7 Code Review Mindset (Self-Review)

Before staging, mentally review as if you're reviewing someone else's PR:

- [ ] Does this change do what it's supposed to? Nothing more, nothing less.
- [ ] Are there any regressions? Could this break existing functionality?
- [ ] Is the code readable without explanation?
- [ ] Are error paths handled?
- [ ] Are there any TODO/FIXME/HACK comments that should be resolved?
- [ ] Is test coverage adequate for the change?

### 11.8 Release Tags

For significant milestones, create annotated tags:

```bash
git tag -a v0.2.0 -m "Multi-agent workflow, spoken-language prompts, per-lead architecture"
git push origin v0.2.0
```

**Semantic versioning:**
- `MAJOR.MINOR.PATCH`
- PATCH: bug fixes
- MINOR: new features (backward compatible)
- MAJOR: breaking changes

---

## Sources

### Company Architectures
- Bland AI: Conversational Pathways (visual flowchart nodes)
- Sierra AI: Constellation of Models (multi-model routing by task complexity)
- Retell AI: Conversation Flows + Knowledge Base (structured nodes, anti-hallucination)
- Air AI: Infinite Memory Architecture (10-40 min calls)
- Synthflow AI: BELL Framework, GPT-4o + ElevenLabs

### Academic Research
- Stanford HAI: Continuous turn prediction ("in how many seconds can I speak?")
- NVIDIA PersonaPlex: 7B full-duplex model, 170ms turn-taking latency (ICASSP 2026)
- arXiv 2025: Sentiment-based backchanneling
- arXiv 2024: Acoustic + LLM fusion for turn-taking/backchannel prediction
- ACM: Conversational fillers reduce perceived latency

### Community Consensus
- "Voice AI doesn't need to be faster. It needs to read the room." (Speechmatics)
- "Latency, turn-taking, barge-in, state handling matter more than prompt quality once you put traffic on a phone line" (HN)
- 1.5s delay rated better than shorter delays in controlled studies
- 255ms endpointing = sweet spot for English (tested across 50k+ calls)
