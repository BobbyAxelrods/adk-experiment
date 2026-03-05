import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock 'agents.agent' and 'agents.rag_agent' etc to prevent heavy imports
# We need to do this BEFORE importing agents.callbacks if agents/__init__.py triggers them
sys.modules["agents.agent"] = MagicMock()
sys.modules["agents.rag_agent"] = MagicMock()
sys.modules["agents.booking_agent"] = MagicMock()
sys.modules["agents.escalation_agent"] = MagicMock()
sys.modules["tools.corpus.corpus_tools"] = MagicMock()
sys.modules["vertexai"] = MagicMock()

# Mock tools dependencies used in callbacks.py
mock_tone = MagicMock()
mock_tone.response_tone_guideline = MagicMock()
mock_tone.ToneCategory = MagicMock()
sys.modules["tools.tone_management.test_tone_guideline"] = mock_tone

mock_policy = MagicMock()
mock_policy.policy_tools = MagicMock()
sys.modules["tools.policy_tools"] = mock_policy
sys.modules["tools.policy_tools.policy_tools"] = mock_policy # Ensure both paths work if needed

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse, LlmRequest
from google.genai import types

# Manually import the file to avoid package init issues if necessary, 
# but hopefully the mocks above are enough.
from agents.callback import count_unrecognized_intents, reset_unrecognized_intent

class TestUnrecognizedIntentCallbacks(unittest.TestCase):
    def setUp(self):
        self.state = {"unrecognized_intent_count": 0, "escalation_recommended": False}
        self.callback_context = MagicMock(spec=CallbackContext)
        self.callback_context.state = self.state

    def test_count_increments_on_no_tool_calls(self):
        # Response with no tool calls
        # Note: LlmResponse structure depends on the library version, mocking what's used in callbacks.py
        response = MagicMock(spec=LlmResponse)
        response.content = MagicMock()
        response.content.parts = [MagicMock()]
        response.content.parts[0].function_call = None # No function call
        
        count_unrecognized_intents(self.callback_context, response)
        
        self.assertEqual(self.state["unrecognized_intent_count"], 1)
        self.assertFalse(self.state["escalation_recommended"])

    def test_escalation_triggered_after_threshold(self):
        self.state["unrecognized_intent_count"] = 2
        
        response = MagicMock(spec=LlmResponse)
        response.content = MagicMock()
        response.content.parts = [MagicMock()]
        response.content.parts[0].function_call = None
        
        count_unrecognized_intents(self.callback_context, response)
        
        self.assertEqual(self.state["unrecognized_intent_count"], 0)
        self.assertTrue(self.state["escalation_recommended"])

    def test_count_does_not_increment_on_tool_calls(self):
        # Response WITH tool calls
        response = MagicMock(spec=LlmResponse)
        response.content = MagicMock()
        part = MagicMock()
        part.function_call = MagicMock() # Has function call
        response.content.parts = [part]
        
        count_unrecognized_intents(self.callback_context, response)
        
        self.assertEqual(self.state["unrecognized_intent_count"], 0)

    def test_tool_call_does_not_increment_even_if_fallback_tone(self):
        self.state["unrecognized_intent_count"] = 2

        response = MagicMock(spec=LlmResponse)
        response.content = MagicMock()
        part = MagicMock()
        function_call = MagicMock()
        function_call.name = "response_tone_guideline"
        function_call.args = {"tone_category": "fallback"}
        part.function_call = function_call
        response.content.parts = [part]

        overridden = count_unrecognized_intents(self.callback_context, response)

        self.assertEqual(self.state["unrecognized_intent_count"], 2)
        self.assertFalse(self.state["escalation_recommended"])
        self.assertEqual(overridden, response)

    def test_reset_callback(self):
        self.state["unrecognized_intent_count"] = 3
        request = MagicMock(spec=LlmRequest)
        
        reset_unrecognized_intent(self.callback_context, request)
        
        self.assertEqual(self.state["unrecognized_intent_count"], 0)

if __name__ == "__main__":
    unittest.main()
