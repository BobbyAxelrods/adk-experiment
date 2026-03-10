# Codebase Changelog — State Management Refactor

---

## Summary

Centralised state management, fixed broken tools, removed dead code, and wired
`{key?}` session context injection into all agent instructions so the LLM sees
live state values at the start of every turn.

---

## Files Changed

### NEW — `agents/_fragments/shared_session_context.md`

**What:** New shared fragment that injects live session state into every agent's
system prompt via ADK `{key?}` template substitution.

**Why:** Previously, agents were told to "check state" but had no mechanism to
actually see live values. The LLM was guessing from conversation history.
Now every agent sees real values baked into the system prompt before reasoning starts.

**Content injected every turn:**
```
Language, User ID, Authenticated, Frustration count,
Escalation recommended, Violation count, Pending intents, Current intent
```

All keys use `?` (optional) — renders empty string if missing, never crashes.

---

### CHANGED — `agents/_fragments/root_agent.md`

- Added `{{ shared_session_context }}` after identity block
- **Replaced Step 1** — was "Check if keys are set" (non-functional, LLM couldn't see values).
  Now reads: "SESSION CONTEXT above shows live values — if escalation_recommended=True skip to Step 8"
- Updated Step 6 routing table to reference SESSION CONTEXT
- Updated Step 7 to match multi-intent queue flow
- Updated TOOLS table — added `return_to_bot`, `update_summary`; fixed descriptions
- `return_to_root` → renamed to `return_to_bot` in tools table (matches function rename)

---

### CHANGED — `agents/_fragments/rag_agent.md`

- Added `{{ shared_session_context }}` after identity block
- Added Step 1 — "Read session context, check escalation_recommended"
- Renumbered subsequent steps accordingly

---

### CHANGED — `agents/_fragments/booking_agent.md`

- Added `{{ shared_session_context }}` after identity block
- Added Step 1 — "Read session context, check escalation_recommended"
- Updated Step 5 (was Step 4) — now references "user_id from SESSION CONTEXT" explicitly
  so LLM can see the actual value and pass it to tools directly
- Renumbered subsequent steps accordingly

---

### CHANGED — `agents/_fragments/escalation_agent.md`

- Added `{{ shared_session_context }}` after identity block
- Added Step 1 — "Read session context, note frustration_count and escalated_to_human
  so you do not ask user to repeat"
- Added explicit check: "If escalation_recommended=True in SESSION CONTEXT → Step 6"
- Renumbered subsequent steps accordingly

---

### CHANGED — `agents/_fragments/vas_agent.md`

- Added `{{ shared_session_context }}` after identity block
- Added Step 1 — "Read session context, check escalation_recommended"
- Renumbered subsequent steps accordingly

---

### CHANGED — `agents/_fragments/policy_mcp_agent.md`

- Added `{{ shared_session_context }}` after identity block
- **Replaced authentication gate** — was "Check session state" (LLM couldn't see the value).
  Now reads: "Check `authentication` in SESSION CONTEXT above — if False, block and transfer"
- Updated Step 2 — now reads "Use user_id from SESSION CONTEXT" (value is visible via injection)
- Removed vague "check state" language throughout

---

### CHANGED — `tools/policy_tools/policy_tools.py`

**Removed:**
- `return_to_root` → renamed to `return_to_bot`
  - Also fixed: now writes `escalated_to_human = False` (not `escalate_to_human = None`)
  - Unifies the two colliding key names (`escalate_to_human` vs `escalated_to_human`)

**Removed:**
- `update_summary` — fully deleted. Was a no-op (returned dict, never wrote to state).
  Redundant: `output_key="root_agent_output"` on `root_agent` already saves the full
  response to state automatically after every turn. No tool needed.

**Changed:**
- `track_frustration` — changed `turn_detection` → `temp:turn_detection`
  so it auto-expires after each turn. No manual reset callback needed.

**Removed FunctionTool:**
- `return_to_root` FunctionTool removed — replaced by `return_to_bot`

**Added FunctionTool:**
- `return_to_bot` registered at bottom

**No logic changes to:** `flag_violation`, `record_unrecognized_intent`,
`report_violation_to_root`, `detect_language`, `set_pending_intents`, `advance_intent`

---

### CHANGED — `tools/mcp_escalation/escalation_tools.py`

**Fixed:**
- `_escalate_to_live_agent` (the function behind `escalate_to_live_agent` tool) —
  now writes `state["escalation_recommended"] = True` when escalating.
  Previously it wrote `escalated_to_human` and `last_escalation_ticket` but
  forgot to set `escalation_recommended`, so callbacks and sub-agents
  didn't know to stop routing.

**Removed:**
- `escalate_to_live_agent = create_escalation_ticket` alias at module level —
  cleaned up, function is now just `_escalate_to_live_agent` internally

**No changes to:** `check_agent_availability`, `request_callback`, `leave_message`

---

### CHANGED — `agents/agent.py`

**INITIAL_STATE — removed dead keys:**
- `frustration_threshold: 3` — was hardcoded constant, never read from state

**INITIAL_STATE — renamed:**
- `escalate_to_human: None` → `escalated_to_human: False`
  Unifies the two colliding key spellings across the codebase

**INITIAL_STATE — added missing keys:**
- `violation_count: 0` — tools wrote to this key but it was never initialised
- `last_escalation_ticket: None` — written by escalate_to_live_agent, now initialised
- `escalation_history: []` — written by escalate_to_live_agent, now initialised

**INITIAL_STATE — removed:**
- `conversation_summary` — not needed; `output_key="root_agent_output"` on root_agent
  automatically saves the full response to state after every turn

**Imports — added:**
- `return_to_bot` (replaces `return_to_root`)

**Imports — removed:**
- `update_summary` — deleted function

**root_agent tools list — added:**
- `return_to_bot`

---

### CHANGED — `agents/callback.py`

**Removed:**
- `reset_turn_detection` function entirely — was resetting `turn_detection` key
  which no longer exists (replaced by `temp:turn_detection` in `track_frustration`).
  `temp:` prefix keys auto-expire after each turn — no manual reset needed.

**No changes to:** `count_unrecognized_intents`, `reset_unrecognized_intent`

---

### DELETED — `tools/escalation_tools/escalation_tools.py`

Near-identical duplicate of `tools/mcp_escalation/escalation_tools.py`.
Was writing the same state keys (`last_escalation_ticket`, `escalated_to_human`,
`escalation_history`, `callback_request`) from two separate files.

All agents that previously imported from `tools.escalation_tools` should now
import from `tools.mcp_escalation.escalation_tools`.

---

## State Key Changes Summary

| Key | Before | After |
|---|---|---|
| `escalate_to_human` | In INITIAL_STATE as `None`, never reliably read | **Removed** |
| `escalated_to_human` | Written by escalation tool only, never initialised | **In INITIAL_STATE** as `False`, unified key |
| `frustration_threshold` | In INITIAL_STATE, never read from state | **Removed** (hardcoded constant in tool) |
| `violation_count` | Written by tool, never in INITIAL_STATE | **Added to INITIAL_STATE** as `0` |
| `last_escalation_ticket` | Written by tool, never in INITIAL_STATE | **Added to INITIAL_STATE** as `None` |
| `escalation_history` | Written by tool, never in INITIAL_STATE | **Added to INITIAL_STATE** as `[]` |
| `conversation_summary` | Not tracked (update_summary was no-op) | **Removed** — `output_key="root_agent_output"` saves response automatically, no state key needed |
| `turn_detection` | Written to session state, never read, never expired | **Replaced** with `temp:turn_detection` (auto-expires) |
| `escalation_recommended` | Written by 2 tools, not by escalate_to_live_agent | **Now written by all 3**: track_frustration, flag_violation, escalate_to_live_agent |

---

## What the LLM Can Now See (vs Before)

| State value | Before | After |
|---|---|---|
| `language` | Only if detect_language was called this turn | **Always** — injected via `{language?}` |
| `authentication` | Never visible (policy_mcp_agent had to guess) | **Always** — injected via `{authentication?}` |
| `escalation_recommended` | Only if a tool returned it this turn | **Always** — injected via `{escalation_recommended?}` |
| `frustration_count` | Only if track_frustration was called this turn | **Always** — injected via `{frustration_count?}` |
| `violation_count` | Only if flag_violation was called this turn | **Always** — injected via `{violation_count?}` |
| `user_id` | Never (booking_agent had to call tool to get it) | **Always** — injected via `{user_id?}` |
| `pending_intents` | Only from conversation history | **Always** — injected via `{pending_intents?}` |
| `current_intent` | Only from conversation history | **Always** — injected via `{current_intent?}` |
