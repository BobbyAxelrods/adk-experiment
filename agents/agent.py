import os
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from config.config import PROJECT_ID, LOCATION

from .rag_agent import rag_agent
from .booking_agent import booking_agent
from .escalation_agent import escalation_agent
from .policy_agent import policy_agent
from .policy_mcp_agent import policy_mcp_agent
from .vas_agent import vas_agent
from .evaluation_agent import evaluation_agent
from .callback import count_unrecognized_intents

from tools.policy_tools.policy_tools import update_summary, track_frustration, detect_language, flag_violation, record_unrecognized_intent, set_pending_intents, advance_intent
from tools.tone_management.tone_guideline_tools import response_tone_guideline
from tools.mcp_escalation.escalation_tools import escalate_to_live_agent
from ._fragments.loader import load_instruction


USER_ID = "member_default"

INITIAL_STATE = {
    "frustration_count": 0,
    "frustration_threshold": 3,
    "unrecognized_intent_count": 0,
    "escalate_to_human": None,
    "escalation_recommended": False,
    "user_id": USER_ID,
    "language": "english",
    "authentication": False,
    "pending_intents": [],
    "current_intent": None,
}

model_name = os.getenv("MODEL_NAME", "gpt-4o")
litellm_model = LiteLlm(model=model_name)

root_agent = Agent(
    name="pru_master_orchestrator",
    model=litellm_model,
    description="master orchestrator for Prudential multi-agent workflow",
    instruction=load_instruction("root_agent"),
    tools=[
        track_frustration,
        detect_language,
        flag_violation,
        update_summary,
        response_tone_guideline,
        record_unrecognized_intent,
        escalate_to_live_agent,
        set_pending_intents,
        advance_intent,
    ],
    sub_agents=[
        rag_agent,
        booking_agent,
        escalation_agent,
        policy_agent,
        policy_mcp_agent,
        vas_agent,
        evaluation_agent,
    ],
    output_key="root_agent_output",
    after_model_callback=count_unrecognized_intents,
)
