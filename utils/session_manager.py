import time
import uuid
from typing import Dict, Optional
from pydantic import BaseModel, Field

class SessionState(BaseModel):
    frustration_count: int = 0
    frustration_threshold: int = 3
    escalate_to_human: Optional[str] = None
    escalation_recommended: bool = False
    language: str = "english"
    authentication: bool = False
    user_id: Optional[str] = None
    # User Metadata (from users.json or other sources)

    class Config:
        extra = "ignore"  # Ensure only defined fields are kept when updating from dict

class SessionManager:
    def __init__(self, ttl_seconds: int = 7200):
        # Store as {from_number: {"session_id": str, "expires_at": float, ...state}}
        self._sessions: Dict[str, Dict] = {}
        self.ttl = ttl_seconds

    def get_or_create_session(self, from_number: str) -> Dict:
        current_time = time.time()
        
        # Check if session exists and is not expired
        if from_number in self._sessions:
            session = self._sessions[from_number]
            if session["expires_at"] > current_time:
                # Refresh expiration
                session["expires_at"] = current_time + self.ttl
                return session
        
        # Create new session
        new_id = str(uuid.uuid4())
        # Initialize with Pydantic model defaults
        state = SessionState(user_id=from_number)
        new_session = state.model_dump()
        new_session["session_id"] = new_id
        new_session["expires_at"] = current_time + self.ttl

        self._sessions[from_number] = new_session
        return new_session

    def update_session(self, from_number: str, updates: Dict):
        """Update session state with a dictionary of changes, enforcing schema via Pydantic."""
        if from_number in self._sessions:
            current_session = self._sessions[from_number]
            
            # Create a model instance from current state + updates to validate and filter
            merged_data = {**current_session, **updates}
            try:
                state = SessionState(**merged_data)
                # Dump new state back into storage, preserving session_id and expires_at
                new_state_dict = state.model_dump()
                current_session.update(new_state_dict)
            except Exception as e:
                print(f"Error updating session state: {e}")

    def delete_session(self, from_number: str):
        if from_number in self._sessions:
            del self._sessions[from_number]

# Global instance
session_manager = SessionManager()
