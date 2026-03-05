import json
import uuid
import time
from typing import Dict, Any, Optional

class SessionManager:
    def __init__(self):
        # In-memory storage: { "phone_number": { "session_id": "...", "user_id": "...", "created_at": timestamp, "user_info": {} } }
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self.TTL_SECONDS = 2 * 60 * 60  # 2 hours

    def get_or_create_session(self, phone_number: str) -> Dict[str, Any]:
        current_time = time.time()
        
        # Check if session exists and is valid
        if phone_number in self._sessions:
            session = self._sessions[phone_number]
            if current_time - session["created_at"] < self.TTL_SECONDS:
                # Refresh timestamp? Optional. Let's keep strict 2hr window for now or refresh on activity.
                session["created_at"] = current_time # Refresh TTL on activity
                return session
        
        # Create new session
        new_session_id = str(uuid.uuid4())
        # Default user_id is phone number until identified
        new_session = {
            "session_id": new_session_id,
            "user_id": phone_number, 
            "created_at": current_time,
            "user_info": None
        }
        self._sessions[phone_number] = new_session
        return new_session

    def update_session(self, phone_number: str, user_id: str, user_info: Dict[str, Any]):
        if phone_number in self._sessions:
            self._sessions[phone_number]["user_id"] = user_id
            self._sessions[phone_number]["user_info"] = user_info

    def get_session(self, phone_number: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(phone_number)

# Singleton instance
session_manager = SessionManager()
