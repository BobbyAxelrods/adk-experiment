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

---

## Coding Logic — How Each Change Was Implemented

This section explains the actual code pattern used for each change so you can replicate or extend the same pattern elsewhere.

---

### Pattern 1 — Fragment Loader (`agents/_fragments/loader.py`)

**The problem it solves:** Agent instructions were long strings hardcoded in each agent file or loaded from separate `.md` files with no reuse. Shared content (identity, language rules, session context) was copy-pasted into every instruction — any edit needed to be made in 7+ places.

**How it works:**

```
Step 1 — At import time, glob all *.md files in _fragments/ into a dict
         { "shared_identity": "...", "root_agent": "...", etc. }

Step 2 — Define a regex: \{\{\s*(\w+)\s*\}\}
         This matches {{ token_name }} inside any template string

Step 3 — For each agent name in the list, find its .md file,
         run _resolve() on it which replaces every {{ token }} with the
         matching file's content from the dict

Step 4 — Store the fully resolved strings in _INSTRUCTION_CACHE

Step 5 — load_instruction("root_agent") just does a dict lookup —
         zero disk I/O at call time
```

**Key code pattern:**
```python
# glob into dict at import time
_FILE_CACHE = {
    path.stem: path.read_text(encoding="utf-8")
    for path in _FRAGMENTS_DIR.glob("*.md")
}

# regex replace {{ token }} with file contents
_TOKEN_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")

def _resolve(template: str) -> str:
    def replacer(match):
        name = match.group(1).strip()
        return _FILE_CACHE[name]      # KeyError if token not found = safe failure
    return _TOKEN_RE.sub(replacer, template)

# resolve once at import, cache forever
_INSTRUCTION_CACHE[name] = _resolve(_FILE_CACHE[name])
```

**To add a new shared fragment:** create `agents/_fragments/my_fragment.md`, then reference it anywhere as `{{ my_fragment }}` in any agent `.md` file. No Python changes needed.

---

### Pattern 2 — Session Context Injection (`agents/_fragments/shared_session_context.md`)

**The problem it solves:** Agents were told "check state for user_id" but ADK doesn't let the LLM read raw state — so the LLM was guessing from conversation history. The LLM had no reliable way to know if the user was authenticated, frustrated, or had pending intents.

**How it works:**

ADK supports `{key?}` template syntax inside instruction strings. Before each turn, ADK substitutes every `{key?}` with the current value from `session.state`. The `?` means "render empty string if key is missing" — it never crashes.

```markdown
## SESSION CONTEXT
- Language: {language?}
- User ID: {user_id?}
- Authenticated: {authentication?}
- Frustration count: {frustration_count?}
- Escalation recommended: {escalation_recommended?}
```

**This file is then pulled into every agent instruction via `{{ shared_session_context }}`.**

The result: every agent's system prompt, at the start of every turn, contains the actual live values. The LLM reads them like normal text — no tool call needed to find out if the user is authenticated.

**The `?` suffix is critical** — without it, a missing key raises an error. Always use `{key?}` not `{key}` for optional state values.

---

### Pattern 3 — `temp:` Key Auto-Expiry (`tools/policy_tools/policy_tools.py` — `track_frustration`)

**The problem it solves:** `track_frustration` was writing a `turn_detection` key to track whether it had already been called this turn (to avoid double-counting). But regular state keys persist across turns — so a manual reset callback was needed after every turn to clean it up.

**How it works:**

ADK has a built-in convention: any state key prefixed with `temp:` is automatically deleted at the end of the turn. No callback, no cleanup code needed.

```python
# Before (persists across turns, needs manual reset):
tool_context.state["turn_detection"] = "frustration"

# After (auto-deleted after the turn ends):
tool_context.state["temp:turn_detection"] = "frustration"
```

**Rule of thumb:** use `temp:` for any key that is only meaningful for the current turn (e.g. "did I already call this tool this turn?"). Use a plain key for anything that must survive across turns (counters, flags, user data).

---

### Pattern 4 — `FunctionTool` Registration Pattern (`tools/policy_tools/policy_tools.py`)

**The problem it solves:** ADK requires tools to be `FunctionTool` objects, not raw Python functions, to be passed to `Agent(tools=[...])`. Without this, ADK either ignores them or errors.

