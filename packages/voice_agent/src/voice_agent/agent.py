"""Voice Agent for AI Lead Qualification System — Multi-Agent Workflow.

Implements a 4-agent conversation flow for natural phone calls:

    GreetingAgent → DiscoveryAgent → PitchAgent → CloseAgent

Each agent has focused instructions and tools for its conversation phase.
Context flows through session.userdata (CallState dataclass).
No DSPy in the real-time loop — context is built before the call starts.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AudioConfig,
    BackgroundAudioPlayer,
    BuiltinAudioClip,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    inference,
    room_io,
)
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from voice_agent.config import ConfigurationError, load_config

logger = logging.getLogger("voice_agent")

# Load environment variables
load_dotenv(".env.local")
# Also try loading from root if we're in packages/voice_agent
load_dotenv("../../.env.local")


# =============================================================================
# Shared Call State
# =============================================================================


@dataclass
class CallState:
    """Shared state across all agents in a call session.

    Stored in session.userdata and accessible by all agents via context.userdata.
    """

    # Pre-built context from DSPy (loaded via --context flag)
    context: dict = field(default_factory=dict)

    # Call tracking
    lead_name: str = ""
    lead_company: str = ""
    lead_title: str = ""
    goal: str = "qualify_interest"
    outcome: str = "pending"

    # Collected during call
    collected_data: dict = field(default_factory=dict)
    lead_email: str | None = None
    objection_reason: str | None = None


RunContext_T = RunContext[CallState]


# =============================================================================
# Voice Output Rules (applied to every agent)
# =============================================================================

VOICE_RULES = """VOICE OUTPUT RULES — follow these in every response:
- Keep responses to 1-3 short sentences per turn.
- Use contractions: "I'm", "don't", "we'll", "that's", "it's", "you're".
- Never output bullet points, numbered lists, or formatted text.
- Start with a brief acknowledgment: "Got it", "Sure", "Right", "Okay".
- Use natural transitions: "So", "Actually", "Well", "Now".
- Ask ONE question at a time. Never ask two questions in one turn.
- Spell out numbers and special characters when saying them.
- Avoid jargon, acronyms, or hard-to-pronounce words.
- Sound like a person on the phone, not a document being read aloud."""


# =============================================================================
# Context Loading
# =============================================================================

_context_instance: dict | None = None


def load_context(context_path: str | None) -> dict | None:
    """Load and validate context from JSON file.

    Args:
        context_path: Path to context JSON file, or None.

    Returns:
        Validated ContextInstance dict, or None if no path provided.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If JSON is invalid or fails schema validation.
    """
    if not context_path:
        return None

    path = Path(context_path)
    if not path.exists():
        raise FileNotFoundError(f"Context file not found: {context_path}")

    try:
        with open(path) as f:
            data = json.load(f)

        # Validate against schema if shared package is available
        try:
            from shared.schemas import ContextInstance

            ContextInstance.model_validate(data)
        except ImportError:
            # shared package not installed, skip validation
            logger.warning("shared package not available, skipping context validation")

        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in context file: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to validate context: {e}") from e


def get_context() -> dict | None:
    """Get the current context instance."""
    return _context_instance


def set_context(context: dict | None) -> None:
    """Set the context instance for this agent run."""
    global _context_instance
    _context_instance = context


# =============================================================================
# Base Agent
# =============================================================================


class BaseCallAgent(Agent):
    """Base agent with shared context access for lead qualification calls."""

    def __init__(self, chat_ctx=None, **kwargs):
        super().__init__(chat_ctx=chat_ctx, **kwargs)

    def _get_state(self) -> CallState:
        """Get shared call state from session userdata."""
        return self.session.userdata

    def _get_ctx(self) -> dict:
        """Get the pre-built context dict."""
        return self._get_state().context


# =============================================================================
# GreetingAgent
# =============================================================================


class GreetingAgent(BaseCallAgent):
    """Opens the call and builds initial rapport.

    For outbound calls: waits for the user to say "Hello?",
    then delivers the opening line from context.
    Hands off to DiscoveryAgent once rapport is established.
    """

    def __init__(self, chat_ctx=None) -> None:
        context = get_context() or {}
        opening_line = context.get("opening_line", "Hi there, how are you doing today?")
        lead_name = context.get("name", "")
        lead_company = context.get("lead_company", "")
        lead_title = context.get("lead_title", "")
        product = context.get("product", "our product")

        # Build personalized lead description
        lead_parts = []
        if lead_name:
            lead_parts.append(lead_name)
        if lead_title:
            lead_parts.append(lead_title)
        if lead_company:
            lead_parts.append(f"at {lead_company}")
        name_note = (
            f"The person you're calling is {', '.join(lead_parts)}. "
            if lead_parts
            else ""
        )

        instructions = f"""{VOICE_RULES}

