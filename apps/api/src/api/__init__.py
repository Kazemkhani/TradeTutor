"""API package for AI Lead Qualification System.

This FastAPI application orchestrates:
- Lead submission (POST /leads)
- Context building (using context_builder)
- Call triggering (using LiveKit SIP)
"""

from api.main import app

__all__ = ["app"]
