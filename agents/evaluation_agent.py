import os
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from tools.lifecycle.lifecycle_main import automated_evaluation_testcase
from tools.policy_tools.policy_tools import flag_violation, report_violation_to_root, track_frustration, record_unrecognized_intent
from tools.mcp_escalation.escalation_tools import escalate_to_live_agent
from .callback import reset_unrecognized_intent, count_unrecognized_intents
from ._fragments.loader import load_instruction


model_name = os.getenv("MODEL_NAME", "gpt-4o")
litellm_model = LiteLlm(model=model_name)

evaluation_agent = Agent(
    name="evaluation_agent",
    model=litellm_model,
    description="Evaluate the performance of RAG agent for Prudential insurance policy/products inquiries",
    instruction=load_instruction("evaluation_agent"),
    tools=[
        automated_evaluation_testcase,
        flag_violation,
        report_violation_to_root,
        track_frustration,
        record_unrecognized_intent,
        escalate_to_live_agent
    ],
    before_agent_callback=reset_unrecognized_intent,
    after_model_callback=count_unrecognized_intents,
)
