import os
from typing import Optional, Dict, List, Any
from google.adk.models.lite_llm import LiteLlm 
from dotenv import load_dotenv
import litellm
from google.adk.tools import FunctionTool

load_dotenv()

def classify_tone_group(query: str, factual_context_found: bool = True) -> str:
    """
    Classify the tone of the user's query.
    
    Classifies the user query into one of the core Prudential tone groups.
    """
    prompt = f"""
    You are a Prudential tone router. Classify the user query into exactly ONE of
    these tone groups:

    - exitflow: User wants to end or pause: thanks, goodbye, stop, unsubscribe.
    - fallback: Emotional distress, confusion, or explicit human/medical help.
    - system_general: Everyday support, general questions, greetings, neutral info.
    - health_action: Clear next-step health actions: screening, booking, forms.
    - health_assurance: Reassurance about health, results, or coverage.
    - reengagement: Win-back or nudge after drop-off.
    - speciality_care: Complex or specialist care, referrals, or serious conditions.

    User Query: "{query}"

    Output only ONE of these exact lowercase labels:
    fallback, exitflow, system_general, health_action, health_assurance,
    reengagement, speciality_care.
    """
    
    try:
        # USE LITELLM
        model_name = os.getenv("MODEL_NAME", "gpt-4o")
        completion = litellm.completion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content.strip().lower()

    except Exception as e:
        print(f"Error in classify_tone_group: {e}")
        return "system_general"

# ADK Tool Definition
classify_tone_group = FunctionTool(func=classify_tone_group)
