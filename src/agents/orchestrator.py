"""Compatibility wrapper for legacy imports.

Prefer importing from src.agents.autogen_service directly.
"""

from src.agents.autogen_service import (
    dispatch_agent,
    dispatch_autogen_service,
    run_autogen_discussion,
    run_autogen_discussion_stream,
    run_debate,
    run_debate_stream,
)

__all__ = [
    "dispatch_autogen_service",
    "run_autogen_discussion",
    "run_autogen_discussion_stream",
    "dispatch_agent",
    "run_debate",
    "run_debate_stream",
]
