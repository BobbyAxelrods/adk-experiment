import asyncio
import json
import os
import sys
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

# Create FastMCP server
mcp = FastMCP("Policy Service")

def get_user_policy_and_products(user_id: str = 'test_123') -> str:
    """
    Retrieve policy and products detail for a user.
    
    Args:
        user_id: The user ID (e.g., 'test_123', 'test_456')
    
    Returns:
        JSON format string with policy details.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    mock_data_path = os.path.join(current_dir, 'mock_policy_data.json')
    
    try:
        with open(mock_data_path, 'r') as f:
            data = json.load(f)
            
        for entry in data:
            if user_id == entry.get('user_id'):
                # Return a copy without user_id to simulate external API response
                response = entry.copy()
                response.pop('user_id', None)
                return json.dumps(response, indent=2)
                
        return json.dumps({"error": "User not found", "user_id": user_id})
        
    except Exception as e:
        return json.dumps({"error": f"Failed to retrieve data: {str(e)}"})

def get_user_client_id_list(user_id: str) -> str:
    """
    Retrieve the list of client IDs associated with a user.

    Args:
        user_id: The user ID to look up.

    Returns:
        JSON format string with a list of client_ids.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    mock_data_path = os.path.join(current_dir, 'mock_policy_data.json')

    try:
        with open(mock_data_path, 'r') as f:
            data = json.load(f)

        client_ids = []
        for entry in data:
            if user_id == entry.get('user_id'):
                client_id = entry.get('client_id')
                if client_id and client_id not in client_ids:
                    client_ids.append(client_id)

        if not client_ids:
            # Fallback: return test client IDs for demo
            client_ids = ['test_123']

        return json.dumps({"client_ids": client_ids})

    except Exception as e:
        return json.dumps({"error": f"Failed to retrieve data: {str(e)}", "client_ids": ["test_123"]})


# Register the tools
mcp.tool()(get_user_client_id_list)
mcp.tool()(get_user_policy_and_products)

if __name__ == "__main__":
    asyncio.run(mcp.run())
