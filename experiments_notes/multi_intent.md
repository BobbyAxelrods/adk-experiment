# Multi-Intent Handling Plan

---

## Problem

When a user sends a single message with **2+ distinct intents**, e.g.:
> "What does my policy cover AND book me an appointment with a cardiologist?"

The root agent currently routes to **one** agent and drops the rest.

---

## Chosen Pattern: AutoFlow + session.state intent queue

Keep the existing `LlmAgent + sub_agents` (AutoFlow) architecture.
No `SequentialAgent` or `ParallelAgent` needed — those are for fixed pipelines.
Teach the root agent to queue intents in `session.state` and process them one by one.

---

## State Keys to Add to INITIAL_STATE

```python
INITIAL_STATE = {
    # ... existing keys ...
    "pending_intents": [],   # ordered list of intents still to handle
    "current_intent": None,  # intent being handled right now
}
```

---

## Functions to Add (`tools/policy_tools/policy_tools.py`)

### 1. `set_pending_intents`

```python
def set_pending_intents(tool_context: ToolContext, intents: list) -> dict:
    """
    Store multiple pending intents in session state for multi-intent handling.

    Call this at the START of a turn when the user message contains more than
    one distinct intent (e.g. policy question + booking request).

    intents: ordered list of intent labels to process.
             Valid labels: "policy_query", "booking", "escalation", "greeting"
             Order by urgency: safety > policy > booking > greeting

    Example: set_pending_intents(intents=["policy_query", "booking"])

    The first item becomes current_intent immediately.
    The rest stay queued in pending_intents.
    After each sub-agent returns, call advance_intent() to pop the next one.
    """
    tool_context.state["pending_intents"] = intents
    tool_context.state["current_intent"] = intents[0] if intents else None
    return {
        "status": "saved",
        "current_intent": tool_context.state["current_intent"],
        "pending_intents": intents,
    }
```

**Why:** Directly mutates `tool_context.state` — same pattern as `track_frustration`.
`update_summary` was considered but it doesn't write to state at all (just returns a dict), so it can't be used here.

---

### 2. `advance_intent`

```python
def advance_intent(tool_context: ToolContext) -> dict:
    """
    Pop the first item from pending_intents and set it as current_intent.

    Call this after a sub-agent returns control to the root agent and there
    are still pending intents left to handle.

    Returns the next intent to process, or None if the queue is empty.
    When done=True, give the user a consolidated closing response.
    """
    pending = tool_context.state.get("pending_intents", [])
    if pending:
        pending.pop(0)
    next_intent = pending[0] if pending else None
    tool_context.state["pending_intents"] = pending
    tool_context.state["current_intent"] = next_intent
    return {
        "next_intent": next_intent,
        "remaining": len(pending),
        "done": next_intent is None,
    }
```

**Why:** Called after each sub-agent completes. Moves the queue forward.
When `done=True` the root agent knows all intents are resolved and can give a final response.

---

## Register as FunctionTool (bottom of policy_tools.py)

```python
set_pending_intents = FunctionTool(func=set_pending_intents)
advance_intent = FunctionTool(func=advance_intent)
```

---

## Wire into root_agent (`agents/agent.py`)

### Import

```python
from tools.policy_tools.policy_tools import (
    update_summary, track_frustration, detect_language,
    flag_violation, record_unrecognized_intent,
    set_pending_intents, advance_intent          # NEW
)
```

### Add to root_agent tools list

```python
root_agent = Agent(
    ...
    tools=[
        track_frustration,
        detect_language,
        flag_violation,
        update_summary,
        response_tone_guideline,
        record_unrecognized_intent,
        escalate_to_live_agent,
        set_pending_intents,    # NEW
        advance_intent,         # NEW
    ],
)
```

---

## Callback guard (`agents/callback.py`)

Add both new tools to `disallowed_reset_tools` inside `count_unrecognized_intents`:

```python
disallowed_reset_tools = {
    "record_unrecognized_intent",
    "response_tone_guideline",
    "response_tone_guideline_tool",
    "detect_language",
    "flag_violation",
    "set_pending_intents",   # NEW — routing helper, not a success signal
    "advance_intent",        # NEW — routing helper, not a success signal
}
```

**Why:** Without this, calling either tool would look like a "success tool" to the
`count_unrecognized_intents` callback and incorrectly reset `unrecognized_intent_count` to 0.

---

## root_agent.md instruction changes (`agents/_fragments/root_agent.md`)

Replace Step 5 and Step 6. Add Step 7.

