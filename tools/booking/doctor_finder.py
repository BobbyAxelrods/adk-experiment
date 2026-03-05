import json
import os
from typing import List, Dict, Optional

# Load mock data
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "mcp_mock_data")

def _load_data(filename: str) -> List[Dict]:
    try:
        with open(os.path.join(DATA_DIR, filename), "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def search_doctors(specialty: Optional[str] = None, location: Optional[str] = None, name: Optional[str] = None) -> List[Dict]:
    """
    Search for doctors based on specialty, location, or name.
    """
    doctors = _load_data("doctors.json")
    results = []
    
    for doc in doctors:
        match = True
        if specialty and specialty.lower() not in doc.get("specialty", "").lower():
            match = False
        if location and location.lower() not in doc.get("location", "").lower():
            match = False
        if name and name.lower() not in doc.get("name", "").lower():
            match = False
        
        if match:
            results.append(doc)
            
    return results

def get_doctor_details(doctor_id: str) -> Optional[Dict]:
    """
    Get detailed information about a specific doctor.
    """
    doctors = _load_data("doctors.json")
    for doc in doctors:
        if doc["id"] == doctor_id:
            return doc
    return None
