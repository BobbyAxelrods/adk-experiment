# State Management — Audit, Problems & Consolidation Plan

---

## STATE MANIPULATION — All The Ways You Can Work With State

### 1. `{key}` Template Injection in Instructions ← BEST for reading state

ADK substitutes `{key}` in instruction strings with `session.state["key"]`
BEFORE sending to the LLM. The agent sees real values upfront, every turn.

```python
agent = Agent(
    instruction="""
    ## SESSION CONTEXT
    Language: {language?}
    Escalation recommended: {escalation_recommended?}
    Violation count: {violation_coun?}
    Pending intents: {pending_intents?}
    """
)
```

Rules:
- `{key}` — key MUST exist in state or ADK throws an error
- `{key?}` — optional key, renders empty string if missing
- Value must be string or convert cleanly to string
- Cannot use raw `{...}` for literal JSON — use InstructionProvider for that

---

### 2. `InstructionProvider` + `inject_session_state` ← for dynamic/complex instructions

Pass a function instead of a string when you need literal `{}` (JSON examples in
instructions) or runtime-computed content that varies per turn.

```python
from google.adk.agents.readonly_context import ReadonlyContext

def build_instruction(context: ReadonlyContext) -> str:
    lang = context.state.get("language", "english")
    count = context.state.get("violation_count", 0)
    # Can now safely include literal braces without ADK trying to substitute them
    return f"""
    Language: {lang}. Violations: {count}.
    Output format: {{"status": "ok", "data": "..."}}
    """

agent = Agent(instruction=build_instruction)
```

For mixed usage (some `{key}` substitution + some literal braces):
```python
from google.adk.agents import instructions_utils

async def build_instruction(context: ReadonlyContext) -> str:
    template = "Language: {language}. Use JSON like: {\"key\": \"value\"}."
    # Only {language} is substituted. {"key": "value"} left as-is.
    return await instructions_utils.inject_session_state(template, context)
```

Notes:
- Reliability: agent always has real state values, not guessing from history
- Maintainability: explicit which parts are dynamic vs static
- Clarity: separates prompt structure from runtime data

---

### 3. `output_key` on Agent ← simplest write, no tool needed

Saves agent's final text response directly to a state key automatically.

```python
agent = Agent(output_key="last_agent_response")
# After agent responds: session.state["last_agent_response"] = "<full response text>"
```

Use case: pipeline agents where one agent's output is the next agent's input context.
Limitation: saves full text response only — not for structured flag values.

---

### 4. `ToolContext.state` in Tool Functions ← WHAT WE USE NOW

The recommended way to read/write state inside tools.
ADK tracks all changes correctly and persists them.

```python
def track_frustration(tool_context: ToolContext) -> dict:
    count = tool_context.state.get("frustration_count", 0) + 1  # READ
    tool_context.state["frustration_count"] = count              # WRITE (session scope)
    tool_context.state["temp:last_signal"] = "frustration"       # WRITE (temp scope)
    return {"frustration_count": count, "escalation_recommended": count >= 3}
```

**State scope prefixes:**

| Prefix | Scope | Lifetime | Use Case |
|---|---|---|---|
| *(none)* | Session | Current session | frustration_count, language, pending_intents |
| `user:` | User | All sessions for this user | user preferences, display name |
| `app:` | App-wide | All users, all sessions | global config, shared templates |
| `temp:` | Invocation | Current turn only | inter-tool intermediate data |

---

### 5. `CallbackContext.state` in Callbacks ← passive observers

Same API as ToolContext. For counters and guards that fire on lifecycle events.

```python
def count_unrecognized_intents(callback_context: CallbackContext, llm_response):
    state = callback_context.state
    state["unrecognized_intent_count"] = state.get("unrecognized_intent_count", 0) + 1
```

---

### 6. `EventActions.state_delta` ← programmatic bulk write from outside agent loop

For initialising or updating state from application code (webhooks, startup):

