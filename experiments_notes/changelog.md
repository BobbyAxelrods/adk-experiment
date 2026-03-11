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

---

## 2026-03-11 — Full Refactor: Centralized State, Multi-Intent, Instruction Alignment

### Overview

Four changes implemented in one session:
1. Centralized all tools and callbacks into `tools/state/state_tools.py`
2. Revised state management to follow ADK patterns correctly
3. Implemented multi-intent handler
4. Updated all agent instructions to use `{key?}` SESSION CONTEXT injection

---

### CHANGE 1 — Centralized State Manager (`tools/state/`)

#### What changed

Created two new files:
- `tools/state/keys.py` — registry of all state key name constants
- `tools/state/state_tools.py` — all 11 tools + all 3 callbacks in one file

Converted old files to thin re-export shims (keep old imports working, zero breakage):
- `tools/policy_tools/policy_tools.py`
- `tools/mcp_escalation/escalation_tools.py`
- `agents/callback.py`

#### Why

State was being mutated in 4 different files with no single source of truth:
- `tools/policy_tools/policy_tools.py` — frustration, violation, language tools
- `tools/mcp_escalation/escalation_tools.py` — escalation tools
- `agents/callback.py` — callbacks
- `agents/agent.py` — INITIAL_STATE

Key names were raw string literals (`"frustration_count"`, `"escalation_recommended"`)
scattered across all these files. A single typo would silently create a new key instead
of raising an error. There was no way to know the full list of state keys without grepping
6 files manually.

#### Code: `keys.py` — the constant registry

```python
# tools/state/keys.py
# Import from here everywhere. Typo = AttributeError immediately.

FRUSTRATION_COUNT         = "frustration_count"
VIOLATION_COUNT           = "violation_count"
UNRECOGNIZED_INTENT_COUNT = "unrecognized_intent_count"
ESCALATION_RECOMMENDED    = "escalation_recommended"
ESCALATED_TO_HUMAN        = "escalated_to_human"
LANGUAGE                  = "language"
USER_ID                   = "user_id"
AUTHENTICATION            = "authentication"
PENDING_INTENTS           = "pending_intents"
CURRENT_INTENT            = "current_intent"
LAST_ESCALATION_TICKET    = "last_escalation_ticket"
ESCALATION_HISTORY        = "escalation_history"
CONVERSATION_SUMMARY      = "conversation_summary"
TEMP_TURN_SIGNAL          = "temp:turn_signal"
```

#### Code: `state_tools.py` — file structure

```python
# tools/state/state_tools.py
# Section 1  — FRUSTRATION      : _track_frustration
# Section 2  — VIOLATION        : _flag_violation, _report_violation_to_root, _record_unrecognized_intent
# Section 3  — LANGUAGE         : _detect_language
# Section 4  — ESCALATION       : _escalate_to_live_agent, _return_to_bot, _request_callback
# Section 5  — MULTI-INTENT     : _set_pending_intents, _advance_intent
# Section 6  — CONVERSATION     : _update_summary
# Section 7  — CALLBACKS        : count_unrecognized_intents, reset_unrecognized_intent,
#                                  clear_intent_queue_on_completion
# Section 8  — FunctionTool reg : all tools wrapped with FunctionTool(func=_fn) at bottom

from .keys import FRUSTRATION_COUNT, ESCALATION_RECOMMENDED, ...
```

#### Code: re-export shim pattern

```python
# tools/policy_tools/policy_tools.py  (same for mcp_escalation, callback.py)
from tools.state.state_tools import (
    track_frustration,
    flag_violation,
    set_pending_intents,
    advance_intent,
    ...
)
# Any file that already imports from here keeps working — zero import breakage
```

#### Reasoning

Functions are prefixed `_fn` (e.g. `_track_frustration`) to keep the raw function
private. At the bottom of the file, `FunctionTool(func=_track_frustration)` is
assigned to the public name `track_frustration`. This means:
- The `FunctionTool` object is what gets imported and passed to `Agent(tools=[...])`
- The raw function cannot be accidentally passed directly as a tool
- Import consumers always get the correct wrapped version

---

### CHANGE 2 — State Management Revised to Follow ADK Patterns

