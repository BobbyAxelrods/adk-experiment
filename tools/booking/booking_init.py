import os
import sys
from google.adk.tools.mcp_tool import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioServerParameters


PATH_TO_MCP_SCRIPT = os.path.join(os.path.dirname(__file__), 'booking_server.py')
print('mcp_server_path', PATH_TO_MCP_SCRIPT)
booking_init = MCPToolset(
    connection_params=StdioServerParameters(
        command=sys.executable,
        args=[PATH_TO_MCP_SCRIPT],
    ),
)