```python
from google.adk.events import Event, EventActions

actions = EventActions(state_delta={
    "language": "malay",
    "user:preferred_name": "Ahmad",
    "authentication": True,
})
await session_service.append_event(session, Event(actions=actions))
```

---

### 7. ❌ NEVER — direct session object mutation

```python
# WRONG — bypasses event tracking, won't persist with DatabaseSessionService,
# causes race conditions, loses auditability
session = await session_service.get_session(...)
session.state["key"] = value
```

Always use ToolContext, CallbackContext, or EventActions.state_delta.

---

## Revised Approach for This Codebase

### What to add: SESSION CONTEXT block in `root_agent.md`

Replace the current "Step 1 — Read state" (which the LLM can't actually execute)
with `{key}` template injection so the LLM always sees real values:

```markdown
## SESSION CONTEXT
- Language: {language}
- Escalation recommended: {escalation_recommended}
- Violation count: {violation_count}
- Frustration count: {frustration_count}
- Authenticated: {authentication}
- Pending intents: {pending_intents?}
- Current intent: {current_intent?}
```

This replaces the old "Step 1 — Check if keys are set" which was never functional.
All keys used here must exist in `INITIAL_STATE` (with defaults) or use `?`.

### What to use InstructionProvider for

If any agent instruction needs to include JSON format examples (e.g. corpus response
format, booking confirmation format), those instructions should use `InstructionProvider`
to avoid ADK misinterpreting the `{` as a template variable.

Currently none of your instructions have this problem — all `{...}` references
are legitimate state keys. Use plain `{key}` for now.


## Current State of State (The Mess)

State is touched in **4 different places** with no single source of truth:

```
agents/agent.py              ← defines INITIAL_STATE (the schema)
agents/callback.py           ← mutates state in callbacks (passive observers)
tools/policy_tools/          ← mutates state directly in tool functions
tools/escalation_tools/      ← mutates state directly in tool functions
tools/mcp_escalation/        ← mutates state directly in tool functions (duplicate)
tools/tone_management/       ← mutates state directly in set_tone_group
```

No type enforcement. No canonical key registry. Keys are string literals scattered
across 6 files. If you rename one key, you have to grep for it manually.

---

## Full State Key Inventory

Every key that exists in `session.state`, where it's written, and where it's read:

| Key | Written By | Read By | Type | Problem |
|---|---|---|---|---|
| `frustration_count` | `track_frustration` | `track_frustration`, `return_to_root` | int | ✓ clean |
| `frustration_threshold` | `INITIAL_STATE` | nowhere (unused in code) | int | dead key |
| `escalation_recommended` | `track_frustration`, `flag_violation`, `create_escalation_ticket` | `callback.py`, `record_unrecognized_intent`, `return_to_root` | bool | written from 3 different files |
| `escalate_to_human` | `INITIAL_STATE`, `return_to_root` | nowhere read in code | None/bool | orphan — different from `escalated_to_human` |
| `escalated_to_human` | `create_escalation_ticket` (both escalation files) | nowhere | bool | duplicate key, different spelling |
| `violation_count` | `flag_violation` | `callback.py`, `record_unrecognized_intent` | int | ✓ mostly clean |
| `unrecognized_intent_count` | `callback.py` | `callback.py`, `record_unrecognized_intent` | int | ✓ clean (callback owns it) |
| `turn_detection` | `track_frustration`, `callback.py (reset_turn_detection)` | nowhere read | str | written twice, never read |
| `language` | `detect_language` | `return_to_root`, `detect_language` | str | ✓ clean |
| `user_id` | `INITIAL_STATE` | nowhere in tools | str | only in initial state |
| `authentication` | `INITIAL_STATE` | nowhere in tools | bool | dead key |
| `pending_intents` | `set_pending_intents`, `advance_intent` | `advance_intent` | list | ✓ new, clean |
| `current_intent` | `set_pending_intents`, `advance_intent` | nothing yet | str/None | ✓ new, clean |
| `tone_group` | `set_tone_group` | `set_tone_group` (reads previous) | str | lives in tone tool, isolated |
| `tone_reason` | `set_tone_group` | nowhere | str | orphan |
| `last_escalation_ticket` | `create_escalation_ticket` (both escalation files) | nowhere | str | written twice (duplicate files) |
| `escalation_history` | `_append_escalation_history` (both escalation files) | nowhere | list | written twice (duplicate files) |
| `callback_request` | `request_callback` (both escalation files) | nowhere | dict | written twice (duplicate files) |

---

## Problems Identified

### Problem 1 — Duplicate escalation files writing the same state keys
`tools/escalation_tools/escalation_tools.py` and `tools/mcp_escalation/escalation_tools.py`
are near-identical. Both write `last_escalation_ticket`, `escalated_to_human`,
`escalation_history`, `callback_request`. The code is duplicated with no diff in logic.

### Problem 2 — `escalate_to_human` vs `escalated_to_human` (key name collision)
- `INITIAL_STATE` defines `escalate_to_human: None` (verb, imperative)
- `create_escalation_ticket` writes `escalated_to_human: True` (past tense)
These are two different keys representing the same concept. Neither is reliably read.

### Problem 3 — Dead keys in INITIAL_STATE
`frustration_threshold` and `authentication` are defined in `INITIAL_STATE` but
never read by any tool or callback. They're noise.

### Problem 4 — `turn_detection` written in two places, read nowhere
`track_frustration` writes `turn_detection = "frustration"`.
`reset_turn_detection` callback clears it to `""`.
Nothing reads it to make a decision. It's a debugging artifact.

### Problem 5 — `escalation_recommended` written from 3 files
`track_frustration` → writes it
`flag_violation` → writes it
`create_escalation_ticket` → does NOT write it (should, but doesn't)
The callback reads it. No single owner.

### Problem 6 — `update_summary` doesn't touch state at all
It's registered as a tool and in the agent tools list but just returns a dict.
The LLM thinks it's saving state. It's a no-op.

### Problem 7 — No state key registry
Keys are string literals (`"frustration_count"`, `"language"`, etc.) scattered
across 6 files. A typo silently creates a new key instead of raising an error.

---

## Proposed Solution: Centralized State Manager

### Target structure

```
tools/
└── state/
    ├── __init__.py
    ├── keys.py          ← single registry of all state key constants
    ├── state_tools.py   ← all state-mutating functions + FunctionTool registrations
    └── README.md
```

Everything that touches `tool_context.state` moves here.
All other tools import from `tools.state.state_tools` — they never touch state directly.

---

## Step 1 — `tools/state/keys.py` — The Key Registry

```python
# tools/state/keys.py
# Single source of truth for all session.state key names.
# Import these constants everywhere — never use raw string literals.

# --- Counters ---
FRUSTRATION_COUNT        = "frustration_count"
VIOLATION_COUNT          = "violation_count"
UNRECOGNIZED_INTENT_COUNT = "unrecognized_intent_count"

# --- Flags ---
ESCALATION_RECOMMENDED   = "escalation_recommended"
ESCALATED_TO_HUMAN       = "escalated_to_human"   # replaces both escalate_to_human variants
AUTHENTICATION           = "authentication"

# --- User context ---
USER_ID                  = "user_id"
LANGUAGE                 = "language"

# --- Escalation records ---
LAST_ESCALATION_TICKET   = "last_escalation_ticket"
ESCALATION_HISTORY       = "escalation_history"
CALLBACK_REQUEST         = "callback_request"

# --- Tone ---
TONE_GROUP               = "tone_group"
TONE_REASON              = "tone_reason"

# --- Multi-intent queue ---
PENDING_INTENTS          = "pending_intents"
CURRENT_INTENT           = "current_intent"

# --- Internal / debugging ---
TURN_DETECTION           = "turn_detection"   # kept but only written by callback
```

---

## Step 2 — `tools/state/state_tools.py` — Centralized State Functions

Move ALL state-mutating functions here. Group by domain:

```python
# tools/state/state_tools.py
from google.adk.tools import ToolContext, FunctionTool
from .keys import *

# ── FRUSTRATION ──────────────────────────────────────────────────────────────

def track_frustration(tool_context: ToolContext) -> dict:
    # reads/writes: FRUSTRATION_COUNT, ESCALATION_RECOMMENDED, TURN_DETECTION
    ...

# ── VIOLATION ────────────────────────────────────────────────────────────────

def flag_violation(tool_context: ToolContext, observed_intent: str) -> dict:
    # reads/writes: VIOLATION_COUNT, ESCALATION_RECOMMENDED
    ...

def record_unrecognized_intent(tool_context: ToolContext) -> dict:
    # reads: UNRECOGNIZED_INTENT_COUNT, VIOLATION_COUNT, ESCALATION_RECOMMENDED
    # write: owned by callback, not this fn
    ...

# ── LANGUAGE ─────────────────────────────────────────────────────────────────

def detect_language(tool_context: ToolContext, language: str) -> dict:
    # reads/writes: LANGUAGE
    ...

# ── ESCALATION ───────────────────────────────────────────────────────────────

def escalate_to_live_agent(tool_context: ToolContext, reason: str, context: str) -> dict:
    # writes: LAST_ESCALATION_TICKET, ESCALATED_TO_HUMAN, ESCALATION_HISTORY,
    #         ESCALATION_RECOMMENDED
    ...

def request_callback(tool_context: ToolContext, phone_number: str, preferred_time: str) -> dict:
    # writes: CALLBACK_REQUEST
    ...

def return_to_bot(tool_context: ToolContext) -> dict:
    # writes: ESCALATED_TO_HUMAN=False, ESCALATION_RECOMMENDED=False
    # replaces: return_to_root (rename for clarity)
    ...

# ── TONE ─────────────────────────────────────────────────────────────────────

def set_tone_group(tool_context: ToolContext, tone_group: str, reason: str) -> dict:
    # writes: TONE_GROUP, TONE_REASON
    ...

# ── MULTI-INTENT QUEUE ───────────────────────────────────────────────────────

def set_pending_intents(tool_context: ToolContext, intents: list) -> dict:
    # writes: PENDING_INTENTS, CURRENT_INTENT
    ...

def advance_intent(tool_context: ToolContext) -> dict:
    # reads/writes: PENDING_INTENTS, CURRENT_INTENT
    ...

# ── FunctionTool registrations ───────────────────────────────────────────────
track_frustration         = FunctionTool(func=track_frustration)
flag_violation            = FunctionTool(func=flag_violation)
record_unrecognized_intent = FunctionTool(func=record_unrecognized_intent)
detect_language           = FunctionTool(func=detect_language)
escalate_to_live_agent    = FunctionTool(func=escalate_to_live_agent)
request_callback          = FunctionTool(func=request_callback)
return_to_bot             = FunctionTool(func=return_to_bot)
set_tone_group            = FunctionTool(func=set_tone_group)
set_pending_intents       = FunctionTool(func=set_pending_intents)
advance_intent            = FunctionTool(func=advance_intent)
```

---

## Step 3 — Clean `INITIAL_STATE` in `agents/agent.py`

Remove dead keys. Unify the escalation key. Add all new keys.

```python
# Before (current)                    # After (clean)
INITIAL_STATE = {                      INITIAL_STATE = {
  "frustration_count": 0,               "frustration_count": 0,
  "frustration_threshold": 3,           # removed — hardcoded in tool constant
  "unrecognized_intent_count": 0,       "unrecognized_intent_count": 0,
  "escalate_to_human": None,            "escalated_to_human": False,   # unified key
  "escalation_recommended": False,      "escalation_recommended": False,
  "user_id": USER_ID,                   "user_id": USER_ID,
  "language": "english",               "language": "english",
  "authentication": False,              "authentication": False,
  "pending_intents": [],                "pending_intents": [],
  "current_intent": None,              "current_intent": None,
}                                       # new keys with defaults
                                        "violation_count": 0,
                                        "last_escalation_ticket": None,
                                        "escalation_history": [],
                                        "tone_group": "system_general",
                                      }
```

---

## Step 4 — Fix `update_summary` (currently broken)

`update_summary` currently does nothing with state. Two options:

**Option A — Make it write to state (fix it)**
```python
def update_summary(tool_context: ToolContext, summary: str) -> dict:
    tool_context.state["conversation_summary"] = summary
    return {"updated": True, "summary": summary}
```

**Option B — Remove it** if no agent instruction actually depends on the summary being
persisted. Check all `.md` fragment files before deciding.

---

## Step 5 — Consolidate duplicate escalation files

Delete `tools/escalation_tools/escalation_tools.py` (the older one).
Keep logic only in `tools/mcp_escalation/escalation_tools.py` — or better, move it
entirely into `tools/state/state_tools.py` since it's fundamentally a state operation.

Agents currently importing from `tools.escalation_tools` need import path updates.

---

## State Ownership Map (After Consolidation)

Clear single owner per key — no more shared writes:

| Key | Owner (writes) | Readers |
|---|---|---|
| `frustration_count` | `track_frustration` | `return_to_bot` |
| `violation_count` | `flag_violation` | `callback.py`, `record_unrecognized_intent` |
| `unrecognized_intent_count` | `callback.py` ONLY | `record_unrecognized_intent` |
| `escalation_recommended` | `track_frustration`, `flag_violation`, `escalate_to_live_agent` | `callback.py`, `return_to_bot` |
| `escalated_to_human` | `escalate_to_live_agent`, `return_to_bot` | agent instructions |
| `language` | `detect_language` | `return_to_bot` |
| `tone_group` | `set_tone_group` | `set_tone_group` |
| `pending_intents` | `set_pending_intents`, `advance_intent` | `advance_intent` |
| `current_intent` | `set_pending_intents`, `advance_intent` | root agent instruction |
| `last_escalation_ticket` | `escalate_to_live_agent` | — |
| `escalation_history` | `escalate_to_live_agent` | — |
| `callback_request` | `request_callback` | — |

---

## Migration Checklist (Sandbox)

### Phase 1 — No behaviour change, just structure
- [ ] Create `tools/state/keys.py` with all key constants
- [ ] Create `tools/state/__init__.py`
- [ ] Create `tools/state/state_tools.py` — copy existing fn bodies, replace string literals with constants
- [ ] Update `agents/agent.py` imports to use `tools.state.state_tools`
- [ ] Update `agents/callback.py` to import from `tools.state.keys` for key names

### Phase 2 — Clean dead/broken things
- [ ] Remove `frustration_threshold` from `INITIAL_STATE`
- [ ] Unify `escalate_to_human` → `escalated_to_human` everywhere
- [ ] Add missing keys to `INITIAL_STATE`: `violation_count`, `last_escalation_ticket`, `escalation_history`, `tone_group`
- [ ] Fix or remove `update_summary` (decide Option A or B)
- [ ] Delete `tools/escalation_tools/escalation_tools.py` (duplicate)
- [ ] Update agents importing from the old escalation path

### Phase 3 — Tighten `turn_detection`
- [ ] Decide: keep as debug signal or remove
- [ ] If keep: make `callback.py` the sole writer (remove from `track_frustration`)
- [ ] If remove: delete from `track_frustration` and `reset_turn_detection`

---

## What This Gives You

| Before | After |
|---|---|
| State keys as raw string literals in 6 files | All keys in one `keys.py` — typo = `AttributeError` |
| State written from tools + callbacks with no rules | Clear owner-per-key rule |
| Duplicate escalation files writing same keys | One file, one path |
| Dead keys in INITIAL_STATE | Only live keys with correct defaults |
| `update_summary` silently doing nothing | Fixed or removed |
| Import from 3 different tool paths | One import: `from tools.state.state_tools import ...` |
