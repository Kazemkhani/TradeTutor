"""LiveKit SIP Dispatch module.

Handles dispatching voice agent and dialing phone numbers via SIP.
"""

import logging
import os
from dataclasses import dataclass

from livekit import api
from shared.schemas import ContextInstance

logger = logging.getLogger("voice-agent-dispatch")


@dataclass
class DispatchConfig:
    """Configuration for LiveKit dispatch."""

    livekit_url: str
    api_key: str
    api_secret: str
    sip_trunk_id: str
    agent_name: str = "voice-agent"

    @classmethod
    def from_env(cls) -> "DispatchConfig":
        """Load dispatch config from environment variables."""
        livekit_url = os.getenv("LIVEKIT_URL", "")
        api_key = os.getenv("LIVEKIT_API_KEY", "")
        api_secret = os.getenv("LIVEKIT_API_SECRET", "")
        sip_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID", "")
        agent_name = os.getenv("VOICE_AGENT_NAME", "voice-agent")

        if not livekit_url:
            logger.warning("LIVEKIT_URL not set")
        if not api_key:
            logger.warning("LIVEKIT_API_KEY not set")
        if not api_secret:
            logger.warning("LIVEKIT_API_SECRET not set")
        if not sip_trunk_id:
            logger.warning("SIP_OUTBOUND_TRUNK_ID not set - calls will fail")

        return cls(
            livekit_url=livekit_url,
            api_key=api_key,
            api_secret=api_secret,
            sip_trunk_id=sip_trunk_id,
            agent_name=agent_name,
        )

    def is_configured(self) -> bool:
        """Check if all required config is present."""
        return bool(
            self.livekit_url and self.api_key and self.api_secret and self.sip_trunk_id
        )


@dataclass
class DispatchResult:
    """Result of a dispatch operation."""

    success: bool
    room_name: str | None = None
    dispatch_id: str | None = None
    error: str | None = None


class LiveKitDispatcher:
    """Dispatches voice agents and dials phone numbers via LiveKit SIP."""

    def __init__(self, config: DispatchConfig | None = None):
        """Initialize the dispatcher.

        Args:
            config: Dispatch configuration. If not provided, loads from environment.
        """
        self.config = config or DispatchConfig.from_env()

    async def dispatch_call(
        self,
        context: ContextInstance,
    ) -> DispatchResult:
        """Dispatch a voice agent to handle an outbound call.

        This creates an agent dispatch only. The agent will:
        1. Join the room
        2. Read the phone number from context metadata
        3. Dial the phone using ctx.api.sip.create_sip_participant()
        4. Wait for the call to be answered before interacting

        Args:
            context: The context instance with phone number and agent config

        Returns:
            DispatchResult with room_name and dispatch_id on success
        """
        if not self.config.is_configured():
            return DispatchResult(
                success=False,
                error="LiveKit not configured. Check LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, and SIP_OUTBOUND_TRUNK_ID",
            )

        # Generate unique room name for this call
        room_name = f"call-{context.id}"

        # Convert context to JSON for agent metadata
        # The agent will read the phone number from this metadata and dial it
        context_json = context.model_dump_json()

        try:
            # Create LiveKit API client
            lkapi = api.LiveKitAPI(
                self.config.livekit_url,
                self.config.api_key,
                self.config.api_secret,
            )

            # Create agent dispatch - the agent will handle dialing the phone
            logger.info(
                f"Creating dispatch for agent {self.config.agent_name} in room {room_name}"
            )
            logger.info(f"Agent will dial {context.phone} after joining")
            dispatch = await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=self.config.agent_name,
                    room=room_name,
                    metadata=context_json,  # Contains phone number for agent to dial
                )
            )
            logger.info(f"Created dispatch: {dispatch.id}")

            await lkapi.aclose()

            return DispatchResult(
                success=True,
                room_name=room_name,
                dispatch_id=dispatch.id,
            )

        except api.TwirpError as e:
            error_msg = f"LiveKit API error: {e.message}"
            logger.error(error_msg)
            return DispatchResult(success=False, error=error_msg)

        except Exception as e:
            error_msg = f"Dispatch error: {e!s}"
            logger.error(error_msg)
            return DispatchResult(success=False, error=error_msg)


# Convenience function
async def dispatch_voice_call(context: ContextInstance) -> DispatchResult:
    """Dispatch a voice call for the given context.

    Args:
        context: The context instance with phone and agent config

    Returns:
        DispatchResult indicating success or failure
    """
    dispatcher = LiveKitDispatcher()
    return await dispatcher.dispatch_call(context)
