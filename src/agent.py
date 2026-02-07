"""Production Voice Agent — Multi-Agent Workflow with SIP Telephony.

This is the production entry point that adds SIP outbound dialing, email sending,
and call outcome reporting on top of the multi-agent workflow.

Conversation flow: GreetingAgent → DiscoveryAgent → PitchAgent → CloseAgent

Context is loaded from LiveKit job metadata (set by the API when dispatching calls).
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv
from livekit import api, rtc
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
    get_job_context,
    room_io,
)
from livekit.agents.beta.workflows import GetEmailTask
from livekit.plugins import deepgram, elevenlabs, noise_cancellation, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# Import shared schemas and email sender (graceful fallback if not available)
try:
    from shared.email import send_post_call_emails
    from shared.schemas import CallGoal, CallResult, ContextInstance

    SHARED_AVAILABLE = True
except ImportError:
    SHARED_AVAILABLE = False
    CallGoal = None
    CallResult = None
    ContextInstance = None
    send_post_call_emails = None

logger = logging.getLogger("voice-agent")

if not SHARED_AVAILABLE:
    logger.warning("shared package not available - email sending disabled")

load_dotenv()  # loads .env by default
load_dotenv(".env.local", override=True)  # .env.local overrides if present

# SIP trunk ID for outbound calls
SIP_OUTBOUND_TRUNK_ID = os.getenv("SIP_OUTBOUND_TRUNK_ID", "")

# Demo mode: skip SIP dialing, agent waits for browser/sandbox participant
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

# ElevenLabs voice ID for TTS (default: "Chris" — natural American male)
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "iP95p4xoKVk53GoZ742B")


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
# Shared Call State
# =============================================================================


@dataclass
class CallState:
    """Shared state across all agents in a production call session."""

    # Pre-built context
    context: dict = field(default_factory=dict)
    context_instance: object | None = None  # ContextInstance if shared pkg available

    # Call tracking
    lead_name: str = ""
    lead_company: str = ""
    lead_title: str = ""
    goal: str = "qualify_interest"
    outcome: str = "pending"
    call_start_time: datetime | None = None
    participant: rtc.RemoteParticipant | None = None

    # Collected during call
    collected_data: dict = field(default_factory=dict)
    lead_email: str | None = None
    objection_reason: str | None = None


RunContext_T = RunContext[CallState]


# =============================================================================
# Base Agent
# =============================================================================


class BaseCallAgent(Agent):
    """Base agent with shared functionality for production calls."""

    def __init__(self, context: dict, chat_ctx=None, **kwargs):
        self._call_context = context
        super().__init__(chat_ctx=chat_ctx, **kwargs)

    async def hangup(self) -> None:
        """Hang up the call by deleting the room."""
        job_ctx = get_job_context()
        if job_ctx:
            await job_ctx.api.room.delete_room(
                api.DeleteRoomRequest(room=job_ctx.room.name)
            )


# =============================================================================
# GreetingAgent
# =============================================================================


class GreetingAgent(BaseCallAgent):
    """Opens the call and builds initial rapport."""

    def __init__(self, context: dict, chat_ctx=None) -> None:
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

IMPORTANT: This is an outbound call. When the person answers with "Hello?" or similar, respond naturally with:
"{opening_line}"

Then have a brief, warm exchange. Keep it natural — like a real person calling.
Don't rush into business talk. But don't linger — after 2-3 exchanges, move to discovery."""

        super().__init__(context=context, instructions=instructions, chat_ctx=chat_ctx)

    async def on_enter(self) -> None:
        """Record call start time. Don't speak first — user answers first."""
        state: CallState = self.session.userdata
        state.call_start_time = datetime.now(timezone.utc)

    @function_tool()
    async def move_to_discovery(self, context: RunContext_T) -> "DiscoveryAgent":
        """Move to discovery after greeting and brief rapport.

        Use this once you've introduced yourself and the person seems engaged.
        """
        return DiscoveryAgent(context=self._call_context, chat_ctx=self.chat_ctx)


# =============================================================================
# DiscoveryAgent
# =============================================================================


