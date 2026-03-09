import os
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from dotenv import load_dotenv
import sys
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from typing import Dict, List, Any, Optional
from tools.mcp_policy.mcp_tools import policy_mcp_tool
from agents._fragments.loader import load_instruction
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.base_tool import BaseTool
from google.genai import types
from .callback import reset_unrecognized_intent, count_unrecognized_intents
from tools.policy_tools.policy_tools import flag_violation, report_violation_to_root, track_frustration, record_unrecognized_intent
from tools.mcp_escalation.escalation_tools import escalate_to_live_agent


load_dotenv()

model_name = os.getenv("MODEL_NAME", "gpt-4o")
litellm_model = LiteLlm(model=model_name)


def after_tool_update_state_user_policy(
     tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext, tool_response: Dict
) -> Optional[Dict]:
    '''
        Update the user_policy data to state and enrich tool response after getting
        the data from get_user_policy_and_products.
    '''
    tool_name = tool.name

    # ONLY perform enrichment and state updates for the specific policy detail tool
    if tool_name != 'get_user_policy_and_products':
        return None

    print(f"[Callback] Processing tool '{tool_name}' in agent '{tool_context.agent_name}'")

    try:
        # The tool response content is a JSON string that needs to be parsed.
        content_list = tool_response.get('content', [])
        if not content_list:
            return None

        policy_data_string = content_list[0].get('text', '[]')
        policy_detail = json.loads(policy_data_string)

        if not isinstance(policy_detail, list):
            return None

        # load product context for enrichment
        products_json_path = os.path.join(os.path.dirname(__file__), '../tools/corpus/prudential_products.json')
        product_metadata = []
        try:
            with open(products_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                product_metadata = data.get("Product", [])
        except Exception as e:
            print(f"Error loading prudential_products.json: {e}")

        # enrich policy details and collect product names
        product_names = []
        enriched_policy_detail = []
        for item in policy_detail:
            if not isinstance(item, dict):
                continue

            product_name = item.get("policy_product_name")
            if product_name:
                product_names.append(product_name)

                # Find all matching metadata entries for this product
                matches = [m for m in product_metadata if m.get("Product") == product_name]

                if matches:
                    # Set the URL from the first match found
                    item["product_url"] = matches[0].get("URL")

                    # Aggregate all unique VAS services
                    all_vas = set()
                    for m in matches:
                        vas_str = m.get("VAS", "NA")
                        if vas_str and vas_str != "NA":
                            services = [s.strip() for s in vas_str.split(";") if s.strip()]
                            all_vas.update(services)

                    item["product_vas"] = sorted(list(all_vas))

            enriched_policy_detail.append(item)

        # Update state only when we actually have policy data
        if enriched_policy_detail:
            tool_context.state['user_policy'] = enriched_policy_detail
            tool_context.state['user_product_name_list'] = list(dict.fromkeys(product_names))

            print(f"Updated user_policy in state with {len(enriched_policy_detail)} items")
            print(f"Updated user_product_name_list in state: {tool_context.state.get('user_product_name_list')}")

        # Return modified tool_response so the agent receives enriched data
        new_response = dict(tool_response)
        new_response['content'] = [dict(c) for c in tool_response['content']]
        new_response['content'][0]['text'] = json.dumps(enriched_policy_detail, ensure_ascii=False, indent=2)
        return new_response

    except Exception as e:
        print(f"Error in after_tool_update_state_user_policy: {e}")
        return None


def _require_authentication_before_policy_lookup(
    callback_context: CallbackContext,
    llm_request: Optional[LlmRequest] = None,
    **kwargs: Any,
) -> Optional[LlmResponse]:
    state_obj = callback_context.state
    state: Dict[str, Any]
    if hasattr(state_obj, "to_dict"):
        state = state_obj.to_dict()
    else:
        state = state_obj  # type: ignore[assignment]

    auth_value = state.get("authentication")
    is_authenticated = False
    
    if isinstance(auth_value, bool):
        is_authenticated = auth_value
    elif isinstance(auth_value, str):
        is_authenticated = auth_value.lower() == "true"
    
    print(f"[Callback] Checking auth in {callback_context.agent_name}. Value: {auth_value} (Type: {type(auth_value)}), Is Authenticated: {is_authenticated}")

    if is_authenticated:
        # If user is authenticated, explicitly set required flag to False
        # This signals the prompt gate that it's safe to proceed
        callback_context.state["authentication_required"] = False
        return None

    try:
        callback_context.state["authentication_required"] = True
        # callback_context.state["authentication_required_agent"] = callback_context.agent_name
    except Exception:
        pass

    return None


policy_mcp_agent = Agent(
    name="policy_mcp_agent",
    model=litellm_model,
    description="Agent with ability to call policy mcp tool when user ask their own policy or product",
    instruction=load_instruction("policy_mcp_agent"),
    tools=[
        policy_mcp_tool,
        flag_violation,
        report_violation_to_root,
        track_frustration,
        record_unrecognized_intent,
        escalate_to_live_agent
    ],
    after_tool_callback=after_tool_update_state_user_policy,
    before_model_callback=_require_authentication_before_policy_lookup,
    before_agent_callback=reset_unrecognized_intent,
    after_model_callback=count_unrecognized_intents,
)
