import os
from typing import Optional
from enum import Enum
from google.adk.tools import FunctionTool, ToolContext

class ToneCategory(str, Enum):
    FALLBACK = "fallback"
    EXITFLOW = "exitflow"
    SYSTEM_GENERAL = "system_general"
    HEALTH_ACTION = "health_action"
    HEALTH_ASSURANCE = "health_assurance"
    REENGAGEMENT = "reengagement"
    SPECIALITY_CARE = "speciality_care"

PEACE_OF_MIND_FORMULA = """
    1. Empathise: Acknowledge the user's feelings, situation, or effort first. Use warm, human language.
    2. Guide: Give a clear next step or factual answer. Avoid jargon. Keep sentences short (12-18 words).
    3. Reassure: End with a calm, confident statement that reinforces Prudential's support.
    """

TONE_GROUP_FILE_MAP = {
    ToneCategory.FALLBACK: "fallback.md",
    ToneCategory.EXITFLOW: "exitflow.md",
    ToneCategory.SYSTEM_GENERAL: "foundation.md",
    "foundation": "foundation.md",
    ToneCategory.HEALTH_ACTION: "health_action.md",
    ToneCategory.HEALTH_ASSURANCE: "health_reassurance.md",
    ToneCategory.REENGAGEMENT: "reengagement.md",
    ToneCategory.SPECIALITY_CARE: "special_care.md",
}

def set_tone_group(tool_context: ToolContext, tone_group: str, reason: str) -> dict:
    """
    Set the current tone group.
    
    Call this when the conversation context shifts and a different tone is needed.
    Sets the active tone group in session state.

    Args:
        tone_group: The new tone category to switch to.
        reason: Brief explanation of why this tone was selected.
    """
    previous = tool_context.state.get("tone_group", "system_general")
    tool_context.state["tone_group"] = tone_group
    tool_context.state["tone_reason"] = reason

    return {
        "previous_tone": previous,
        "current_tone":  tone_group,
        "reason":        reason,
        "status":        "tone_updated"
    }

def _resolve_tone_file(group: str | ToneCategory) -> str:
    key = group.value if isinstance(group, ToneCategory) else str(group).strip().lower().replace(" ", "_")
    
    if "health_action" in key: key = ToneCategory.HEALTH_ACTION
    elif "health_assurance" in key or "health_reassurance" in key: key = ToneCategory.HEALTH_ASSURANCE
    elif "reengagement" in key or "re-engagement" in key: key = ToneCategory.REENGAGEMENT
    elif "speciality_care" in key or "specialty_care" in key or "special_care" in key: key = ToneCategory.SPECIALITY_CARE
    elif "exit" in key: key = ToneCategory.EXITFLOW
    elif "fallback" in key: key = ToneCategory.FALLBACK
    elif "foundation" in key or "system" in key: key = ToneCategory.SYSTEM_GENERAL
    
    return TONE_GROUP_FILE_MAP.get(key, "foundation.md")


def _load_tone_markdown(filename: str) -> str:
    # Adjust path to match our structure: root/tone_group/filename
    # This file is in root/tools/tone_management/
    # So we go up 2 levels to root, then into tone_group
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tone_group_dir = os.path.join(root_dir, "tone_group")
    
    path = os.path.join(tone_group_dir, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return ""

def response_tone_guideline(tone_category: str, user_mood: Optional[str] = None) -> str:
    """
    Get tone guidelines.
    
    Provides a comprehensive guideline for the agent to construct a response with the correct tone.
    """
    # Convert string to Enum if possible, or let _resolve_tone_file handle it
    filename = _resolve_tone_file(tone_category)
    specific_guidelines = _load_tone_markdown(filename)
    foundation_guidelines = _load_tone_markdown("foundation.md")
    
    display_name = str(tone_category)
    guidance = f"## RESPONSE TONE GUIDELINES: {display_name.upper()}\n\n"
    
    if user_mood:
        guidance += f"### USER MOOD DETECTED: {user_mood.upper()}\n"
        guidance += f"Tailor your empathy and reassurance to specifically address this mood.\n\n"
    
    guidance += "### 1. THE PEACE-OF-MIND FORMULA (STRICTLY FOLLOW)\n"
    guidance += PEACE_OF_MIND_FORMULA + "\n"
    
    guidance += "### 2. CORE RULES\n"
    guidance += "- Max 20 words per sentence.\n"
    guidance += "- No jargon (e.g., no 'journey', 'ecosystem', 'orchestration').\n"
    guidance += "- Use 'help', 'support', 'team' instead of 'Guided Care'.\n\n"
    
    if foundation_guidelines:
        guidance += "### 3. FOUNDATION GUIDELINES\n"
        guidance += foundation_guidelines + "\n\n"
        
    if specific_guidelines and filename != "foundation.md":
        guidance += f"### 4. SPECIFIC CATEGORY GUIDELINES: {tone_category.upper()}\n"
        guidance += specific_guidelines + "\n"
        
    return guidance

# ADK Tool Definitions
set_tone_group = FunctionTool(func=set_tone_group)
response_tone_guideline_tool = FunctionTool(func=response_tone_guideline)
