# prudential_mysql_server.py
#!/usr/bin/env python3
"""
    run: python prudential_mysql_server.py, to start mcp mysql server
"""

import asyncio
import json
import os
import sys
# import pymysql
# from pymysql.cursors import DictCursor
from typing import Dict, Any, List, Optional
from mcp import types as mcp_types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type


DB_CONFIG = {
    "host": "34.143.244.245",
    "connect_timeout": 30,
    "user": "mysqlusrgudedcare",
    "password": "Gu6C?ide%f^]8fpoc",
    "database": "mysqldb_guided_care_poc",
    "charset": "utf8mb4",
    # "cursorclass": DictCursor
}

# def get_user_policy(user_id: str= '123') -> str:
#     response = {
#         'policy_id': '936005',
#         'policy_number': 'CHA60YK3MV',
#         'proposal_number': 'WE4V1IZECM',
#         'product_code': 'PRUWL001',
#         'agent_number': 'IRM3ZY',
#         'party_id': '6H92DCL3',
#         'component_code': '8OLGB4'
#     }
#     return json.dumps(response, ensure_ascii=False, indent=2)


def get_user_policy_and_products(user_id: str='test_123', params: Optional[List[str]] = None) -> str:
    """
    use the user_id to retreive the policy and products detail
    
    Args:
        user_id: the user_id to get finnal data
        params: Optional list of parameters for the SQL query
    
    Returns:
        JSON format string with query results or execution status
    """
    # Construct the absolute path to the mock data file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    mock_data_path = os.path.join(current_dir, 'mock_policy_data.json')
    # use the user_id to get client_id 1st and the use client_id to get policy , products
    with open(mock_data_path) as f:
        data = json.load(f)
    response = {}
    for entry in data:
        if user_id == entry.get('user_id'):
            entry.pop('user_id', '')
            response = entry
            break
    # response = {
    #     "policy_id": "936005",
    #     "policy_number": "CHA60YK3MV",
    #     'policy_product_name': 'Whole Life Protection',
    #     'policy_product_category': 'Base',
    #     'policy_product_id': 'PRU001',
    #     'policy_product_description': 'Provides lifetime coverage with guaranteed cash value accumulation.',
    # }

    return json.dumps(response, ensure_ascii=False, indent=2)
   

# adk_tool_to_expose = FunctionTool(get_user_products)
app = Server("prudential-mysql-server")

GET_USER_POLICY_AND_PRODUCTS_SCHEMA = {
    "name": "get_user_policy_and_products",
    # "description": "Execute a MySQL query and return results. Only SELECT, SHOW, and DESC statements are supported for data retrieval.",
    "description": "use the user_id to retreive the user policy data, policy data also contains product details",
    "parameters": {
        "type": "object",
        "properties": {
            # "sql": {
            #     "type": "string",
            #     "description": "The complete SQL query string to execute. Example: 'SELECT * FROM contact LIMIT 10'"
            # },
            "user_id": {
                "type": "string",
                "description": "the user_id to get the policy"
            },
            "params": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional parameters for SQL prepared statements to prevent injection."
            }
        },
        "required": ["user_id"]
    }
}

# GET_USER_POLICY_SCHEMA = {
#     "name": "get_user_policy",
#     "description": "return the user policy",
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "user_id": {
#                 "type": "string",
#                 "description": "the user_id to get the policy"
#             }
#         },
#     "required": ["user_id"]
#     }
# }

@app.list_tools()
async def list_mcp_tools() -> List[mcp_types.Tool]:
    """
        List available MCP tools, Only returns get_user_products tool
    """
    # mcp_tool_schema = adk_to_mcp_tool_type(adk_tool_to_expose)
    # return [mcp_tool_schema]
    return [
        mcp_types.Tool(
            name=GET_USER_POLICY_AND_PRODUCTS_SCHEMA["name"],
            description=GET_USER_POLICY_AND_PRODUCTS_SCHEMA["description"],
            inputSchema=GET_USER_POLICY_AND_PRODUCTS_SCHEMA["parameters"]
        ),
        #  mcp_types.Tool(
        #     name=GET_USER_POLICY_SCHEMA["name"],
        #     description=GET_USER_POLICY_SCHEMA["description"],
        #     inputSchema=GET_USER_POLICY_SCHEMA["parameters"]
        # )
    ]


@app.call_tool()
async def call_mcp_tool(name: str, arguments: Dict[str, Any]) -> List[mcp_types.TextContent]:
    """
    Call MCP tool
    
    Args:
        name: Tool name
        arguments: Tool parameters
    
    Returns:
        MCP formatted response content
    """
 
    try:
        # sql = arguments.get("sql", "")
        user_id = arguments.get("user_id", "")
        params = arguments.get("params", [])
        
        # if not sql:
        #     return [mcp_types.TextContent(
        #         type="text",
        #         text=json.dumps({
        #             "success": False,
        #             "error": "missing_sql_parameter"
        #         }, ensure_ascii=False, indent=2)
        #     )]
        if name == 'get_user_policy_and_products':
            result = get_user_policy_and_products(user_id, params)
        # if name == 'get_user_policy':
        #     result = get_user_policy('123')
        
        return [mcp_types.TextContent(type="text", text=result)]
        
    except Exception as e:
        return [mcp_types.TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": f"error_call_tools: {str(e)}"
            }, ensure_ascii=False, indent=2)
        )]


async def main():
    '''main function to run the MCP server'''    
    # run mcp server over stdio
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="prudential-mysql-server",
                server_version="1.0.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                )
            )
        )

if __name__ == "__main__":

    print("🚀 start Prudential MySQL MCP server...", file=sys.stderr)
    # print(f"📊 db: {DB_CONFIG['database']}", file=sys.stderr)
    # print(f"📍 host : {DB_CONFIG['host']}", file=sys.stderr)
    print("🔧 available: get_user_policy_and_products", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("MCP stopped by user.", file=sys.stderr)
    except Exception as e:
        print(f"MCP server error: {e}", file=sys.stderr)
    finally:
        print("MCP server process exited.", file=sys.stderr)
