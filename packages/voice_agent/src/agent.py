#!/usr/bin/env python3
"""Compatibility shim to preserve the original entrypoint.

This file ensures that `python src/agent.py dev` continues to work
after restructuring to the monorepo layout.

Usage (both work):
  python src/agent.py dev              # Original command (still works)
  python src/agent.py console          # Console mode
  python src/agent.py dev --context ./context.json  # With context
  python -m voice_agent.agent dev      # New module-style command
"""

import os
import sys

# Add the src directory to path so we can import voice_agent
sys.path.insert(0, os.path.dirname(__file__))

# Import and re-export everything from the main agent module
from voice_agent.agent import (
    Assistant,
    get_context,
    load_context,
    main,
    my_agent,
    prewarm,
    server,
    set_context,
)

__all__ = [
    "Assistant",
    "get_context",
    "load_context",
    "main",
    "my_agent",
    "prewarm",
    "server",
    "set_context",
]

if __name__ == "__main__":
    main()
