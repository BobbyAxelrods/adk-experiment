import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP
from fastapi import Request, Response

# Create FastMCP server instance
mcp = FastMCP("Policy Service API")


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
            client_ids = ['test_123']

        return json.dumps({"client_ids": client_ids})

    except Exception as e:
        return json.dumps({"error": f"Failed to retrieve data: {str(e)}", "client_ids": ["test_123"]})


def get_user_policy_and_products(user_id: str = 'test_123') -> str:
    """
    Retrieve policy and products detail for a user.

    Args:
        user_id: The user ID (e.g., 'test_123', 'test_456', 'test_789')

    Returns:
        JSON format string with policy details.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    mock_data_path = os.path.join(current_dir, 'mock_policy_data.json')

    try:
        with open(mock_data_path, 'r') as f:
            data = json.load(f)

        results = []
        for entry in data:
            if user_id == entry.get('user_id') or user_id == entry.get('client_id'):
                response = entry.copy()
                response.pop('user_id', None)
                results.append(response)

        if results:
            return json.dumps(results, indent=2)

        return json.dumps({"error": "User not found", "user_id": user_id})

    except Exception as e:
        return json.dumps({"error": f"Failed to retrieve data: {str(e)}"})


# Register tools
mcp.tool()(get_user_client_id_list)
mcp.tool()(get_user_policy_and_products)


def create_mcp_lifespan_and_handler():
    """
    Create and return the MCP lifespan context manager and ASGI handler.
    Used by start_local_mcp_server.py to mount MCP endpoints.
    """
    @asynccontextmanager
    async def lifespan(app):
        yield

    async def handler(scope, receive, send):
        if scope["type"] == "http":
            request = Request(scope, receive)
            # Simple passthrough for MCP SSE/streamable HTTP
            response = Response(content="MCP handler active", media_type="text/plain")
            await response(scope, receive, send)

    return lifespan, handler
