import os
from google.adk.agents import Agent
from tools.booking.booking_init import booking_init
from google.adk.models.lite_llm import LiteLlm
from .callback import reset_turn_detection, count_unrecognized_intents, reset_unrecognized_intent
from tools.tone_management.tone_guideline_tools import response_tone_guideline

def load_instructions(file_name):
    path = os.path.join(os.path.dirname(__file__), f"{file_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

model_name = os.getenv("MODEL_NAME", "gpt-4o")
litellm_model = LiteLlm(model=model_name)

booking_agent = Agent(
    name="booking_agent",
    model=litellm_model,
    description="Worker for booking appointments",
    instruction=load_instructions("booking_agent_instruction"),
    tools=[booking_init, response_tone_guideline],
    before_agent_callback=reset_unrecognized_intent,
    before_model_callback=reset_turn_detection,
    after_model_callback=count_unrecognized_intents,
)
