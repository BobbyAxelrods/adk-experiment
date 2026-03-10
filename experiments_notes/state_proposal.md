# State Management Proposal — Full Codebase Plan

---

## Guiding Principles (from ADK docs)

1. **`{key?}` injection** = the right way for agents to *read* state — baked into the
   system prompt before the LLM thinks, zero tool call overhead
2. **`tool_context.state`** = the right way for tools to *write* state — ADK tracks
   all changes through the event system correctly
3. **`output_key`** = only for passing full text between pipeline agents — not for flags
4. **`temp:` prefix** = for data that should die after a single turn
5. **`EventActions.state_delta`** = for initialising state from outside the agent loop
6. **Never** mutate `session.state` directly — bypasses persistence and event tracking

---

## How State Flows in This Codebase (Current Reality)

```
main.py
  └── runner.run_async(user_id, session_id, new_message)
        │
        ├── INITIAL_STATE loaded at session creation (agents/agent.py)
        │     Sets all default values for the session
        │
        ├── root_agent instruction built
        │     ← {key} template vars substituted HERE before LLM sees it
        │     ← Currently NOT using {key} injection → LLM can't see live state
        │
        ├── LLM reasons → calls tools
        │     └── tool_context.state[key] = value   ← state mutated here
        │
        ├── after_model_callback fires (count_unrecognized_intents)
        │     └── callback_context.state[key] = value  ← state mutated here
        │
        ├── transfer_to_agent("sub_agent")
        │     ├── before_agent_callback fires (reset_unrecognized_intent)
        │     ├── sub_agent instruction built
        │     │     ← {key} template vars substituted HERE for sub_agent
        │     │     ← Sub-agents also NOT using {key} injection currently
        │     ├── sub_agent LLM reasons → calls tools → mutates state
        │     └── sub_agent transfers back to root
        │
        └── session.state persists across all turns (InMemorySessionService)
```

---

## What Needs to Change — 3 Categories

### Category A — Instruction changes (make LLM aware of live state)
### Category B — Tool/function changes (fix broken, consolidate, clean)
### Category C — INITIAL_STATE changes (correct schema)

---

## Category A — Instruction Changes

### A1. Add `shared_session_context.md` fragment (NEW FILE)

This is the most impactful change. Create one shared fragment that injects
live state into every agent's system prompt. Every agent will include it.

**New file: `agents/_fragments/shared_session_context.md`**
```markdown
## SESSION CONTEXT
- Language: {language?}
- User ID: {user_id?}
- Authenticated: {authentication?}
- Frustration count: {frustration_count?}
- Escalation recommended: {escalation_recommended?}
- Violation count: {violation_count?}
- Pending intents: {pending_intents?}
- Current intent: {current_intent?}
```

All keys use `?` (optional) so ADK renders them empty if missing — no crash.
This fragment gives EVERY agent real live values at the start of each turn.

**Why this matters:** Your `root_agent.md` Step 1 says "check if `language`,
`escalation_recommended` are set" but the LLM had no way to actually see those
values. With this fragment, the LLM sees them baked into the system prompt.

---

### A2. Update `root_agent.md`

**Replace Step 1:**
```markdown
# BEFORE (non-functional — LLM told to check but can't see values)
### Step 1 — Read state
Check if `user_name`, `language`, `escalation_recommended`, `violation_count` are set.

# AFTER (functional — values are already injected above via {{ shared_session_context }})
### Step 1 — Read session context
The SESSION CONTEXT block above shows current state values.
- If `escalation_recommended` is `True` → skip all steps, go to Step 8 immediately
- If `violation_count` >= 3 → skip all steps, go to Step 8 immediately
```

**Add `{{ shared_session_context }}` near the top:**
```markdown
# ROOT AGENT — pru_master_orchestrator

---

{{ shared_identity }}

---

{{ shared_session_context }}    ← ADD THIS

---

## SCOPE
...
```

---

### A3. Update `policy_mcp_agent.md`

