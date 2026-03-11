import os
from google.adk.agents import Agent
from tools.corpus.corpus_tools import query_corpus
from tools.tone_management.tone_guideline_tools import response_tone_guideline
from tools.mcp_policy.mcp_tools import policy_mcp_tool
from utils.agent_config import generate_content_config


def load_instructions(file_name):
    path = os.path.join(os.path.dirname(__file__), f"{file_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

model = os.getenv("MODEL_NAME", "gemini-2.5-flash")

vas_agent = Agent(
    name="vas_agent",
    model=model,
    description="Factual knowledge agent for Prudential insurance value-added services (vas) inquiries",
    instruction=load_instructions("vas_agent_instruction"),
    generate_content_config=generate_content_config,
    tools=[query_corpus, response_tone_guideline, policy_mcp_tool],
)