**How it works:**

Define the function with `tool_context: ToolContext` as a parameter (ADK injects this automatically), then wrap it:

```python
# 1. Define the function — ToolContext is injected by ADK, not called manually
def track_frustration(tool_context: ToolContext) -> dict:
    count = tool_context.state.get("frustration_count", 0) + 1
    tool_context.state["frustration_count"] = count
    return {"frustration_count": count}

# 2. Wrap as FunctionTool at module level (bottom of file)
track_frustration = FunctionTool(func=track_frustration)

# 3. Import and pass to Agent
from tools.policy_tools.policy_tools import track_frustration
root_agent = Agent(tools=[track_frustration, ...])
```

**Why re-assign the same name:** `track_frustration = FunctionTool(func=track_frustration)` shadows the function with the tool object. This means any file that does `from tools.policy_tools.policy_tools import track_frustration` gets the `FunctionTool`, not the raw function. Consistent and safe.

---

### Pattern 5 — `after_model_callback` for Passive Counting (`agents/callback.py`)

**The problem it solves:** Counting unrecognized intents inside the tool itself would require the LLM to call the tool correctly every time. Putting the counter logic in a callback means it runs automatically after every model response — the LLM only needs to signal intent, not manage the counter.

**How it works:**

```
after_model_callback fires after every LLM response, before the response is returned.
It receives: callback_context (has .state), llm_response (has .content.parts)

Logic:
  1. Scan llm_response.content.parts for function_call objects
  2. If the LLM called record_unrecognized_intent → increment counter
  3. If the LLM called any other "real" tool → reset counter (genuine success)
  4. If counter >= 3 → set escalation_recommended = True, reset counter
  5. Always return llm_response unchanged (never block the response)
```

```python
def count_unrecognized_intents(callback_context, llm_response):
    for part in llm_response.content.parts:
        func_call = getattr(part, "function_call", None)
        if func_call:
            name = getattr(func_call, "name", "")
            if name == "record_unrecognized_intent":
                called_record_unrecognized = True
            elif name not in disallowed_reset_tools:
                saw_success_tool = True    # real tool = genuine success = reset

    if called_record_unrecognized:
        state["unrecognized_intent_count"] += 1
        if count >= 3:
            state["escalation_recommended"] = True
    elif saw_success_tool:
        state["unrecognized_intent_count"] = 0

    return llm_response    # must return — returning None would swallow the response
```

**`disallowed_reset_tools`** is the set of signal/routing tools that don't count as genuine success (e.g. `detect_language`, `flag_violation`). Without this list, calling any tool would reset the counter even if the LLM was still confused.

---

### Pattern 6 — INITIAL_STATE as the Single Source of Truth (`agents/agent.py`)

**The problem it solves:** Tools were writing state keys like `violation_count`, `escalation_history`, `last_escalation_ticket` on first use — but those keys never existed in initial state. This means on the very first read (e.g. `state.get("violation_count", 0)`), the default was used, but it was never formally declared anywhere. This caused subtle bugs where state checks worked sometimes but not others.

**How it works:**

```python
INITIAL_STATE = {
    # User context
    "user_id":                   USER_ID,
    "language":                  "english",
    "authentication":            False,

    # Counters — all start at 0
    "frustration_count":         0,
    "violation_count":           0,
    "unrecognized_intent_count": 0,

    # Escalation — all start at False/None/[]
    "escalation_recommended":    False,
    "escalated_to_human":        False,
    "last_escalation_ticket":    None,
    "escalation_history":        [],

    # Multi-intent queue
    "pending_intents":           [],
    "current_intent":            None,
}
```

**Rule:** every key that any tool or callback reads or writes should be declared here with its zero/empty/default value. If a tool writes to a key that isn't in `INITIAL_STATE`, add it. This makes state predictable from turn 0.

**`output_key="root_agent_output"`** on the `root_agent` replaces the old `update_summary` tool — ADK automatically writes the agent's final text response to `session.state["root_agent_output"]` after every turn. No tool needed, no state key to declare.

---

### Pattern 7 — Multi-Intent Queue (`set_pending_intents` + `advance_intent`)

**The problem it solves:** When a user sends a message with two intents (e.g. "what does my policy cover AND book me an appointment"), the root agent would only handle one. The other was lost.