#### a) `temp:` prefix replaces manual reset callback

```python
# BEFORE — regular session key, persists across turns, needed manual cleanup
tool_context.state["turn_detection"] = "frustration"
# reset_turn_detection callback existed solely to clear this after every turn

# AFTER — ADK auto-deletes temp: keys after each turn (invocation scope)
tool_context.state["temp:turn_signal"] = "frustration"
# reset_turn_detection callback deleted entirely
```

**Reasoning:** ADK has 4 state scopes. The `temp:` prefix means invocation scope —
the key lives only for the current turn and is automatically removed by ADK after the
turn completes. Using the wrong scope (session scope for a turn-level signal) required
a cleanup callback that was pure boilerplate. Using `temp:` removes the need for it.

ADK State Scopes:
| Prefix | Scope | Lifetime |
|---|---|---|
| *(none)* | Session | Whole session |
| `temp:` | Invocation | Current turn only — auto-deleted |
| `user:` | User | Across sessions for same user |
| `app:` | App | All users, all sessions |

#### b) Unified `escalated_to_human` key

```python
# BEFORE — two different keys, same concept, neither reliably read
INITIAL_STATE = {"escalate_to_human": None}    # verb, past undefined
state["escalated_to_human"] = True             # past tense, different name

# AFTER — one key, one spelling, correct boolean default
INITIAL_STATE = {"escalated_to_human": False}
# escalate_to_live_agent writes: state["escalated_to_human"] = True
# return_to_bot writes:          state["escalated_to_human"] = False
```

**Reasoning:** Two different string literals for the same concept meant neither key
was ever consistently read. The `?` optional injection in instructions would render
the wrong key as empty, making the LLM think the user was never escalated.

#### c) `escalation_recommended` set by ALL 4 trigger paths

```python
# BEFORE — escalate_to_live_agent forgot to set it
def escalate_to_live_agent(...):
    state["escalated_to_human"] = True
    state["last_escalation_ticket"] = ticket_id
    # escalation_recommended was NOT set here — bug

# AFTER
def _escalate_to_live_agent(tool_context, reason, context):
    state[ESCALATED_TO_HUMAN]     = True
    state[ESCALATION_RECOMMENDED] = True   # ← added
    state[LAST_ESCALATION_TICKET] = ticket_id
    ...
```

**Reasoning:** Every agent reads `escalation_recommended` from SESSION CONTEXT to decide
whether to stop routing. If `escalate_to_live_agent` doesn't set it, an escalation ticket
is created but agents keep routing the user through sub-agents anyway, because they see
`escalation_recommended=False` in their context.

All 4 paths that set `escalation_recommended=True`:
1. `track_frustration` — at `frustration_count >= 3`
2. `flag_violation` — at `violation_count >= 3`
3. `escalate_to_live_agent` — immediately on call
4. `count_unrecognized_intents` callback — at `unrecognized_intent_count >= 3`

#### d) `update_summary` fixed — now actually writes state

```python
# BEFORE — returned a dict but never touched state (was a silent no-op)
def update_summary(tool_context, summary):
    return {"updated": True, "summary": summary}

# AFTER — correctly writes to session state
def _update_summary(tool_context: ToolContext, summary: str) -> dict:
    tool_context.state[CONVERSATION_SUMMARY] = summary
    return {"updated": True, "summary": summary}
```

**Reasoning:** The LLM was calling this tool believing the summary was being persisted.
It was not. The returned dict was discarded. Tools must use `tool_context.state[key] = value`
to actually write to session state — returning a value from a tool only sends it back
to the LLM as the tool result, it does not affect state.

#### e) Clean `INITIAL_STATE`

```python
INITIAL_STATE = {
    "user_id":                   USER_ID,     # kept
    "language":                  "english",   # kept
    "authentication":            False,        # kept

    "frustration_count":         0,            # kept
    "violation_count":           0,            # kept — was missing before
    "unrecognized_intent_count": 0,            # kept

    "escalation_recommended":    False,        # kept
    "escalated_to_human":        False,        # RENAMED from escalate_to_human
    "last_escalation_ticket":    None,         # ADDED — tool wrote it, never initialised
    "escalation_history":        [],           # ADDED — tool wrote it, never initialised

    "pending_intents":           [],           # kept
    "current_intent":            None,         # kept

    "conversation_summary":      "",           # ADDED — update_summary now writes here
    # REMOVED: "frustration_threshold": 3     — hardcoded constant in tool, not state
    # REMOVED: "escalate_to_human": None      — renamed to escalated_to_human
}
```

