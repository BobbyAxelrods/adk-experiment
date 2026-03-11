import os
from typing import Optional
from google.adk.agents import Agent
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types
from dotenv import load_dotenv
import vertexai
from config.config import PROJECT_ID, LOCATION
from google.adk.sessions.in_memory_session_service import InMemorySessionService

# ── Sub-agent imports ──────────────────────────────────────────────────────────
from .rag_agent import rag_agent
from .booking_agent import booking_agent
from .escalation_agent import escalation_agent
from .policy_mcp_agent import policy_mcp_agent
from .vas_agent import vas_agent
from .evaluation_agent import evaluation_agent


# ── Centralized state tools + callbacks ───────────────────────────────────────
from tools.state.state_tools import (
    track_frustration,
    flag_violation,
    report_violation_to_root,
    record_unrecognized_intent,
    detect_language,
    escalate_to_live_agent,
    return_to_bot,
    set_pending_intents,
    advance_intent,
    update_summary,
    count_unrecognized_intents,       # after_model_callback
    clear_intent_queue_on_completion, # after_agent_callback (safety net)
)
# from tools.intent_handler.multi_intent import set_pending_intents, advance_intent
from tools.tone_management.tone_guideline_tools_v2 import get_tone_guideline
from utils.agent_config import generate_content_config
from prompts.manager import prompt_manager

# ── Env ────────────────────────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv()

model = os.getenv("MODEL_NAME", "gemini-2.5-flash")

if PROJECT_ID and LOCATION:
    vertexai.init(project=PROJECT_ID, location=LOCATION)

# ── Session service ────────────────────────────────────────────────────────────
session_service = InMemorySessionService()

APP_NAME = "health_insurance_assistant"
USER_ID  = "member_default"   # replace with real user ID from auth layer

# ── INITIAL_STATE — single source of truth for all session keys ───────────────
# Every key that any tool/callback reads or writes must be declared here.
# This ensures state is predictable from turn 0.
INITIAL_STATE = {
    # --- User context ---
    "user_id":                    USER_ID,
    "language":                   "english",
    "authentication":             False,

    # --- Counters ---
    "frustration_count":          0,
    "violation_count":            0,
    "unrecognized_intent_count":  0,

    # --- Escalation ---
    "escalation_recommended":     False,
    "escalated_to_human":         False,   # unified key (was escalate_to_human)
    "last_escalation_ticket":     None,
    "escalation_history":         [],

    # --- Multi-intent queue ---
    "pending_intents":            [],
    "current_intent":             None,

    # --- Conversation ---
    "conversation_summary":       "",      # written by update_summary tool
    # root_agent_output written automatically via output_key="root_agent_output"
}


# ── Instruction loader ─────────────────────────────────────────────────────────
def load_instructions(template_name: str) -> str:
    return prompt_manager.get_instruction(template_name)


# ── Root Agent ─────────────────────────────────────────────────────────────────
root_agent = Agent(
    name="root_agent",
    model=model,
    description="Master orchestrator for Prudential multi-agent workflow",
    instruction=load_instructions("root_agent"),
    tools=[
        track_frustration,
        detect_language,
        flag_violation,
        report_violation_to_root,
        record_unrecognized_intent,
        escalate_to_live_agent,
        return_to_bot,
        set_pending_intents,       # multi-intent: queue all intents
        advance_intent,            # multi-intent: pop next intent
        update_summary,
        get_tone_guideline,
    ],
    sub_agents=[
        rag_agent,
        booking_agent,
        escalation_agent,
        policy_mcp_agent,
        vas_agent,
        evaluation_agent,
    ],
    output_key="root_agent_output",
    generate_content_config=generate_content_config,
    after_model_callback=count_unrecognized_intents,
    after_agent_callback=clear_intent_queue_on_completion,
)
