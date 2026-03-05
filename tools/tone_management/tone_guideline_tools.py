from .test_tone_guideline import *
from .test_tone_guideline import response_tone_guideline as _response_tone_guideline_fn, ToneCategory, response_tone_guideline_tool
from google.adk.tools import FunctionTool

# Export response_tone_guideline as a FunctionTool (alias for response_tone_guideline_tool)
response_tone_guideline = response_tone_guideline_tool
