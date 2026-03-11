import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from google.adk.agents.llm_agent import Agent

from typing import List, Dict, Any, Optional
from thefuzz import fuzz  # Import the fuzzy logic library

DB_FILE = "tools/booking/mock_db.json" # tools/booking/mock_db.json

def load_db() -> dict:
    if not os.path.exists(DB_FILE):
        raise FileNotFoundError(f"{DB_FILE} not found. Please create it.")
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data: dict):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

#patient_id: str, policy_id: str
def create_booking_tools():

    def get_current_datetime() -> str:
        """Returns the current date and time in Hong Kong (HKT / UTC+8)."""
        hk_timezone = timezone(timedelta(hours=8))
        return datetime.now(hk_timezone).strftime("%Y-%m-%d %H:%M:%S")

    # def search_in_network_providers(
    #     specialty: Optional[str] = None, 
    #     district: Optional[str] = None, 
    #     name: Optional[str] = None,
    #     policy_id: str = "",
    # ) -> List[Dict[str, Any]]:
    #     """
    #     Searches for in-network doctors. You can search by specialty, district, or doctor name.
        
    #     Args:
    #         specialty: (Optional) Medical specialty (e.g. 'general_practice', 'cardiology').
    #         district: (Optional) HK district name (e.g. 'Wan Chai', 'Central').
    #         name: (Optional) Doctor's name (e.g. 'James Wong').
    #     """
    #     if policy_id == "":
    #         return "Please provide a policy_id"

    #     db = load_db()
    #     policy = db["policies"].get(policy_id)
        
    #     in_network_ids = policy.get("in_network_provider_ids", [])
    #     matching_providers = []
        
    #     for prov_id in in_network_ids:
    #         provider = db["providers"].get(prov_id)
    #         if not provider:
    #             continue
                
    #         # 1. Filter by specialty (if provided)
    #         if specialty:
    #             search_spec = "general_practice" if specialty.lower() in ["gp", "general practice"] else specialty.lower()
    #             if provider["specialty"].lower() != search_spec:
    #                 continue
                
    #         # 2. Filter by district (if provided, fuzzy match)
    #         if district and district.lower() not in provider["district"].lower():
    #             continue
                
    #         # 3. Filter by name (if provided, fuzzy match)
    #         if name and name.lower() not in provider["name"].lower():
    #             continue
                
    #         matching_providers.append({
    #             "provider_id": prov_id,
    #             "name": provider["name"],
    #             "specialty": provider["specialty"],
    #             "district": provider["district"]
    #         })
                
    #     return matching_providers


    def search_in_network_providers(
        specialty: Optional[str] = None, 
        district: Optional[str] = None, 
        name: Optional[str] = None,
        policy_id: str = "",
    ) -> List[Dict[str, Any]]:

        if policy_id == "":
            return "Please provide a policy_id"

        db = load_db()
        policy = db["policies"].get(policy_id) # if missing what it returnn > null 
        try: 
            in_network_ids = policy.get("in_network_provider_ids", [])
        except:
            return "no matching ID's found, please enter correct ID's"

        matching_providers = []
        
        # Threshold: How strict do you want to be? 
        # 80 is usually a good balance. 100 is exact match, 0 is anything.
        MATCH_THRESHOLD = 80 

        for prov_id in in_network_ids:
            provider = db["providers"].get(prov_id)
            if not provider:
                continue
                
            # 1. Fuzzy Filter by specialty
            if specialty:
                # partial_ratio works great for "Immunologist" -> "Immunology"
                # It checks if the search term is 'mostly' inside the DB field.
                score = fuzz.partial_ratio(specialty.lower(), provider["specialty"].lower())
                
                # Special handling for GP because "GP" is too short for fuzzy matching 
                # (e.g., "GP" might fuzzy match to "Gastroenteropathology" or "Group")
                if specialty.lower() in ['gp', 'general practice']:
                    if 'general practice' not in provider["specialty"].lower():
                        continue
                elif score < MATCH_THRESHOLD:
                    continue
                
            # 2. Fuzzy Filter by district
            if district:
                score = fuzz.partial_ratio(district.lower(), provider["district"].lower())
                if score < MATCH_THRESHOLD:
                    continue
                
            # 3. Fuzzy Filter by name
            if name:
                score = fuzz.partial_ratio(name.lower(), provider["name"].lower())
                if score < MATCH_THRESHOLD:
                    continue
                
            matching_providers.append({
                "provider_id": prov_id,
                "name": provider["name"],
                "specialty": provider["specialty"],
                "district": provider["district"]
            })
                
        return matching_providers

    def get_provider_availability(provider_id: str, date: str) -> List[str]:
        """Checks a specific provider's schedule to find available times on a given date."""
        db = load_db()
        provider = db["providers"].get(provider_id)
        if not provider: return []
            
        daily_schedule = provider.get("daily_schedule", [])
        booked_times = [
            appt["time"] for appt in db["appointments"].values()
            if appt["provider_id"] == provider_id and appt["date"] == date
        ]
        
        return [t for t in daily_schedule if t not in booked_times]

    def get_available_districts(policy_id: str) -> List[str]:
        """Returns a list of all Hong Kong districts where we have in-network doctors."""
        db = load_db()
        policy = db["policies"].get(policy_id)
        try: 
            in_network_ids = policy.get("in_network_provider_ids", [])
        except:
            return "no matching ID's found, please enter correct ID's"
        # in_network_ids = policy.get("in_network_provider_ids", [])
        districts = set()
        
        for prov_id in in_network_ids:
            provider = db["providers"].get(prov_id)
            if provider:
                districts.add(provider["district"])
                
        return sorted(list(districts))


    def book_appointment(provider_id: str, date: str, time: str, patient_id: str, policy_id: str) -> Dict[str, Any]:
        """Books the appointment."""
        db = load_db()
        provider = db["providers"].get(provider_id)
        
        hk_timezone = timezone(timedelta(hours=8))
        today_date = datetime.now(hk_timezone).strftime("%Y-%m-%d")
        if date < today_date:
            return {"error": "Cannot book appointments in the past."}
            
        if not provider:
            return {"error": "Provider not found."}
            
        booked_times = [
            a["time"] for a in db["appointments"].values() 
            if a["provider_id"] == provider_id and a["date"] == date
        ]
        if time not in provider["daily_schedule"] or time in booked_times:
            return {"error": f"Time slot {time} on {date} is not available."}
            
        appointment_id = f"APT_{str(uuid.uuid4())[:8].upper()}"
        
        db["appointments"][appointment_id] = {
            "patient_id": patient_id,
            "policy_id": policy_id, 
            "provider_id": provider_id,
            "date": date,
            "time": time,
            "status": "CONFIRMED"
        }
        save_db(db)
        
        return {
            "status": "success",
            "appointment_id": appointment_id,
            "message": f"Appointment confirmed with {provider['name']} in {provider['district']} on {date} at {time}."
        }
    
    
    return [
        get_current_datetime, 
        search_in_network_providers, 
        get_provider_availability, 
        book_appointment, 
        get_available_districts]

