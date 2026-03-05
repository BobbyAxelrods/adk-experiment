import unittest
import sys
import os
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock dependencies (only for importing policy_tools). Must not leak into other tests.
_original_google_adk_tools = sys.modules.get("google.adk.tools")
sys.modules["google.adk.tools"] = MagicMock()

def side_effect_function_tool(func, **kwargs):
    return func

sys.modules["google.adk.tools"].FunctionTool = side_effect_function_tool

# Explicitly load the module from file path because standard import is being weird
import importlib.util
file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "policy_tools", "policy_tools.py")
spec = importlib.util.spec_from_file_location("policy_tools", file_path)
policy_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy_tools)

if _original_google_adk_tools is None:
    sys.modules.pop("google.adk.tools", None)
else:
    sys.modules["google.adk.tools"] = _original_google_adk_tools

track_frustration = policy_tools.track_frustration

class TestFrustrationTool(unittest.TestCase):
    def setUp(self):
        # Setup mock context with state
        self.state = {"frustration_count": 0, "escalation_recommended": False}
        # Since we mocked ToolContext as a MagicMock, we can't use it as a spec.
        # Just create a MagicMock directly.
        self.tool_context = MagicMock()
        self.tool_context.state = self.state

    def test_increments_count(self):
        # First call
        print(f"DEBUG: Before call state: {self.tool_context.state}")
        result = track_frustration(self.tool_context)
        print(f"DEBUG: After call state: {self.tool_context.state}")
        
        self.assertEqual(self.state["frustration_count"], 1)
        self.assertEqual(result["frustration_count"], 1)
        self.assertFalse(result["escalation_recommended"])

    def test_triggers_escalation_at_threshold(self):
        # Set count to 2 (threshold is 3)
        self.state["frustration_count"] = 2
        
        # Call tool (should hit 3)
        result = track_frustration(self.tool_context)
        
        self.assertEqual(self.state["frustration_count"], 3)
        self.assertTrue(self.state["escalation_recommended"])
        self.assertTrue(result["escalation_recommended"])
        self.assertIn("hint", result)

    def test_continues_escalation_above_threshold(self):
        self.state["frustration_count"] = 5
        
        result = track_frustration(self.tool_context)
        
        self.assertEqual(self.state["frustration_count"], 6)
        self.assertTrue(result["escalation_recommended"])

if __name__ == "__main__":
    unittest.main()
