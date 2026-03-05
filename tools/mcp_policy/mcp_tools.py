import os
from google.adk.tools.mcp_tool import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams, StdioServerParameters

PATH_TO_MCP_SCRIPT = os.path.join(os.path.dirname(__file__), 'mysql_server.py')

# In a real environment, this would connect to a running MCP server.
# For demo purposes, we can try to run the script directly via Stdio or connect to a URL.
# Since we are rebuilding, let's use StdioServerParameters pointing to our local script.

policy_mcp_tool = MCPToolset(
    connection_params=StdioServerParameters(
        command='python',
        args=[
            PATH_TO_MCP_SCRIPT
        ],
    ),
    # If using HTTP:
    # connection_params=StreamableHTTPConnectionParams(
    #     url="http://localhost:8080/policy",
    #     timeout=15
    # ),
    tool_filter=["get_user_client_id_list", "get_user_policy_and_products"]
)
