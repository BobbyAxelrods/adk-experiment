# tools/state/keys.py
# Single source of truth for ALL session.state key names.
# Import these constants everywhere — never use raw string literals.
# A typo here = AttributeError immediately, not a silent new key.

# --- User context ---
USER_ID                   = "user_id"
LANGUAGE                  = "language"
AUTHENTICATION            = "authentication"

# --- Counters ---
FRUSTRATION_COUNT         = "frustration_count"
VIOLATION_COUNT           = "violation_count"
UNRECOGNIZED_INTENT_COUNT = "unrecognized_intent_count"

# --- Escalation flags ---
ESCALATION_RECOMMENDED    = "escalation_recommended"
ESCALATED_TO_HUMAN        = "escalated_to_human"
LAST_ESCALATION_TICKET    = "last_escalation_ticket"
ESCALATION_HISTORY        = "escalation_history"
ESCALATION_TIME           = "escalation_time"

# --- Callback / support ---
CALLBACK_REQUEST          = "callback_request"

# --- Tone ---
TONE_GROUP                = "tone_group"
TONE_REASON               = "tone_reason"

# --- Multi-intent queue ---
PENDING_INTENTS           = "pending_intents"
CURRENT_INTENT            = "current_intent"

# --- Conversation ---
CONVERSATION_SUMMARY      = "conversation_summary"

# --- Temp (auto-expires after each turn via ADK temp: prefix) ---
TEMP_TURN_SIGNAL          = "temp:turn_signal"
