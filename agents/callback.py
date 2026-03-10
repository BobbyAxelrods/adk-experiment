from typing import Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse


def count_unrecognized_intents(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """
    after_model_callback — passive counter.
    Only increments when the agent explicitly calls `record_unrecognized_intent`.
    No forced LlmResponse override (Bug 1 fix).
    """
    state = callback_context.state

    if "unrecognized_intent_count" not in state:
        state["unrecognized_intent_count"] = 0
    if "violation_count" not in state:
        state["violation_count"] = 0

    called_record_unrecognized = False
    saw_success_tool = False

    disallowed_reset_tools = {
        "record_unrecognized_intent",
        "response_tone_guideline",
        "response_tone_guideline_tool",
        "detect_language",
        "flag_violation",
        # intent queue tools are routing helpers, not success signals
        "set_pending_intents",
        "advance_intent",
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
        current = state.get("unrecognized_intent_count", 0) + 1
        state["unrecognized_intent_count"] = current
        if current >= 3:
            state["escalation_recommended"] = True
            state["unrecognized_intent_count"] = 0

    elif saw_success_tool:
        if state.get("unrecognized_intent_count", 0) > 0:
            state["unrecognized_intent_count"] = 0

    return llm_response


def reset_turn_detection(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """
    before_model_callback — resets turn_detection state before each model call.
    """
    callback_context.state["turn_detection"] = ""
    return None


def reset_unrecognized_intent(
    callback_context: CallbackContext,
) -> None:
    """
    before_agent_callback — resets unrecognized_intent_count on sub-agent entry.
    Never touches violation_count or escalation_recommended (Bug 2 fix).
    """
    state = callback_context.state
    if state.get("unrecognized_intent_count", 0) > 0:
        state["unrecognized_intent_count"] = 0