class DiscoveryAgent(BaseCallAgent):
    """Asks qualification questions and discovers needs."""

    def __init__(self, context: dict, chat_ctx=None) -> None:
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
- Once you've covered the important questions, move to the pitch."""

        super().__init__(context=context, instructions=instructions, chat_ctx=chat_ctx)

    async def on_enter(self) -> None:
        """Transition smoothly from greeting into discovery."""
        self.session.generate_reply(
            instructions="Transition naturally from the greeting into your first discovery question."
        )

    @function_tool()
    async def record_info(
        self, context: RunContext_T, field_name: str, value: str
    ) -> str:
        """Record information shared by the prospect.

        Args:
            field_name: Type of info (budget, timeline, decision_maker, pain_point, current_solution, etc.)
            value: What they said
        """
        state = context.userdata
        state.collected_data[field_name] = value
        return "Recorded. Continue the conversation naturally."

    @function_tool()
    async def move_to_pitch(self, context: RunContext_T) -> "PitchAgent":
        """Move to pitch after understanding the prospect's needs.

        Use this once you've gathered enough information to tailor the pitch.
        """
        return PitchAgent(context=self._call_context, chat_ctx=self.chat_ctx)


# =============================================================================
# PitchAgent
# =============================================================================


class PitchAgent(BaseCallAgent):
    """Presents value proposition and handles objections."""

    def __init__(self, context: dict, chat_ctx=None) -> None:
        product = context.get("product", "our product")
        goal = context.get("goal", "qualify_interest")
        objection_handlers = context.get("objection_handlers", {})

        objection_guidance = ""
        if objection_handlers:
            handlers = "\n".join(
                f'- If they say "{k}": {v}' for k, v in objection_handlers.items()
            )
            objection_guidance = f"""If they push back, use these responses naturally:
{handlers}"""

        goal_styles = {
            "book_meeting": "Focus on the value of a deeper conversation. Make the meeting feel low-commitment.",
            "qualify_interest": "Focus on understanding fit. Help them see if this is right for them.",
            "collect_info": "Focus on why sharing information benefits them.",
            "close_sale": "Focus on specific value and urgency. Be assertive but not pushy.",
        }
        pitch_style = goal_styles.get(goal, "Present the value proposition clearly.")

        instructions = f"""{VOICE_RULES}

You're in the pitch phase of a call about {product}.
{pitch_style}

Rules for this phase:
- Connect your pitch to what they told you in discovery.
- Keep explanations short. One benefit at a time.
- After each point, check in: "Does that make sense?" or "How does that sound?"
- Don't monologue. Keep it interactive.
- If they push back, acknowledge first, then address it.

{objection_guidance}

Once they seem interested or you've addressed their concerns, move to the close."""

        super().__init__(context=context, instructions=instructions, chat_ctx=chat_ctx)

    async def on_enter(self) -> None:
        """Transition into pitch, referencing discovered needs."""
        self.session.generate_reply(
            instructions="Transition naturally from discovery into your pitch. Reference something specific they mentioned."
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
        """Move to closing when the prospect seems ready.

        Use this when they express interest or after handling objections.
        """
        return CloseAgent(context=self._call_context, chat_ctx=self.chat_ctx)


# =============================================================================
# CloseAgent
# =============================================================================


class CloseAgent(BaseCallAgent):
    """Executes the call goal and wraps up."""

    def __init__(self, context: dict, chat_ctx=None) -> None:
        goal = context.get("goal", "qualify_interest")
        closing_script = context.get(
            "closing_script", "Thanks so much for your time today."
        )
        product = context.get("product", "our product")

        goal_instructions = {
            "book_meeting": """Your goal is to book a meeting.
Ask if they'd like to schedule a time for a deeper conversation.
If yes, use the collect_email_for_link tool to get their email.
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
If yes, use the collect_email_for_link tool to get their email.
Say something like: "I'll send you everything you need to get started."
When they give an email, confirm it by spelling it back.""",
        }

        instructions = f"""{VOICE_RULES}

You're in the closing phase of a call about {product}.

{goal_instructions.get(goal, "Wrap up the call professionally.")}

When ending the call, say something like:
"{closing_script}"

Keep it brief and natural. Don't repeat things already discussed."""

        super().__init__(context=context, instructions=instructions, chat_ctx=chat_ctx)

    async def on_enter(self) -> None:
        """Transition into closing naturally."""
        self.session.generate_reply(
            instructions="Transition naturally to closing. Execute the call goal."
        )

    @function_tool()
    async def collect_email_for_link(self, context: RunContext_T) -> str:
        """Collect the prospect's email to send them a booking or payment link.

        Use this after they agree to book a meeting or make a purchase.
        """
        state = context.userdata
        goal = state.goal

        if goal == "book_meeting":
            extra_instructions = "The prospect agreed to a meeting. Collect their email for the booking link."
        elif goal == "close_sale":
            extra_instructions = "The prospect committed to purchase. Collect their email for the payment link."
        else:
            extra_instructions = "Collect the prospect's email address."

        try:
            email_result = await GetEmailTask(
                chat_ctx=self.chat_ctx, extra_instructions=extra_instructions
            )
            state.lead_email = email_result.email_address
            state.collected_data["email"] = email_result.email_address

            if goal == "book_meeting":
                return f"Got it, I'll send the booking link to {email_result.email_address} right away."
            elif goal == "close_sale":
                return f"Perfect, I'll send the payment link to {email_result.email_address} right now."
            else:
                return f"Thanks, I've got your email as {email_result.email_address}."
        except Exception as e:
            logger.error(f"Failed to collect email: {e}")
            return "I didn't catch that. Could you spell out your email for me?"

    @function_tool()
    async def record_collected_info(
        self, context: RunContext_T, field_name: str, field_value: str
    ) -> str:
        """Record information collected from the prospect.

        Args:
            field_name: The name of the field being collected
            field_value: The value provided by the prospect
        """
        state = context.userdata
        state.collected_data[field_name] = field_value
        return "Recorded. Continue the conversation."

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
# Agent Server Setup
# =============================================================================

server = AgentServer()


def prewarm(proc: JobProcess):
    """Prewarm the process with VAD model tuned for telephony."""
    proc.userdata["vad"] = silero.VAD.load(
        activation_threshold=0.6,
        min_silence_duration=0.6,
    )


server.setup_fnc = prewarm


@server.rtc_session(agent_name="voice-agent")
async def voice_agent_session(ctx: JobContext):
    """Main entrypoint for the production voice agent session.

    Loads context from job metadata and creates a multi-agent workflow.
    For outbound calls, dials the phone number via SIP.

    Note: agent_name="voice-agent" enables explicit dispatch via API.
    """
    ctx.log_context_fields = {"room": ctx.room.name}

    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect()

    # Load context from job metadata
    context = {}
    context_instance = None
    phone_number = None
    if ctx.job.metadata:
        try:
            context = json.loads(ctx.job.metadata)
            phone_number = context.get("phone")
            if SHARED_AVAILABLE and ContextInstance is not None:
                try:
                    context_instance = ContextInstance.model_validate(context)
                except Exception as e:
                    logger.warning(f"Failed to parse context as ContextInstance: {e}")
            logger.info(
                f"Loaded context for goal: {context.get('goal')}, phone: {phone_number}"
            )
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse job metadata as JSON, using default context"
            )

    # Initialize shared call state
    call_state = CallState(
        context=context,
        context_instance=context_instance,
        lead_name=context.get("name", ""),
        lead_company=context.get("lead_company", ""),
        lead_title=context.get("lead_title", ""),
        goal=context.get("goal", "qualify_interest"),
    )

    # Set up voice AI pipeline
    session = AgentSession[CallState](
        userdata=call_state,
        stt=deepgram.STT(model="nova-3", language="en"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=elevenlabs.TTS(
            voice_id=ELEVENLABS_VOICE_ID,
            model="eleven_turbo_v2_5",
            language="en",
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
        min_interruption_words=2,
        min_interruption_duration=0.8,
        min_endpointing_delay=0.6,
        resume_false_interruption=True,
        false_interruption_timeout=1.5,
    )

    # Background audio: subtle office ambience + typing sounds during thinking
    background_audio = BackgroundAudioPlayer(
        ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.15),
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.6, probability=0.7),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.5, probability=0.3),
        ],
    )

    # Start session BEFORE dialing so agent doesn't miss anything
    session_started = asyncio.create_task(
        session.start(
            agent=GreetingAgent(context=context),
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(
                    noise_cancellation=noise_cancellation.BVCTelephony(),
                ),
            ),
        )
    )

    # Dial outbound if we have a phone number and SIP trunk (unless demo mode)
    participant_identity = phone_number
    if phone_number and SIP_OUTBOUND_TRUNK_ID and not DEMO_MODE:
        logger.info(f"Dialing {phone_number} via SIP trunk {SIP_OUTBOUND_TRUNK_ID}")
        try:
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=SIP_OUTBOUND_TRUNK_ID,
                    sip_call_to=phone_number,
                    participant_identity=participant_identity,
                    wait_until_answered=True,
                )
            )
            logger.info(f"Call answered by {phone_number}")
            await session_started
            participant = await ctx.wait_for_participant(identity=participant_identity)
            logger.info(f"Participant joined: {participant.identity}")
            call_state.participant = participant

        except api.TwirpError as e:
            sip_status = (
                e.metadata.get("sip_status_code", "unknown")
                if hasattr(e, "metadata")
                else "unknown"
            )
            sip_message = (
                e.metadata.get("sip_status", "") if hasattr(e, "metadata") else ""
            )
            logger.error(
                f"SIP error dialing {phone_number}: {e.message}, "
                f"SIP status: {sip_status} {sip_message}"
            )
            call_state.outcome = "no_answer"
            ctx.shutdown()
            return

        except Exception as e:
            logger.error(f"Error dialing {phone_number}: {e}")
            call_state.outcome = "error"
            ctx.shutdown()
            return
    else:
        if DEMO_MODE:
            logger.info("DEMO_MODE enabled - skipping SIP dial, waiting for browser participant")
        elif not phone_number:
            logger.warning("No phone number in context - treating as inbound call")
        elif not SIP_OUTBOUND_TRUNK_ID:
            logger.warning("SIP_OUTBOUND_TRUNK_ID not configured")
        await session_started

    # Start background audio after session is running
    await background_audio.start(room=ctx.room, agent_session=session)

    # Shutdown callback to report outcome and send emails
    async def report_outcome():
        """Report call outcome and send post-call emails."""
        call_end_time = datetime.now(timezone.utc)

        duration_seconds = 0
        if call_state.call_start_time:
            duration_seconds = int(
                (call_end_time - call_state.call_start_time).total_seconds()
            )

        logger.info(
            f"Call completed: outcome={call_state.outcome}, "
            f"duration={duration_seconds}s, "
            f"email={call_state.lead_email}, "
            f"objection={call_state.objection_reason}"
        )

        # Send emails if shared package is available
        if (
            SHARED_AVAILABLE
            and call_state.context_instance
            and CallResult is not None
            and send_post_call_emails is not None
        ):
            call_result = CallResult(
                call_id=uuid4(),
                submission_id=call_state.context_instance.id,
                phone=call_state.context_instance.phone,
                duration_seconds=duration_seconds,
                goal=call_state.context_instance.goal,
                outcome=call_state.outcome,
                objection_reason=call_state.objection_reason,
                collected_data=call_state.collected_data
                if call_state.collected_data
                else {},
                lead_email=call_state.lead_email,
                transcript=None,
                recording_url=None,
                lead_email_sent=False,
                error=None,
                started_at=call_state.call_start_time,
                ended_at=call_end_time,
            )

            try:
                email_results = await send_post_call_emails(
                    context=call_state.context_instance,
                    result=call_result,
                )
                logger.info(f"Email results: {email_results}")
            except Exception as e:
                logger.error(f"Failed to send post-call emails: {e}")
        elif not SHARED_AVAILABLE:
            logger.warning("shared package not available - skipping email sending")

    ctx.add_shutdown_callback(report_outcome)


if __name__ == "__main__":
    cli.run_app(server)
