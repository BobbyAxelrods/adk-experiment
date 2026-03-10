from typing import Dict, Any, Optional, List
import random
import string
from datetime import datetime, timezone
import logging
from google.adk.tools.tool_context import ToolContext
from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)


def _generate_ticket_id(prefix: str = "TKT", length: int = 8) -> str:
    return f"{prefix}-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_escalation_history(state: Dict[str, Any], entry: Dict[str, Any]) -> None:
    history: List[Dict[str, Any]] = state.get("escalation_history", [])
    history.append(entry)
    state["escalation_history"] = history


def _escalate_to_live_agent(
    reason: str = "User request",
    context: str = "",
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """
    Escalate the user to a live agent by creating an escalation ticket.

    Call this when:
    - The user explicitly requests a human agent
    - escalation_recommended is True in state
    - The issue is too complex or sensitive for automated handling
    - A safety or crisis situation is detected

    Args:
        reason: short reason for escalation (e.g. "User requested human agent")
        context: the user message or system context that triggered escalation
    """
    ticket_id = _generate_ticket_id()
    priority  = "high" if "urgent" in (context or "").lower() else "normal"

    payload = {
        "status":    "success",
        "message":   "Escalation ticket created. Transferring to human agent.",
        "ticket_id": ticket_id,
        "reason":    reason,
        "priority":  priority,
    }

    if tool_context is not None and hasattr(tool_context, "state"):
        try:
            state = tool_context.state

            escalation_record = {
                "ticket_id":          ticket_id,
                "transfer_reason":    reason,
                "context":            context,
                "priority":           priority,
                "escalated_to_human": True,
                "escalation_time":    _now_iso(),
            }

            state["escalated_to_human"]      = True
            state["last_escalation_ticket"]  = ticket_id
            state["escalation_recommended"]  = True   # ensure routing flags are set
            _append_escalation_history(state, escalation_record)

        except Exception:
            logger.exception("Failed to write escalation record into tool_context.state")

    return payload


def check_agent_availability() -> Dict[str, Any]:
    """
    Check if live agents are currently available.

    Returns availability status, estimated wait time, and current queue length.
    """
    available    = random.random() < 0.8
    queue_length = random.randint(0, 5) if available else random.randint(10, 20)
    wait_time    = queue_length * 2

    return {
        "available":               available,
        "status":                  "online" if available else "busy",
        "queue_length":            queue_length,
        "estimated_wait_minutes":  wait_time,
        "message":                 f"Agents are {'available' if available else 'busy'}. Estimated wait: {wait_time} mins.",
    }


def request_callback(
    tool_context: ToolContext,
    phone_number: str,
    preferred_time: str,
) -> Dict[str, Any]:
    """
    Request a callback from a live agent.

    Args:
        phone_number: the user's contact number
        preferred_time: when they want to be called (e.g. "ASAP", "tomorrow morning")
    """
    ticket_id = _generate_ticket_id(prefix="CB")

    if hasattr(tool_context, "state"):
        tool_context.state["callback_request"] = {
            "ticket_id": ticket_id,
            "phone":     phone_number,
            "time":      preferred_time,
            "timestamp": _now_iso(),
        }

    return {
        "status":            "scheduled",
        "ticket_id":         ticket_id,
        "message":           f"Callback scheduled for {preferred_time} at {phone_number}.",
        "confirmation_code": ticket_id,
    }


def leave_message(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """
    Leave a message for the support team when no live agent is available.

    Args:
        message: the content to leave for the support team
    """
    ticket_id = _generate_ticket_id(prefix="MSG")

    return {
        "status":    "sent",
        "ticket_id": ticket_id,
        "message":   "Your message has been recorded and sent to the support team.",
        "timestamp": _now_iso(),
    }


# ── FunctionTool registrations ────────────────────────────────────────────────

escalate_to_live_agent    = FunctionTool(func=_escalate_to_live_agent)
check_agent_availability  = FunctionTool(func=check_agent_availability)
request_callback          = FunctionTool(func=request_callback)
leave_message             = FunctionTool(func=leave_message)
