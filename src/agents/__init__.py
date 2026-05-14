"""Multi-agent discussion orchestration — AutoGen (legacy) + LangGraph (new)."""

from .autogen_service import (
    dispatch_agent,
    dispatch_autogen_service,
    run_autogen_discussion,
    run_autogen_discussion_stream,
    run_debate,
    run_debate_stream,
)
from .langgraph_service import (
    run_langgraph_discussion_stream,
    resume_langgraph_discussion_stream,
    build_discussion_graph,
    get_discussion_state,
)

__all__ = [
    # Legacy AutoGen
    "dispatch_autogen_service",
    "run_autogen_discussion",
    "run_autogen_discussion_stream",
    "dispatch_agent",
    "run_debate",
    "run_debate_stream",
    # New LangGraph
    "run_langgraph_discussion_stream",
    "resume_langgraph_discussion_stream",
    "build_discussion_graph",
    "get_discussion_state",
]
