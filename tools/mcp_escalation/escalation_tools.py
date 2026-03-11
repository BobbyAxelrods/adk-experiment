# tools/mcp_escalation/escalation_tools.py
#
# All escalation logic has been centralized into tools/state/state_tools.py.
# This file re-exports for backward compatibility.
#
# Prefer importing directly from tools.state.state_tools in new code.

from tools.state.state_tools import (
    escalate_to_live_agent,
    return_to_bot,
    request_callback,
)

__all__ = [
    "escalate_to_live_agent",
    "return_to_bot",
    "request_callback",
]