**How it works — two tools, one queue in state:**

```
Turn start:
  LLM detects multiple intents → calls set_pending_intents(["policy_query", "booking"])
  State: pending_intents=["policy_query", "booking"], current_intent="policy_query"

Root agent routes to rag_agent for policy_query.
rag_agent returns.

Root agent calls advance_intent():
  State: pending_intents=["booking"], current_intent="booking"
  Returns: {next_intent: "booking", remaining: 1, done: False}

Root agent routes to booking_agent.
booking_agent returns.

Root agent calls advance_intent():
  State: pending_intents=[], current_intent=None
  Returns: {next_intent: None, remaining: 0, done: True}

done=True → give consolidated closing response.
```

```python
def set_pending_intents(tool_context, intents: list):
    tool_context.state["pending_intents"] = intents
    tool_context.state["current_intent"]  = intents[0] if intents else None

def advance_intent(tool_context):
    pending = tool_context.state.get("pending_intents", [])
    pending.pop(0)                        # remove completed intent
    next_intent = pending[0] if pending else None
    tool_context.state["pending_intents"] = pending
    tool_context.state["current_intent"]  = next_intent
    return {"next_intent": next_intent, "done": next_intent is None}
```

The queue is a plain list in state — `pop(0)` removes the head, the next item becomes `current_intent`. The LLM reads `current_intent` from SESSION CONTEXT to know what to route next.

---

### Pattern 8 — `escalation_recommended` as a Shared Stop Signal

**The problem it solves:** Multiple tools could trigger escalation (`track_frustration`, `flag_violation`, `escalate_to_live_agent`) but only some of them were setting `escalation_recommended = True`. Sub-agents had no reliable way to know they should stop routing and escalate.

**How it works — every escalation path sets the same key:**

```python
# track_frustration — sets it at threshold 3
if count >= FRUSTRATION_THRESHOLD:
    tool_context.state["escalation_recommended"] = True

# flag_violation — sets it at 3 violations
if count >= 3:
    tool_context.state["escalation_recommended"] = True

# escalate_to_live_agent — sets it immediately, always
state["escalation_recommended"] = True

# count_unrecognized_intents callback — sets it at 3 unrecognized
if current >= 3:
    state["escalation_recommended"] = True
```

Every agent instruction starts with `{{ shared_session_context }}` which injects the current value. Step 1 of every agent is: "if `escalation_recommended` is True → stop, go to escalation step immediately."

This means the stop signal is always visible to every agent, set by every trigger path, and the LLM sees it in plain text at the start of its system prompt — not buried in a tool response.

---

## Git Integration — Merge `origin/main` into `major` (2026-03-11)

### What Changed

Merged `origin/main` (unrelated history, single "initial" commit from 2026-03-05) into the `major` branch using the `ours` merge strategy.

### Why

The `major` branch and `origin/main` had no common ancestor — they were pushed from separate git lineages. Without this merge, git would refuse to track the two histories as related. The merge formally unifies them into one lineage so future pulls/pushes against `origin/main` work cleanly.

### Strategy: `ours`

The `ours` strategy was used deliberately:

- **All code on `major` is preserved exactly** — no files were overwritten or reverted
- `origin/main` contributed nothing to the working tree; only the commit graph was updated
- Old files that existed only on `origin/main` (e.g. `agents/instruction.md`, `agents/*_instruction.md`, `agents/.adk/session.db`, `tools/escalation_tools/escalation_tools.py`) were **not** restored — they are correctly superseded by the `_fragments/` system and `tools/mcp_escalation/`

### What Was NOT Merged (Intentionally)

| File | Reason skipped |
|---|---|
| `agents/instruction.md` | Replaced by `agents/_fragments/` system |
| `agents/*_instruction.md` (6 files) | Replaced by per-agent fragment `.md` files |
| `agents/.adk/session.db` | Runtime artifact, not source code |
| `tools/escalation_tools/escalation_tools.py` | Duplicate — consolidated into `tools/mcp_escalation/escalation_tools.py` |

### Result

- `major` is now **2 commits ahead of `origin/major`** and ready to push
- Git history is unified — `origin/main` is a reachable ancestor of `major`
- No code regressions; all current architecture (LiteLLM, `_fragments`, multi-intent tools, safety tools) is intact

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