**Replace the authentication gate (currently tells LLM to "check state" but values aren't injected):**

```markdown
# BEFORE
## AUTHENTICATION GATE — MUST run before any tool call
Check the session state:
- If `authentication` is **False** OR `authentication_required` is **True**:

# AFTER — values are now injected via {{ shared_session_context }}
## AUTHENTICATION GATE — MUST run before any tool call
The SESSION CONTEXT block above shows `authentication` value.
- If `authentication` is `False` or empty:
  1. Do NOT call any policy tools
  2. Tell the user they need to authenticate first
  3. Transfer to root: transfer_to_agent("pru_master_orchestrator")
Only proceed if `authentication` is `True`.
```

Also add `{{ shared_session_context }}` after `{{ shared_identity }}`.

---

### A4. Update `booking_agent.md`

Step 4 says "Call `get_user_client_id_list` using `user_id` from state".
With `{user_id?}` injected via the fragment, the LLM can see the actual `user_id`
value and pass it directly as an argument to the tool.

No structural change needed — just add `{{ shared_session_context }}` after identity.

---

### A5. Add `{{ shared_session_context }}` to ALL sub-agents

All sub-agents need to handle `escalation_recommended` and `violation_count`
correctly without relying on history. Add the fragment to:
- `rag_agent.md`
- `booking_agent.md`
- `escalation_agent.md`
- `vas_agent.md`
- `policy_mcp_agent.md`

Sub-agents don't need `pending_intents` / `current_intent` — those are root-only.
You can create a leaner `shared_session_context_sub.md` for sub-agents if needed,
or use the same one with `?` making unused keys render harmlessly empty.

---

### A6. Register `shared_session_context` in `loader.py`

The fragment system auto-picks up new `.md` files via glob — no change to
`_FILE_CACHE` needed. But you need to add `{{ shared_session_context }}` tokens
to each agent `.md` file manually (per A2–A5 above).

---

## Category B — Tool / Function Changes

### B1. Fix `update_summary` — currently a no-op

```python
# CURRENT (broken — never writes to state)
def update_summary(tool_context: ToolContext, summary: str) -> dict:
    return {"updated": True, "summary": summary}

# PROPOSED FIX
def update_summary(tool_context: ToolContext, summary: str) -> dict:
    tool_context.state["conversation_summary"] = summary
    return {"updated": True, "summary": summary}
```

Also add `"conversation_summary": ""` to `INITIAL_STATE`.

---

### B2. Fix `escalate_to_live_agent` — doesn't set `escalation_recommended`

The current `create_escalation_ticket` writes `escalated_to_human=True` and
`last_escalation_ticket` but never sets `escalation_recommended=True`.
This means the callback and sub-agents don't know to stop routing.

```python
# ADD this line inside create_escalation_ticket after writing escalated_to_human:
state["escalation_recommended"] = True
```

---

### B3. Unify `escalate_to_human` → `escalated_to_human`

`INITIAL_STATE` has `escalate_to_human: None` (verb).
`create_escalation_ticket` writes `escalated_to_human: True` (past tense).
Two different keys, same concept.

Fix: remove `escalate_to_human` from `INITIAL_STATE`, add `escalated_to_human: False`.
Update `return_to_root` function to write `escalated_to_human = False`.

---

### B4. Delete duplicate escalation file

`tools/escalation_tools/escalation_tools.py` is nearly identical to
`tools/mcp_escalation/escalation_tools.py`. Delete the older one.

Check which agents import from which path and update imports to point to
`tools.mcp_escalation.escalation_tools` only.

---

### B5. Move `set_tone_group` to be aware of state context

`set_tone_group` in `test_tone_guideline.py` writes `tone_group` and `tone_reason`
to state. This is fine as-is. No change needed — but document it in the keys registry.

---

### B6. Add `temp:` prefix to within-turn transient data

`turn_detection` is written but never read. If you keep it (for debugging),
change it to `temp:turn_detection` so it auto-expires after each turn and
doesn't pollute persistent state:

```python
# In track_frustration:
tool_context.state["temp:turn_detection"] = "frustration"
# In reset_turn_detection callback: remove the callback entirely —
# temp: keys die automatically, no manual reset needed
```

---

### B7. Guard `callback.py` — add `temp:` aware key handling

Since `temp:` keys auto-expire, the `reset_turn_detection` callback
becomes unnecessary if you adopt `temp:turn_detection`. Remove it.

---

## Category C — INITIAL_STATE Changes

```python
# agents/agent.py

INITIAL_STATE = {
    # --- User context ---
    "user_id":                  USER_ID,
    "language":                 "english",
    "authentication":           False,

    # --- Counters ---
    "frustration_count":        0,
    "violation_count":          0,          # ADD — currently missing, tool reads it fine but not initialised
    "unrecognized_intent_count": 0,

    # --- Escalation flags ---
    "escalation_recommended":   False,
    "escalated_to_human":       False,      # RENAME from escalate_to_human
    "last_escalation_ticket":   None,       # ADD
    "escalation_history":       [],         # ADD

    # --- Multi-intent queue ---
    "pending_intents":          [],
    "current_intent":           None,

    # --- Conversation ---
    "conversation_summary":     "",         # ADD (now that update_summary actually writes)

    # REMOVED:
    # "frustration_threshold": 3   — hardcoded constant in tool, not state
    # "escalate_to_human": None    — renamed to escalated_to_human
    # "authentication": False      — kept, policy_mcp_agent reads it
}
```

---

## How State Flows After These Changes

```
Turn starts
    │
    ▼
ADK builds system prompt for root_agent:
    ├── {{ shared_identity }} resolved
    ├── {{ shared_session_context }} resolved with LIVE values:
    │       Language: english
    │       Authenticated: False
    │       Escalation recommended: False
    │       Frustration count: 0
    │       Violation count: 0
    │       Pending intents: []
    │       Current intent: None
    ├── rest of root_agent.md resolved
    └── LLM now sees real state values upfront — no guessing from history
    │
    ▼
LLM Step 1: reads SESSION CONTEXT — sees real values, acts accordingly
LLM Step 4: detect_language() → writes state["language"] = "malay"
            → returns {"language": "malay", "accepted": True}
LLM Step 5: set_pending_intents(["policy_query","booking"])
            → writes state["pending_intents"] = [...]
            → writes state["current_intent"] = "policy_query"
    │
    ▼
transfer to rag_agent
    │
    ▼
ADK builds system prompt for rag_agent:
    ├── {{ shared_session_context }} resolved with UPDATED values:
    │       Language: malay          ← updated by detect_language this turn
    │       Escalation recommended: False
    │       Frustration count: 0
    └── rag_agent now sees current state without any tool calls
    │
    ▼
rag_agent runs, returns to root
    │
    ▼
root_agent: advance_intent() → pops queue, routes to booking_agent
    │
    ▼
booking_agent:
    ├── {{ shared_session_context }} shows:
    │       User ID: member_default  ← booking_agent uses this directly
    │       Authenticated: False
    └── booking_agent calls get_user_client_id_list(user_id="member_default")
```

---

## Files to Touch — Ordered by Priority

### Must do (breaks LLM reasoning without these)

| # | File | Change |
|---|---|---|
| 1 | `agents/_fragments/shared_session_context.md` | CREATE — the `{key?}` injection fragment |
| 2 | `agents/_fragments/root_agent.md` | Add `{{ shared_session_context }}`, fix Step 1 |
| 3 | `agents/_fragments/policy_mcp_agent.md` | Add `{{ shared_session_context }}`, fix auth gate |
| 4 | `agents/agent.py` | Fix `INITIAL_STATE` — add missing keys, rename escalation key |
| 5 | `tools/policy_tools/policy_tools.py` | Fix `update_summary` to actually write state |
| 6 | `tools/mcp_escalation/escalation_tools.py` | Add `escalation_recommended = True` when escalating |

### Should do (correctness + clean)

| # | File | Change |
|---|---|---|
| 7 | `agents/_fragments/rag_agent.md` | Add `{{ shared_session_context }}` |
| 8 | `agents/_fragments/booking_agent.md` | Add `{{ shared_session_context }}` |
| 9 | `agents/_fragments/escalation_agent.md` | Add `{{ shared_session_context }}` |
| 10 | `agents/_fragments/vas_agent.md` | Add `{{ shared_session_context }}` |
| 11 | `agents/_fragments/loader.py` | Register `shared_session_context` in `_AGENT_NAMES` check (auto-loaded but document it) |
| 12 | `tools/policy_tools/policy_tools.py` | Change `turn_detection` → `temp:turn_detection` |
| 13 | `agents/callback.py` | Remove `reset_turn_detection` (temp: keys auto-expire) |

### Nice to have (structural)

| # | File | Change |
|---|---|---|
| 14 | `tools/state/keys.py` | CREATE — constants registry for all key names |
| 15 | `tools/escalation_tools/escalation_tools.py` | DELETE — duplicate of mcp_escalation version |

---

## State Ownership Map — Final Target

| Key | Written By | When | Read By (via injection) |
|---|---|---|---|
| `language` | `detect_language` tool | Language detection turn | All agents via `{language?}` |
| `authentication` | `INITIAL_STATE` / external | Session start / auth flow | `policy_mcp_agent` via `{authentication?}` |
| `user_id` | `INITIAL_STATE` | Session start | `booking_agent`, `policy_mcp_agent` via `{user_id?}` |
| `frustration_count` | `track_frustration` tool | Frustration detected | All agents via `{frustration_count?}` |
| `violation_count` | `flag_violation` tool | Violation detected | All agents via `{violation_count?}` |
| `unrecognized_intent_count` | `callback.py` ONLY | After each model call | Callback only |
| `escalation_recommended` | `track_frustration`, `flag_violation`, `escalate_to_live_agent` | Threshold crossed | All agents via `{escalation_recommended?}` |
| `escalated_to_human` | `escalate_to_live_agent`, `return_to_root` | Escalation/return | All agents via `{escalated_to_human?}` |
| `pending_intents` | `set_pending_intents`, `advance_intent` | Multi-intent turn | `root_agent` via `{pending_intents?}` |
| `current_intent` | `set_pending_intents`, `advance_intent` | Multi-intent routing | `root_agent` via `{current_intent?}` |
| `conversation_summary` | `update_summary` tool | After resolved request | Optional reference |
| `last_escalation_ticket` | `escalate_to_live_agent` | Escalation created | Reference only |
| `temp:turn_detection` | `track_frustration` | Per turn | Expires automatically |
