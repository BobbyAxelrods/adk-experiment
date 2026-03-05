from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse, LlmRequest
from google.adk.models.lite_llm import LiteLlm
from typing import Optional
import os
from tools.mcp_escalation.escalation_tools import escalate_to_live_agent
from tools.policy_tools.policy_tools import track_frustration
from tools.tone_management.tone_guideline_tools import response_tone_guideline
from .callback import reset_unrecognized_intent, count_unrecognized_intents


def load_instructions(file_name):
    path = os.path.join(os.path.dirname(__file__), f"{file_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


model_name = os.getenv("MODEL_NAME", "gpt-4o")
litellm_model = LiteLlm(model=model_name)


escalation_agent = Agent(
    name="escalation_agent",
    model=litellm_model,
    description="Worker for escalating complex or sensitive cases to human agents",
    instruction=load_instructions("escalation_agent_instruction"),
    tools=[track_frustration, response_tone_guideline, escalate_to_live_agent],
    after_model_callback=count_unrecognized_intents,
    before_agent_callback=reset_unrecognized_intent
)
