import os
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from tools.policy_tools.policy_tools import flag_violation, report_violation_to_root, track_frustration
from tools.mcp_escalation.escalation_tools import escalate_to_human
from tools.tone_management.tone_guideline_tools import response_tone_guideline
from tools.booking.appointment_booking import create_booking_tools
from tools.mcp_policy.mcp_tools import policy_mcp_tool, booking_mcp_tool
from .callback import reset_unrecognized_intent, count_unrecognized_intents


def load_instructions(file_name):
    path = os.path.join(os.path.dirname(__file__), f"{file_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

model_name = os.getenv("MODEL_NAME", "gpt-4o")
litellm_model = LiteLlm(model=model_name)

tools = create_booking_tools()

tools.append(policy_mcp_tool)
tools.append(response_tone_guideline)
tools.append(flag_violation)
tools.append(report_violation_to_root)
tools.append(escalate_to_human)
tools.append(track_frustration)

booking_agent = Agent(
    model=litellm_model,
    name='booking_agent',
    description="Worker for booking appointments",
    instruction=load_instructions("booking_agent_instruction"),
    tools=tools,
    after_model_callback=count_unrecognized_intents,
    before_agent_callback=reset_unrecognized_intent

)



