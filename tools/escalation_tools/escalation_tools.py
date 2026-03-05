from typing import Dict, Any, Optional, List
import random
import string
from datetime import datetime, timezone, timedelta
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


def create_escalation_ticket(reason: str = "User request", context: str = "", tool_context: Optional[ToolContext] = None) -> Dict[str, Any]:
    """
    Create an escalation ticket.
    
    Generates a ticket ID and logs the escalation request.
    This does NOT switch the active agent (the orchestrator handles that).

    Args:
      reason: short reason for escalation
      context: optional user message or system context that triggered escalation
      tool_context: optional ADK ToolContext (duck-typed) whose `.state` will be updated

    Returns:
      A dict with ticket details.
    """
    ticket_id = _generate_ticket_id()

    priority = "high" if "urgent" in (context or "").lower() else "normal"

    payload = {
        "status": "success",
        "message": "Escalation ticket created.",
        "ticket_id": ticket_id,
        "reason": reason,
        "priority": priority,
    }

    if tool_context is not None and hasattr(tool_context, "state"):
        try:
            state = tool_context.state

            # We don't force active_agent switch here, assuming ADK runner did it 
            # or will do it via sub-agent call.
            # But we record the event.

            escalation_record = {
                "ticket_id": ticket_id,
                "transfer_reason": reason,
                "context": context,
                "priority": priority,
                "escalated_to_human": True,
                "escalation_time": _now_iso(),
            }
            
            # Update state for reference
            state["last_escalation_ticket"] = ticket_id
            state["escalated_to_human"] = True
            
            _append_escalation_history(state, escalation_record)
        except Exception:
            logger.exception("Failed to write escalation record into tool_context.state")

    return payload

# Renamed for clarity in imports if needed, but we keep the old name for compatibility 
# inside the module if other tools use it, though we should update them.
escalate_to_live_agent = create_escalation_ticket 


def check_agent_availability() -> Dict[str, Any]:
    """
    Check if live agents are currently available.
    
    Returns:
        Dict with availability status, estimated wait time, and current queue length.
    """
    # Simulate availability based on random chance or time of day
    # For demo, we'll assume 80% availability
    available = random.random() < 0.8
    queue_length = random.randint(0, 5) if available else random.randint(10, 20)
    wait_time = queue_length * 2  # 2 minutes per person
    
    return {
        "available": available,
        "status": "online" if available else "busy",
        "queue_length": queue_length,
        "estimated_wait_minutes": wait_time,
        "message": f"Agents are {'available' if available else 'busy'}. Estimated wait: {wait_time} mins."
    }

def request_callback(tool_context: ToolContext, phone_number: str, preferred_time: str) -> Dict[str, Any]:
    """
    Request a callback from a live agent.
    
    Args:
        phone_number: The user's contact number.
        preferred_time: When they want to be called (e.g., "ASAP", "tomorrow morning").
    """
    ticket_id = _generate_ticket_id(prefix="CB")
    
    # Store in state if possible
    if hasattr(tool_context, "state"):
        tool_context.state["callback_request"] = {
            "ticket_id": ticket_id,
            "phone": phone_number,
            "time": preferred_time,
            "timestamp": _now_iso()
        }
        
    return {
        "status": "scheduled",
        "ticket_id": ticket_id,
        "message": f"Callback scheduled for {preferred_time} at {phone_number}.",
        "confirmation_code": ticket_id
    }

def leave_message(tool_context: ToolContext, message: str) -> Dict[str, Any]:
    """
    Leave a message for the support team.
    
    Args:
        message: The content of the message to leave.
    """
    ticket_id = _generate_ticket_id(prefix="MSG")
    
    return {
        "status": "sent",
        "ticket_id": ticket_id,
        "message": "Your message has been recorded and sent to the support team.",
        "timestamp": _now_iso()
    }

# ADK Tool Definitions
# escalate_to_live_agent is kept as a tool for the escalation agent to use (to generate ticket)
escalate_to_live_agent = FunctionTool(func=escalate_to_live_agent)
check_agent_availability = FunctionTool(func=check_agent_availability)
request_callback = FunctionTool(func=request_callback)
leave_message = FunctionTool(func=leave_message)
