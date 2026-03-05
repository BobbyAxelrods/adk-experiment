import json
import os
import uuid
from typing import List, Dict, Optional
from datetime import datetime

# Load mock data
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "mcp_mock_data")

def _load_data(filename: str) -> List[Dict]:
    try:
        with open(os.path.join(DATA_DIR, filename), "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# In-memory storage for bookings for this session/demo
# In a real app, this would be a database
_bookings = []

def list_service_providers(category: Optional[str] = None) -> List[Dict]:
    """List available service providers (clinics, hospitals)."""
    providers = _load_data("providers.json")
    if not category:
        return providers
    
    return [p for p in providers if p.get("category") == category]

def get_service_provider(provider_id: str) -> Optional[Dict]:
    """Get details of a specific provider."""
    providers = _load_data("providers.json")
    for p in providers:
        if p["id"] == provider_id:
            return p
    return None

def get_availability(provider_id: str, date: str) -> List[str]:
    """Get available slots for a provider on a given date (YYYY-MM-DD)."""
    # Mock logic: generate some slots
    return ["09:00", "10:00", "14:00", "15:30"]

def book_appointment(provider_id: str, user_id: str, date: str, time: str, service_type: str) -> Dict:
    """Book an appointment."""
    booking_id = str(uuid.uuid4())
    booking = {
        "id": booking_id,
        "provider_id": provider_id,
        "user_id": user_id,
        "date": date,
        "time": time,
        "service_type": service_type,
        "status": "confirmed",
        "created_at": datetime.now().isoformat()
    }
    _bookings.append(booking)
    return booking

def cancel_appointment(booking_id: str) -> bool:
    """Cancel an appointment."""
    global _bookings
    for b in _bookings:
        if b["id"] == booking_id:
            b["status"] = "cancelled"
            return True
    return False

def get_user_bookings(user_id: str) -> List[Dict]:
    """Get all bookings for a user."""
    return [b for b in _bookings if b["user_id"] == user_id]
