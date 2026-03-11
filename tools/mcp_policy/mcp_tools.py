import httpx
from google.adk.tools.mcp_tool import McpToolset as MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams


MAX_TIMEOUT = 30

def custom_mcp_client_factory(headers=None, timeout=None, auth=None):
    """Factory that creates an HTTPX client with 3 retries."""
    transport = httpx.AsyncHTTPTransport(retries=3)
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        auth=auth,
        transport=transport,
        follow_redirects=True
    )

policy_mcp_tool = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://gc-mcp-mock-1091311790583.asia-southeast1.run.app/policy/",
        timeout=MAX_TIMEOUT,
        httpx_client_factory=custom_mcp_client_factory
    ),
    tool_filter=["get_user_client_id_list", "get_user_policy_and_products"]
)

booking_mcp_tool = MCPToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://gc-mcp-mock-1091311790583.asia-southeast1.run.app/booking/",
        timeout=MAX_TIMEOUT,
        httpx_client_factory=custom_mcp_client_factory
    ),
)
