import os
from google.adk.agents import Agent
from dotenv import load_dotenv
import sys
import json
# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from typing import Dict, List, Any, Optional
from tools.mcp_policy.mcp_tools import policy_mcp_tool
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.base_tool import BaseTool
from google.genai import types
from .callback import reset_unrecognized_intent, count_unrecognized_intents
from utils.agent_config import generate_content_config
from prompts.manager import prompt_manager
from pydantic import BaseModel, Field


load_dotenv()
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
def after_tool_update_state_user_policy(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext, tool_response: Dict) -> Optional[Dict]:
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
                            # Split by semicolon, strip whitespace, and add to set
                            services = [s.strip() for s in vas_str.split(";") if s.strip()]
                            all_vas.update(services)
                    
                    # Assign aggregated VAS as a sorted list
                    item["product_vas"] = sorted(list(all_vas))
            
            enriched_policy_detail.append(item)

        # Update state only when we actually have policy data
        if enriched_policy_detail:
            tool_context.state['user_policy'] = enriched_policy_detail
            # Deduplicate product name list
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


def check_user_authentication(callback_context: CallbackContext) -> Optional[types.Content]:
    agent_name = callback_context.agent_name
    invocation_id = callback_context.invocation_id
    current_state = callback_context.state.to_dict()
    print(444, current_state)
    print(f"\n[Callback] Entering agent: {agent_name} (Inv: {invocation_id})")
    print(f"[Callback] Current State: {current_state}")

    if current_state.get('authentication'):
        print(f"[Callback] User authenticated: Proceeding with agent {agent_name}.")
        return None
    else:
        print(f"[Callback] State condition 'skip_llm_agent=True' met: Skipping agent {agent_name}.")
        return types.Content(
            parts=[types.Part(text=f"Please authenticate first by confirming your OTP code.")],
            role="model" 
        )


def load_instructions(instruction_file_name):
    """Legacy wrapper for backward compatibility or direct file loads if needed."""
    return prompt_manager.get_instruction(instruction_file_name)


class UserIdInput(BaseModel):
    user_id: str = Field(description="The user_id to search")


def my_before_tool_callback(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext) -> Optional[dict[str, Any]]:
    """Injects user_id from state into tool arguments before execution."""
    # just make sure the user_id would always added to args before call get_user_clint_id_list
    if tool.name == "get_user_client_id_list":
        user_id = tool_context.state.get("user_id")
        if user_id and user_id not in args:
            args["user_id"] = user_id
    return None 


policy_mcp_agent = Agent(
    name="policy_mcp_agent",
    model=LLM_MODEL,
    description="Agent with ability to call policy mcp tool when user ask their own policy or product",
    instruction=load_instructions("policy_mcp_agent"),
    generate_content_config=generate_content_config,
    tools=[policy_mcp_tool],
    after_tool_callback=after_tool_update_state_user_policy,
    before_agent_callback=check_user_authentication,
    before_tool_callback=my_before_tool_callback,
    after_model_callback=count_unrecognized_intents,

)