```markdown
### Step 5 — Detect multi-intent
Count the number of distinct actionable intents in the user message.

**Single intent** → skip to Step 6 directly.

**Multiple intents** → call `set_pending_intents(intents=[...])` with the full
ordered list BEFORE routing anything.
- Valid labels: "policy_query", "booking", "escalation", "greeting"
- Order by urgency: safety > policy > booking > greeting
- Example: set_pending_intents(intents=["policy_query", "booking"])

### Step 6 — Route or respond
Check `current_intent` in state (set by set_pending_intents, or None for single-intent).

| current_intent       | Action                                                              |
|----------------------|---------------------------------------------------------------------|
| "policy_query"       | transfer to rag_agent                                               |
| "booking"            | transfer to booking_agent                                           |
| "escalation"         | call escalate_to_live_agent(reason, context) → transfer to escalation_agent |
| "greeting"           | call response_tone_guideline("foundation", "greeting")              |
| None (single intent) | apply same routing rules as above based on message content          |
| out-of-scope         | call record_unrecognized_intent() → standard redirect. Stop.        |

### Step 7 — After sub-agent returns, check remaining intents
When a sub-agent returns control back to you:
1. Call advance_intent()
2. Check the result:
   - done=False → route to next agent using next_intent (same table as Step 6)
   - done=True  → all intents resolved, give a consolidated closing response

### Step 8 — Check escalation flag
After any tool call, if escalation_recommended=True in state → transfer to escalation_agent.
```

---

## Full Execution Flow

```
User: "What does my policy cover AND book me with a cardiologist?"
    │
    ▼
[before_agent_callback]   ← fires on root_agent entry (reset_unrecognized_intent not on root)
    │
    ▼
[before_model_callback]   ← fires before LLM thinks (reset_turn_detection clears turn_detection)
    │
    ▼
LLM detects 2 intents
    │── set_pending_intents(["policy_query", "booking"])   ← tool writes state directly
    │   state: pending=["policy_query","booking"], current="policy_query"
    │
    ▼
transfer to rag_agent → answers policy question → returns to root
    │
    ▼
LLM: advance_intent()   ← tool writes state directly
    │   state: pending=["booking"], current="booking", done=False
    │
    ▼
transfer to booking_agent → books appointment → returns to root
    │
    ▼
LLM: advance_intent()   ← tool writes state directly
    │   state: pending=[], current=None, done=True
    │
    ▼
[after_model_callback]    ← fires after LLM generates final response
    │   count_unrecognized_intents sees set_pending_intents/advance_intent
    │   in disallowed_reset_tools → does NOT reset unrecognized_intent_count
    │
    ▼
root_agent: consolidated response to user
```

---

## Do We Need a New Callback for Multi-Intent?

**Short answer: No.** The tools write state directly — no callback needed to trigger or observe them.

### Why each callback type is NOT needed

| Callback | On | Needed? | Reason |
|---|---|---|---|
| `before_agent_callback` | root | No | Queue is set by tool call mid-turn, not on agent entry |
| `before_model_callback` | root | No | LLM reads `pending_intents` naturally from state via instruction |
| `after_model_callback` | root | No | Already guarded — both tools added to `disallowed_reset_tools` |
| `after_agent_callback` | root | **Optional safety net** | Clears stale `pending_intents` if LLM forgets to call `advance_intent` |
| Any callback | sub-agents | No | Sub-agents never read or write the intent queue |

### The optional safety net (`after_agent_callback` on root only)

```python
def clear_intent_queue_on_completion(callback_context: CallbackContext) -> None:
    """
    after_agent_callback on root_agent only.
    Safety net: if pending_intents is non-empty when root_agent finishes a turn,
    the LLM dropped the queue mid-flow. Reset it so the next turn starts clean.
    """
    state = callback_context.state
    if state.get("pending_intents"):
        state["pending_intents"] = []
        state["current_intent"] = None
```

**When to add it:** Only if sandbox testing shows the LLM occasionally skips `advance_intent`
and leaves stale state into the next turn. Don't add it preemptively.

---

## Files to Touch (Sandbox Checklist)

- [ ] `tools/policy_tools/policy_tools.py` — add `set_pending_intents`, `advance_intent` functions + FunctionTool registrations
- [ ] `agents/agent.py` — import new tools, add to `root_agent` tools list, add keys to `INITIAL_STATE`
- [ ] `agents/callback.py` — add both tools to `disallowed_reset_tools`
- [ ] `agents/_fragments/root_agent.md` — update Step 5/6, add Step 7, update TOOLS table
- [ ] `agents/callback.py` *(optional)* — add `clear_intent_queue_on_completion` as `after_agent_callback` on root if stale state observed in testing
