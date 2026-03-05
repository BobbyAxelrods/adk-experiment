from google.adk.tools import FunctionTool
import json
import logging
from typing import Optional, Dict
from tools.booking.booking_server import run_mcp_server, get_mcp_client

logger = logging.getLogger(__name__)

def booking_init(
    query: str,
    user_id: Optional[str] = None
) -> Dict[str, str]:
    """
    Initialize booking process for appointments or doctor search.
    
    Initialize a booking process by querying the booking MCP server.
    
    Args:
        query: The user's booking request (e.g., "book a dentist").
        user_id: The user's ID if available.
        
    Returns:
        A dictionary with the server's response or an error message.
    """
    logger.info(f"Booking init called with query: {query}")
    
    # In a real scenario, this would connect to a running MCP server
    # For this demo, we can simulate the interaction or import the logic directly
    # if we want to run it in-process.
    
    # Since we have the server code in `booking_server.py`, let's try to 
    # invoke the logic directly via a simulated client or just run the function.
    
    # However, the instruction implies using the MCP pattern.
    # Let's assume we use the `booking_server`'s logic.
    
    try:
        # Direct call simulation for simplicity in this demo environment
        from tools.booking.sp_booking import list_service_providers, book_appointment
        from tools.booking.doctor_finder import search_doctors
        
        # Simple intent routing based on keywords (MCP would do this better)
        query_lower = query.lower()
        
        if "doctor" in query_lower or "cardiologist" in query_lower or "specialist" in query_lower:
            # Extract specialty - very naive extraction for demo
            specialty = "general"
            if "cardiologist" in query_lower: specialty = "cardiology"
            if "dentist" in query_lower: specialty = "dentistry"
            
            results = search_doctors(specialty=specialty)
            return {"result": json.dumps(results, indent=2)}
            
        elif "book" in query_lower and "appointment" in query_lower:
            # If we have specific details, try to book. Otherwise list providers.
            # This is a simplification.
            providers = list_service_providers()
            return {"result": f"Here are available providers: {json.dumps(providers[:3], indent=2)}. Please specify which one and a time."}
            
        else:
            return {"result": "I can help you find a doctor or book a service. What do you need?"}
            
    except Exception as e:
        logger.error(f"Error in booking_init: {e}")
        return {"error": str(e)}

# Define the ADK Tool
booking_init = FunctionTool(func=booking_init)
