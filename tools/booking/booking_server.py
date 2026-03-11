from mcp.server.fastmcp import FastMCP
from sp_booking import _register_sp_booking_tools as register_sp_booking_tools
from doctor_finder import _register_doctor_finder_tools as register_doctor_finder_tools


mcp = FastMCP("PHKL MCP (Modular)", json_response=True)

register_doctor_finder_tools(mcp)
register_sp_booking_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="stdio")


