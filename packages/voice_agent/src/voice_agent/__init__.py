"""Voice Agent package for AI Lead Qualification System.

This package contains the LiveKit-based voice agent that handles
real-time voice calls. It receives pre-built ContextInstance JSON
and uses it during the call - no DSPy in the real-time loop.
"""

from voice_agent.agent import Assistant, server

__all__ = ["Assistant", "server"]