You're a friendly, professional caller reaching out about {product}.
{name_note}

When the person answers with "Hello?" or similar, respond naturally with:
"{opening_line}"

Then have a brief, warm exchange. Keep it natural — like a real person calling.
Don't rush into business talk. But don't linger — after 2-3 exchanges, move to discovery."""

        super().__init__(instructions=instructions, chat_ctx=chat_ctx)

    async def on_enter(self) -> None:
        """For outbound calls, don't speak first — wait for user's greeting."""
        # User speaks first on outbound calls ("Hello?")
        pass

    @function_tool()
    async def move_to_discovery(self, context: RunContext_T) -> "DiscoveryAgent":
        """Move to the discovery phase after greeting and brief rapport.

        Use this once you've introduced yourself and the person seems engaged.
        """
        return DiscoveryAgent(chat_ctx=self.chat_ctx)


# =============================================================================
# DiscoveryAgent
# =============================================================================


class DiscoveryAgent(BaseCallAgent):
    """Asks qualification questions and discovers the prospect's needs.

    Uses questions from the pre-built context.
    Records answers in shared call state.
    Hands off to PitchAgent once discovery is complete.
    """

    def __init__(self, chat_ctx=None) -> None:
        context = get_context() or {}
        questions = context.get("qualification_questions", [])
        product = context.get("product", "our product")

        question_guidance = ""
        if questions:
            q_lines = "\n".join(f"- {q}" for q in questions)
            question_guidance = f"""Things to find out (ask naturally, don't read from a script):
{q_lines}"""

        instructions = f"""{VOICE_RULES}

You're in the discovery phase of a call about {product}.
Your job is to understand the prospect's situation, needs, and pain points.

{question_guidance}

Rules for this phase:
- Ask ONE question at a time. Wait for the answer.
- Acknowledge what they say before asking the next question.
- Mirror their words back to show you're listening.
- If they mention a pain point, dig deeper: "Tell me more about that."
- Don't interrogate — keep it conversational and curious.
- Record key information they share.
- Once you've covered the important questions and understand their situation, move to the pitch."""

        super().__init__(instructions=instructions, chat_ctx=chat_ctx)

    async def on_enter(self) -> None:
        """Transition smoothly from greeting into discovery."""
        self.session.generate_reply(
            instructions="Transition naturally from the greeting into your first discovery question. Build on what was just discussed."
        )

    @function_tool()
    async def record_info(
        self, context: RunContext_T, field_name: str, value: str
    ) -> str:
        """Record information shared by the prospect.

        Args:
            field_name: Type of info (budget, timeline, decision_maker, pain_point, current_solution, team_size, etc.)
            value: What they said
        """
        state = context.userdata
        state.collected_data[field_name] = value
        return "Recorded. Continue the conversation naturally."

    @function_tool()
    async def move_to_pitch(self, context: RunContext_T) -> "PitchAgent":
        """Move to the pitch phase after understanding the prospect's needs.

        Use this once you've gathered enough information to tailor the pitch.
        """
        return PitchAgent(chat_ctx=self.chat_ctx)


# =============================================================================
# PitchAgent
# =============================================================================


class PitchAgent(BaseCallAgent):
    """Presents the value proposition and handles objections.

    Tailors the pitch to discovered needs.
    Uses objection handlers from context.
    Hands off to CloseAgent when the prospect is ready.
    """

    def __init__(self, chat_ctx=None) -> None:
        context = get_context() or {}
        product = context.get("product", "our product")
        goal = context.get("goal", "qualify_interest")
        objection_handlers = context.get("objection_handlers", {})

        objection_guidance = ""
        if objection_handlers:
            handlers = "\n".join(
                f'- If they say "{k}": {v}' for k, v in objection_handlers.items()
            )
            objection_guidance = f"""If they push back, use these responses naturally (don't read word-for-word):
{handlers}"""

        goal_styles = {
            "book_meeting": "Focus on the value of a deeper conversation. Make the meeting feel low-commitment and worthwhile.",
            "qualify_interest": "Focus on understanding fit. Help them see if this is right for them.",
            "collect_info": "Focus on why sharing information benefits them.",
            "close_sale": "Focus on specific value and urgency. Be assertive but not pushy.",
        }
        pitch_style = goal_styles.get(goal, "Present the value proposition clearly.")

        instructions = f"""{VOICE_RULES}

You're in the pitch phase of a call about {product}.
{pitch_style}

Rules for this phase:
- Connect your pitch to what they told you in discovery. Reference their specific needs and pain points.
- Keep explanations short. One benefit at a time.
- After each point, check in: "Does that make sense?" or "How does that sound?"
- Don't monologue. Keep it interactive and conversational.
- If they push back, acknowledge their concern first, then address it.

{objection_guidance}

Once they seem interested or you've addressed their concerns, move to the close."""

        super().__init__(instructions=instructions, chat_ctx=chat_ctx)

    async def on_enter(self) -> None:
        """Transition into pitch, referencing discovered needs."""
        self.session.generate_reply(
            instructions="Transition naturally from discovery into your pitch. Reference something specific they mentioned and connect it to the value of the product."
        )

    @function_tool()
    async def record_objection(
        self, context: RunContext_T, objection_type: str, details: str
    ) -> str:
        """Record an objection raised by the prospect.

        Args:
            objection_type: Category (price, timing, need_approval, not_interested, need_to_think)
            details: What they specifically said
        """
        state = context.userdata
        state.objection_reason = objection_type
        state.collected_data[f"objection_{objection_type}"] = details
        return "Acknowledged. Address their concern naturally."

    @function_tool()
    async def move_to_close(self, context: RunContext_T) -> "CloseAgent":
        """Move to the closing phase when the prospect seems ready.

        Use this when they express interest, or after handling their objections.
        """
        return CloseAgent(chat_ctx=self.chat_ctx)


# =============================================================================
# CloseAgent
# =============================================================================


class CloseAgent(BaseCallAgent):
    """Executes the call goal and wraps up.

    Goal-specific behavior:
    - book_meeting: Get commitment, collect email, mention booking link
    - qualify_interest: Summarize qualification, discuss next steps
    - collect_info: Confirm all info collected
    - close_sale: Get purchase commitment, collect email, mention payment link
    """

    def __init__(self, chat_ctx=None) -> None:
        context = get_context() or {}
        goal = context.get("goal", "qualify_interest")
        closing_script = context.get(
            "closing_script", "Thanks so much for your time today."
        )
        product = context.get("product", "our product")

        goal_instructions = {
            "book_meeting": """Your goal is to book a meeting.
Ask if they'd like to schedule a time for a deeper conversation.
If yes, collect their email so you can send a calendar link.
Say something like: "I'll send you a link to pick a time that works."
When they give an email, confirm it by spelling it back.""",
            "qualify_interest": """Your goal is to determine if this prospect is qualified.
Based on everything discussed, briefly summarize their situation.
Let them know the next steps.
Thank them for their time.""",
            "collect_info": """Your goal is to confirm you've gathered all needed information.
Briefly summarize what you've learned.
Ask if there's anything they'd like to add.
Thank them for sharing.""",
            "close_sale": """Your goal is to get a purchase commitment.
Ask directly but warmly: "Would you like to move forward with this?"
If yes, collect their email so you can send payment details.
Say something like: "I'll send you everything you need to get started."
When they give an email, confirm it by spelling it back.""",
        }

        instructions = f"""{VOICE_RULES}

You're in the closing phase of a call about {product}.

{goal_instructions.get(goal, "Wrap up the call professionally.")}

When ending the call, say something like:
"{closing_script}"

Keep it brief and natural. Don't repeat things already discussed."""

        super().__init__(instructions=instructions, chat_ctx=chat_ctx)

    async def on_enter(self) -> None:
        """Transition into closing naturally."""
        self.session.generate_reply(
            instructions="Transition naturally to closing. Based on how the conversation went, execute the call goal."
        )

    @function_tool()
    async def record_email(self, context: RunContext_T, email: str) -> str:
        """Record the prospect's email address.

        Args:
            email: The email address they provided
        """
        state = context.userdata
        state.lead_email = email
        state.collected_data["email"] = email
        return "Recorded. Confirm the email by spelling it back, then wrap up the call."

    @function_tool()
    async def end_call_success(self, context: RunContext_T) -> str:
        """End the call successfully — the goal was achieved.

        Use after: meeting booked, lead qualified, info collected, or sale committed.
        """
        state = context.userdata
        goal_outcomes = {
            "book_meeting": "booked",
            "qualify_interest": "qualified",
            "collect_info": "collected",
            "close_sale": "committed",
        }
        state.outcome = goal_outcomes.get(state.goal, "completed")
        return "Say your closing line and end the call warmly."

    @function_tool()
    async def end_call_declined(self, context: RunContext_T, reason: str) -> str:
        """End the call when the prospect declines.

        Args:
            reason: Why they declined (not_interested, bad_timing, too_expensive, need_approval)
        """
        state = context.userdata
        state.outcome = "declined"
        state.objection_reason = reason
        return "Thank them politely for their time and end the call gracefully."


# =============================================================================
# Backward-compatible alias
# =============================================================================


class Assistant(GreetingAgent):
    """Alias for GreetingAgent for backward compatibility with tests."""

    pass


# =============================================================================
# Agent Server Setup
# =============================================================================

server = AgentServer()


def prewarm(proc: JobProcess):
    """Prewarm models for faster startup with telephony-tuned VAD."""
    proc.userdata["vad"] = silero.VAD.load(
        activation_threshold=0.6,
        min_silence_duration=0.6,
    )


server.setup_fnc = prewarm


@server.rtc_session()
async def my_agent(ctx: JobContext):
    """Handle a voice call session with multi-agent workflow."""
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Load configuration from environment
    try:
        config = load_config()
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        raise

    # Initialize shared call state
    context = get_context() or {}
    call_state = CallState(
        context=context,
        lead_name=context.get("name", ""),
        lead_company=context.get("lead_company", ""),
        lead_title=context.get("lead_title", ""),
        goal=context.get("goal", "qualify_interest"),
    )

    # Set up voice AI pipeline using inference module (provider-agnostic via config)
    session = AgentSession[CallState](
        userdata=call_state,
        stt=inference.STT(model=config.stt_model, language=config.language),
        llm=inference.LLM(model=config.llm_model),
        tts=inference.TTS(
            model=config.tts_model,
            voice=config.voice_id,
            language=config.language,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # Turn-taking tuning for natural conversation
        preemptive_generation=True,
        min_interruption_words=2,
        min_interruption_duration=0.8,
        min_endpointing_delay=0.6,
        resume_false_interruption=True,
        false_interruption_timeout=1.5,
    )

    # Background audio: office ambience + typing sounds during thinking
    background_audio = BackgroundAudioPlayer(
        ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.15),
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.6, probability=0.7),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.5, probability=0.3),
        ],
    )

    # Start with GreetingAgent — the first phase of every call
    await session.start(
        agent=GreetingAgent(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: noise_cancellation.BVCTelephony()
                if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                else noise_cancellation.BVC(),
            ),
        ),
    )

    # Start background audio after session is ready
    await background_audio.start(room=ctx.room, agent_session=session)

    # Join the room and connect to the user
    await ctx.connect()


def main():
    """Main entry point with --context flag support."""
    import sys

    # Check for --context flag
    context_path = None
    args = sys.argv[1:]
    new_args = []
    i = 0
    while i < len(args):
        if args[i] == "--context" and i + 1 < len(args):
            context_path = args[i + 1]
            i += 2
        else:
            new_args.append(args[i])
            i += 1

    # Load context if provided
    if context_path:
        try:
            context = load_context(context_path)
            set_context(context)
            logger.info(f"Loaded context from {context_path}")
        except Exception as e:
            logger.error(f"Failed to load context: {e}")
            sys.exit(1)

    # Restore args for CLI
    sys.argv = [sys.argv[0], *new_args]

    # Run the agent
    cli.run_app(server)


if __name__ == "__main__":
    main()
