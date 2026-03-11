from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse, LlmRequest
from typing import Optional
import os

# Import Agents & Tools
from tools.mcp_escalation.escalation_tools import escalate_to_live_agent
from tools.policy_tools.policy_tools import track_frustration
from tools.tone_management.tone_guideline_tools_v2 import get_tone_guideline
from tools.state.state_tools import set_pending_intents, advance_intent
from .callback import reset_unrecognized_intent,count_unrecognized_intents
from utils.agent_config import generate_content_config

# Import Instructions
def load_instructions(file_name):
    path = os.path.join(os.path.dirname(__file__), f"{file_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

model = os.getenv("MODEL_NAME", "gemini-2.5-flash")

escalation_agent = Agent(
    name="escalation_agent",
    model=model,
    description="Agent for emergency & crisis management, frustrated users management or when a human is explicitly requested.",
    instruction=load_instructions("escalation_agent_instruction"),
    generate_content_config=generate_content_config,
    tools=[
        track_frustration,
        get_tone_guideline,
        escalate_to_live_agent,
        set_pending_intents,
        advance_intent,
    ],
    after_model_callback=count_unrecognized_intents,
    before_agent_callback=reset_unrecognized_intent
)

# Reviewed by Shafiq
