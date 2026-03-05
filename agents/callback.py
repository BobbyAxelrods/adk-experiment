from typing import Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse


def count_unrecognized_intents(
    callback_context: CallbackContext,
    llm_response: LlmResponse
) -> Optional[LlmResponse]:
    """
    Passive counter — only increments when the agent explicitly calls
    `record_unrecognized_intent` in its response.

    No forced LlmResponse override. The agent prompt handles escalation decisions
    based on the `escalation_recommended` flag set here.
    """
    state = callback_context.state

    # Initialize counters if missing
    if "unrecognized_intent_count" not in state:
        state["unrecognized_intent_count"] = 0
    if "violation_count" not in state:
        state["violation_count"] = 0

    # Inspect function calls in the response
    called_record_unrecognized = False
    saw_success_tool = False

    # Tools that do NOT count as "intent resolved" (do not reset counter)
    disallowed_reset_tools = {
        "record_unrecognized_intent",
        "response_tone_guideline",
        "response_tone_guideline_tool",
        "detect_language",
        "flag_violation",
    }

    if llm_response.content and llm_response.content.parts:
        for part in llm_response.content.parts:
            func_call = getattr(part, "function_call", None)
            if func_call:
                func_name = getattr(func_call, "name", "")
                if func_name == "record_unrecognized_intent":
                    called_record_unrecognized = True
                elif func_name and func_name not in disallowed_reset_tools:
                    saw_success_tool = True

    if called_record_unrecognized:
        # Only the callback increments — tool no longer does (Bug 3 fix)
        current = state.get("unrecognized_intent_count", 0) + 1
        state["unrecognized_intent_count"] = current

        if current >= 3:
            state["escalation_recommended"] = True
            # Reset counter so it doesn't keep firing every turn
            state["unrecognized_intent_count"] = 0

    elif saw_success_tool:
        # A genuine intent-resolving tool was called — reset unrecognized counter
        if state.get("unrecognized_intent_count", 0) > 0:
            state["unrecognized_intent_count"] = 0

    # Always return the original response unchanged — no override (Bug 1 fix)
    return llm_response


def reset_turn_detection(
    callback_context: CallbackContext,
    llm_request: LlmRequest = None
) -> None:
    """
    Resets the turn_detection state key before each model call.
    Used by booking_agent as before_model_callback.
    """
    callback_context.state["turn_detection"] = ""


def reset_unrecognized_intent(
    callback_context: CallbackContext,
    llm_request: LlmRequest = None
) -> None:
    """
    Resets only `unrecognized_intent_count` when entering a sub-agent.
    Never touches `violation_count` or `escalation_recommended` (Bug 2 fix).
    """
    state = callback_context.state
    if state.get("unrecognized_intent_count", 0) > 0:
        state["unrecognized_intent_count"] = 0
