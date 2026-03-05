import os
from google.adk.agents import Agent
from google.adk.tools import AgentTool
from google.adk.models.lite_llm import LiteLlm
from tools.corpus.corpus_tools import query_corpus  
from tools.tone_management.tone_guideline_tools import response_tone_guideline
from tools.mcp_policy.mcp_tools import policy_mcp_tool
from .callback import reset_unrecognized_intent, count_unrecognized_intents
from .policy_mcp_agent import policy_mcp_agent


def load_instructions(file_name):
    path = os.path.join(os.path.dirname(__file__), f"{file_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


model_name = os.getenv("MODEL_NAME", "gpt-4o")
litellm_model = LiteLlm(model=model_name)


rag_agent = Agent(
    name="rag_agent",
    model=litellm_model,
    description="Factual knowledge agent for Prudential insurance,policy/products and health inquiries",
    instruction=load_instructions("rag_agent_instruction"),
    tools=[
        query_corpus,
        response_tone_guideline,
        AgentTool(policy_mcp_agent)
    ],
    before_agent_callback=reset_unrecognized_intent,
    after_model_callback=[count_unrecognized_intents]
)
