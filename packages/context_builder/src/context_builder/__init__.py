"""Context Builder package for Stateless Multi-Tenant Voice Agent MVP.

This package uses Stanford DSPy to build ContextInstance objects
before calls start. It runs BEFORE the call, not during the
real-time voice loop.
"""

from context_builder.builder import (
    ContextBuilder,
    build_context,
    build_contexts_for_submission,
)

__all__ = ["ContextBuilder", "build_context", "build_contexts_for_submission"]
