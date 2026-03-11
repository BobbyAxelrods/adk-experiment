from enum import Enum
from google.adk.tools import FunctionTool
from prompts.manager import prompt_manager


class ToneCategory(str, Enum):
    FALLBACK         = "fallback"
    EXITFLOW         = "exitflow"
    SYSTEM_GENERAL   = "system_general"
    HEALTH_ACTION    = "health_action"
    HEALTH_ASSURANCE = "health_assurance"
    REENGAGEMENT     = "reengagement"
    SPECIALITY_CARE  = "speciality_care"



def get_tone_guideline(tone_category: str) -> str:
    """
    Returns tone guidelines for the given category.
    Always loads system_general (foundation layer) + the specific category file.
    File keys match ToneCategory enum values exactly.
    Falls back to system_general if tone_category is unrecognised.
    """
    try:
        category = ToneCategory(tone_category)
    except ValueError:
        category = ToneCategory.SYSTEM_GENERAL

    foundation = prompt_manager.get_tone_group("system_general")
    specific   = prompt_manager.get_tone_group(category.value) if category != ToneCategory.SYSTEM_GENERAL else ""

    return f"{foundation}\n\n{specific}".strip() if specific else foundation


get_tone_guideline = FunctionTool(func=get_tone_guideline)
