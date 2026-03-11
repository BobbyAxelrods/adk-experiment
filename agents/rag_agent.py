import os
from google.adk.agents import Agent
from google.adk.tools import AgentTool
from tools.corpus.corpus_tools import query_corpus, identify_policy_vas_context
from tools.tone_management.tone_guideline_tools import response_tone_guideline
from tools.policy_tools.policy_tools import flag_violation, track_frustration, record_unrecognized_intent
from tools.mcp_escalation.escalation_tools import escalate_to_live_agent
from tools.mcp_policy.mcp_tools import policy_mcp_tool
from .callback import reset_unrecognized_intent, count_unrecognized_intents
from agents.policy_mcp_agent import policy_mcp_agent
from utils.agent_config import generate_content_config
# Import instructions
def load_instructions(file_name):
    path = os.path.join(os.path.dirname(__file__), f"{file_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

model = os.getenv("MODEL_NAME", "gemini-2.5-flash")

rag_agent = Agent(
    name="rag_agent",
    model=model,
    description="Factual knowledge agent for Prudential insurance,policy/products and health inquiries",
    instruction=load_instructions("rag_agent_instruction"),
    # Sub-agent tools: allow querying corpus, flag/report violations, increment
    # frustration, and escalate directly to a human if necessary. Tone selection
    # should be guided by response_tone_guideline (stateless helper).
    tools=[
        query_corpus,
        flag_violation,
        escalate_to_live_agent,
        track_frustration,
        response_tone_guideline,
        record_unrecognized_intent,
        AgentTool(policy_mcp_agent),
    ],
    generate_content_config=generate_content_config,
    before_agent_callback=reset_unrecognized_intent,
    after_model_callback=count_unrecognized_intents 
)

# Reviewed by Shafiq
