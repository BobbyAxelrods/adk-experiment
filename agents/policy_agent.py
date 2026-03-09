import os
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from tools.corpus.corpus_tools import query_corpus
from tools.tone_management.tone_guideline_tools import response_tone_guideline
from tools.mcp_policy.mcp_tools import policy_mcp_tool
from tools.policy_tools.policy_tools import flag_violation, report_violation_to_root, track_frustration, record_unrecognized_intent
from tools.mcp_escalation.escalation_tools import escalate_to_live_agent
from .callback import reset_unrecognized_intent, count_unrecognized_intents


from ._fragments.loader import load_instruction


model_name = os.getenv("MODEL_NAME", "gpt-4o")
litellm_model = LiteLlm(model=model_name)

policy_agent = Agent(
    name="policy_agent",
    model=litellm_model,
    description="Factual knowledge agent for Prudential insurance policy/products inquiries",
    instruction=load_instruction("policy_agent"),
    tools=[
        query_corpus,
        response_tone_guideline,
        policy_mcp_tool,
        flag_violation,
        report_violation_to_root,
        track_frustration,
        record_unrecognized_intent,
        escalate_to_live_agent
    ],
    before_agent_callback=reset_unrecognized_intent,
    after_model_callback=count_unrecognized_intents,
)
