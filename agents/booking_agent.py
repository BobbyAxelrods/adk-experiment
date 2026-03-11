# Import Libary
import os
from google.adk.agents import Agent
from tools.policy_tools.policy_tools import flag_violation, report_violation_to_root, track_frustration, record_unrecognized_intent
from tools.mcp_escalation.escalation_tools import escalate_to_live_agent
from tools.tone_management.tone_guideline_tools_v2 import get_tone_guideline
from tools.booking.appointment_booking import create_booking_tools
from tools.state.state_tools import set_pending_intents, advance_intent
from tools.mcp_policy.mcp_tools import policy_mcp_tool
from tools.mcp_policy.mcp_tools import booking_mcp_tool
from .callback import reset_unrecognized_intent, count_unrecognized_intents
from google.adk.tools import AgentTool
from agents.policy_mcp_agent import policy_mcp_agent
from utils.agent_config import generate_content_config

def load_instructions(file_name):
    path = os.path.join(os.path.dirname(__file__), f"{file_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

model = os.getenv("MODEL_NAME", "gemini-2.5-flash")

tools = create_booking_tools()
tools.append(AgentTool(policy_mcp_agent))

tools.append(get_tone_guideline)
tools.append(track_frustration)
tools.append(flag_violation)
tools.append(record_unrecognized_intent)
tools.append(set_pending_intents)
tools.append(advance_intent)

booking_agent = Agent(
    model=model,
    name='booking_agent',
    description="Worker for booking, appointment and scheduling management",
    instruction=load_instructions("booking_agent_instruction"),
    tools=tools,
    after_model_callback=count_unrecognized_intents,
    generate_content_config=generate_content_config,
    before_agent_callback=reset_unrecognized_intent
)