**Reasoning:** Every key any tool or callback writes must be declared in INITIAL_STATE
with a correct type and default. Undeclared keys work at runtime (dict accepts any key)
but cause three problems: (1) `{key?}` injection renders empty instead of the default,
(2) state inspection shows confusing missing keys on the first turn, (3) some ADK
session backends (e.g. DatabaseSessionService) may behave differently on first write
vs. update of a key.

---

### CHANGE 3 — Multi-Intent Handler

#### What changed

Added to `tools/state/state_tools.py`:
- `_set_pending_intents` → `FunctionTool` as `set_pending_intents`
- `_advance_intent` → `FunctionTool` as `advance_intent`
- `clear_intent_queue_on_completion` callback (safety net)

Both tools added to `root_agent` tools list in `agents/agent.py`.
Both added to `_DISALLOWED_RESET_TOOLS` in `count_unrecognized_intents` callback.
`clear_intent_queue_on_completion` wired as `after_agent_callback` on root_agent.

#### Why

When a user sends one message with 2+ distinct intents (e.g. "what does my policy
cover AND book me an appointment"), root_agent routed to the first sub-agent and
silently dropped the second intent. No mechanism existed to queue multiple intents
and process them sequentially.

#### Code: `set_pending_intents`

```python
def _set_pending_intents(tool_context: ToolContext, intents: list) -> dict:
    """
    Call at START of turn when user message has 2+ distinct intents.
    Valid labels: "policy_query", "booking", "vas_query", "escalation", "greeting"
    Order by urgency: safety > policy > booking > vas > greeting
    """
    tool_context.state[PENDING_INTENTS] = intents
    tool_context.state[CURRENT_INTENT]  = intents[0] if intents else None
    return {
        "status":          "saved",
        "current_intent":  tool_context.state[CURRENT_INTENT],
        "pending_intents": intents,
    }
```

**Reasoning:** Stores the full list and immediately sets `current_intent` to the first
item. Root agent reads `current_intent` from SESSION CONTEXT (already injected) to
know what to route next — it doesn't need to inspect `pending_intents` directly.

#### Code: `advance_intent`

```python
def _advance_intent(tool_context: ToolContext) -> dict:
    """
    Call after sub-agent returns. Pops completed intent, promotes next one.
    done=True means queue is empty — give consolidated closing response.
    """
    pending = list(tool_context.state.get(PENDING_INTENTS, []))
    if pending:
        pending.pop(0)                         # remove head (completed intent)
    next_intent = pending[0] if pending else None
    tool_context.state[PENDING_INTENTS] = pending
    tool_context.state[CURRENT_INTENT]  = next_intent
    return {
        "next_intent": next_intent,
        "remaining":   len(pending),
        "done":        next_intent is None,    # signal to root: queue empty
    }
```

**Reasoning:** `pop(0)` removes the front of the list. This is a FIFO queue — intents
are processed in the order they were declared (urgency order). The `done=True` flag is
the explicit signal to root_agent to stop routing and give the user a final combined
response instead of routing to another sub-agent.

#### Code: callback guard

```python
_DISALLOWED_RESET_TOOLS = {
    "record_unrecognized_intent",
    "response_tone_guideline",
    "detect_language",
    "flag_violation",
    "report_violation_to_root",
    "set_pending_intents",    # routing helper — NOT a genuine success signal
    "advance_intent",         # routing helper — NOT a genuine success signal
}
```

**Reasoning:** `count_unrecognized_intents` callback resets `unrecognized_intent_count`
to 0 whenever it sees a "real" tool call (genuine success signal). Without this guard,
calling `set_pending_intents` or `advance_intent` would look like success and reset the
counter even though nothing was actually resolved for the user.

#### Code: safety net callback

```python
def clear_intent_queue_on_completion(callback_context: CallbackContext) -> None:
    """after_agent_callback on root_agent only."""
    state = callback_context.state
    if state.get(PENDING_INTENTS):         # non-empty = LLM forgot to advance
        state[PENDING_INTENTS] = []
        state[CURRENT_INTENT]  = None
```

**Reasoning:** LLMs occasionally forget to call `advance_intent` after a sub-agent
returns, leaving stale intents in the queue. Without this callback, the stale entries
would persist into the next user turn, causing root_agent to route to the wrong
sub-agent based on an old `current_intent`. `after_agent_callback` fires after
root_agent finishes each turn — the cleanup is invisible to the user.

#### Execution flow

```
User: "What does my policy cover AND book me a cardiologist appointment?"

root_agent Step 5 — detects 2 intents:
  set_pending_intents(["policy_query", "booking"])
  state: pending=["policy_query","booking"], current="policy_query"

root_agent Step 6 — routes:
  current_intent="policy_query" → transfer to rag_agent

rag_agent answers → returns to root_agent

root_agent Step 7 — advances queue:
  advance_intent()
  state: pending=["booking"], current="booking", done=False

root_agent Step 6 — routes:
  current_intent="booking" → transfer to booking_agent

booking_agent books → returns to root_agent

root_agent Step 7 — advances queue:
  advance_intent()
  state: pending=[], current=None, done=True

root_agent: done=True → consolidated closing response

after_agent_callback (clear_intent_queue_on_completion):
  pending=[] already — nothing to clean up
```

---

### CHANGE 4 — Instruction Alignment with `{key?}` SESSION CONTEXT

#### What changed

Created `prompts/fragments/shared_session_context.md` — a shared fragment injected
into all 6 agent templates via `{{SHARED_SESSION_CONTEXT}}`.

Rewrote Step 1 of every agent from "check state" (non-functional) to "read SESSION
CONTEXT" (functional). Rewrote `policy_mcp_agent` authentication gate.

#### Why

ADK substitutes `{key?}` in instruction strings with `session.state["key"]` BEFORE
sending to the LLM, once per turn. Previously all agent instructions told the LLM to
"check if authentication is True" or "check escalation_recommended" — but the LLM had
no mechanism to read those values. It was guessing from conversation history.

With `{key?}` injection, real values appear in the system prompt as plain text.
The LLM reads "Authenticated | False" in a table and acts on it reliably.

#### Code: the fragment

```markdown
<!-- prompts/fragments/shared_session_context.md -->
## SESSION CONTEXT
> Live state values injected by ADK at the start of every turn.

| Key | Value |
|-----|-------|
| Language | {language?} |
| User ID | {user_id?} |
| Authenticated | {authentication?} |
| Frustration count | {frustration_count?} |
| Violation count | {violation_count?} |
| Escalation recommended | {escalation_recommended?} |
| Escalated to human | {escalated_to_human?} |
| Pending intents | {pending_intents?} |
| Current intent | {current_intent?} |
```

**Why `?` on every key:** `{key}` (no `?`) throws an ADK error if the key is absent
from state. `{key?}` renders as empty string if missing — safe default. Since
INITIAL_STATE now declares every key, the `?` is technically redundant for known keys,
but it is kept as a safety net for any future key additions that might not be in
INITIAL_STATE yet.

#### How the two-pass system works

```
Pass 1 — PromptManager at import time (static composition):
  Template: "{{IDENTITY}}\n{{SHARED_SESSION_CONTEXT}}\n..."
  PromptManager replaces {{TOKEN}} with the .md file content
  Result: full static instruction string with {key?} placeholders intact

Pass 2 — ADK at each turn (runtime injection):
  ADK sees: "Authenticated | {authentication?}"
  ADK looks up session.state["authentication"] → False
  ADK injects: "Authenticated | False"
  LLM receives the complete prompt with real values
```

PromptManager only touches `{{DOUBLE_BRACE}}` tokens.
ADK only touches `{single_brace?}` tokens.
They never interfere with each other.

#### Code: policy_mcp_agent authentication gate — before vs after

```markdown
// BEFORE — LLM told to check a value it cannot see
## AUTHENTICATION GATE
Check the session state:
- If authentication is False OR authentication_required is True:
  → block user

// AFTER — value is visible in SESSION CONTEXT table above
## AUTHENTICATION GATE — MUST run before any tool call
Check authentication in SESSION CONTEXT above.
- If authentication is False or empty:
  1. Do NOT call any policy tools.
  2. Tell the user: "To view your policy details, please verify your identity first."
  3. transfer_to_agent("root_agent") immediately.
- Only proceed if authentication is True.
```

**Reasoning:** The old gate used `authentication_required` (a different key that was
set by a callback, not by INITIAL_STATE). The new gate uses `authentication` directly
from the injected SESSION CONTEXT table — the value the LLM can see is the exact value
from state, no intermediate key needed.

#### Agents updated

| Agent | SESSION CONTEXT added | Key behaviour change |
|---|---|---|
| `root_agent` | ✓ | Step 1 checks escalation_recommended, escalated_to_human, violation_count before routing |
| `booking_agent` | ✓ | Step 1 checks escalation; Step 4 auth gate reads from context |
| `rag_agent` | ✓ | Step 1 checks escalation |
| `escalation_agent` | ✓ | Step 1 reads frustration_count so it doesn't ask user to repeat |
| `policy_mcp_agent` | ✓ | Auth gate now reads live authentication value |
| `evaluation_agent` | ✓ | Context added (minimal — no routing logic change) |

---

### Final State Ownership Map

| Key | Written by | When | Injected into |
|---|---|---|---|
| `language` | `detect_language` | Language detected | All agents |
| `authentication` | `INITIAL_STATE` / external | Session start / auth flow | All agents |
| `user_id` | `INITIAL_STATE` | Session start | `booking_agent`, `policy_mcp_agent` |
| `frustration_count` | `track_frustration` | Frustration signal | All agents |
| `violation_count` | `flag_violation` | Violation detected | All agents |
| `unrecognized_intent_count` | `count_unrecognized_intents` callback ONLY | After each model call | Callback only — not injected |
| `escalation_recommended` | `track_frustration`, `flag_violation`, `escalate_to_live_agent`, `count_unrecognized_intents` | Threshold crossed | All agents |
| `escalated_to_human` | `escalate_to_live_agent`, `return_to_bot` | Handoff / return | All agents |
| `pending_intents` | `set_pending_intents`, `advance_intent` | Multi-intent turn | `root_agent` |
| `current_intent` | `set_pending_intents`, `advance_intent` | Multi-intent routing | `root_agent` |
| `conversation_summary` | `update_summary` | After resolved request | Optional |
| `last_escalation_ticket` | `escalate_to_live_agent` | Escalation created | Audit only |
| `temp:turn_signal` | `track_frustration` | Each frustration signal | Expires — never injected |

---

### Files Changed

| File | Change |
|---|---|
| `tools/state/__init__.py` | NEW — package init |
| `tools/state/keys.py` | NEW — 14 state key constants |
| `tools/state/state_tools.py` | NEW — all 11 tools + 3 callbacks centralized |
| `tools/policy_tools/policy_tools.py` | REWRITE — thin re-export shim |
| `tools/mcp_escalation/escalation_tools.py` | REWRITE — thin re-export shim |
| `agents/callback.py` | REWRITE — thin re-export shim |
| `agents/agent.py` | REWRITE — clean INITIAL_STATE, import from state_tools, multi-intent tools, all sub-agents |
| `prompts/fragments/shared_session_context.md` | NEW — `{key?}` injection fragment |
| `prompts/templates/root_agent.md` | REWRITE — SESSION CONTEXT + 8-step workflow with multi-intent Steps 5-7 |
| `prompts/templates/booking_agent.md` | REWRITE — SESSION CONTEXT + auth reads from context |
| `prompts/templates/rag_agent.md` | REWRITE — SESSION CONTEXT + clean workflow |
| `prompts/templates/escalation_agent.md` | REWRITE — SESSION CONTEXT + reads frustration_count |
| `prompts/templates/policy_mcp_agent.md` | REWRITE — SESSION CONTEXT + functional auth gate |
| `prompts/templates/evaluation_agent.md` | MODIFIED — SESSION CONTEXT added |
