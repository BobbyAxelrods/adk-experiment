import asyncio
import logging
from mcp.server.fastmcp import FastMCP
from tools.booking.sp_booking import list_service_providers, get_service_provider, get_availability, book_appointment, cancel_appointment, get_user_bookings
from tools.booking.doctor_finder import search_doctors, get_doctor_details

# Initialize FastMCP server
mcp = FastMCP("Booking Service")

# Register tools from sp_booking.py
mcp.tool()(list_service_providers)
mcp.tool()(get_service_provider)
mcp.tool()(get_availability)
mcp.tool()(book_appointment)
mcp.tool()(cancel_appointment)
mcp.tool()(get_user_bookings)

# Register tools from doctor_finder.py
mcp.tool()(search_doctors)
mcp.tool()(get_doctor_details)

async def run_mcp_server():
    """Runs the MCP server."""
    await mcp.run()

def get_mcp_client():
    """Returns a client to interact with this server (if needed)."""
    # This is a placeholder as FastMCP usually runs as a standalone process
    pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_mcp_server())
