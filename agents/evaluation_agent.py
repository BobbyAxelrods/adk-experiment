import os
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from tools.corpus.corpus_tools import query_corpus
from tools.tone_management.tone_guideline_tools import response_tone_guideline
from tools.mcp_policy.mcp_tools import policy_mcp_tool
from tools.lifecycle.lifecycle_main import automated_evaluation_testcase


def load_instructions(file_name):
    path = os.path.join(os.path.dirname(__file__), f"{file_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


model_name = os.getenv("MODEL_NAME", "gpt-4o")
litellm_model = LiteLlm(model=model_name)

evaluation_agent = Agent(
    name="evaluation_agent",
    model=litellm_model,
    description="Evaluate the performance of RAG agent for Prudential insurance policy/products inquiries",
    instruction=load_instructions("evaluation_agent_instruction"),
    tools=[automated_evaluation_testcase],
)
