# CHANGELOG

---

## [2026-03-12] — Multi-Intent: Clarify First + User Confirmation Between Intents

### What changed and why
Previously, multi-intent was handled silently: the root agent queued all intents and auto-advanced through them without telling the user. This caused issues when interactive sub-agents (e.g. booking) needed multiple turns — the queue would get wiped mid-flow.

The new design: **any agent** can own the multi-intent queue. Each intent is confirmed with the user before running, and again before advancing to the next.

---

### Files changed

#### `prompts/fragments/multi_intent.md` ⚠️ REPLACE ENTIRE FILE
**Old behaviour:** Queue silently, auto-advance after each sub-agent returns.
**New behaviour:**
- Step 2: Present detected intents to user, ask confirmation before calling `set_pending_intents`
- Step 4: After each intent completes, call `advance_intent()` then ask "Ready to move on to X?" — wait for yes

#### `prompts/templates/root_agent.md` — Step 7 only
**Old:**
```
### Step 7 — After sub-agent returns
Follow the advance-intent steps in the MULTI-INTENT HANDLING section above.
```
**New:**
```
### Step 7 — After sub-agent returns
- If `current_intent` is set in SESSION CONTEXT → sub-agent is mid-flow. Route reply back to same sub-agent. Do NOT call `advance_intent`.
- If `pending_intents` is empty and `current_intent` is None → all intents done. Give a brief closing response.
- Sub-agents own `advance_intent` and user confirmation between intents — do not call it here.
```

#### `agents/rag_agent_instruction.md` ⚠️ RECOMPILE FROM FRAGMENTS
Re-generated from `agents/_fragments/rag_agent.md`. Now includes `{{ shared_multi_intent }}` after Step 2 (violation check). Step numbers shifted by +1 from Step 4 onward. Tools table has two new rows:
- `set_pending_intents(intents)` — call ONCE after user confirms
- `advance_intent()` — after completing current intent

#### `agents/booking_agent_instruction.md` ⚠️ RECOMPILE FROM FRAGMENTS
Same as rag — `{{ shared_multi_intent }}` injected after Step 2. Step numbers shifted. Tools table has same two new rows.

#### `agents/_fragments/shared_multi_intent.md` — NEW FILE
New shared fragment used by `agents/_fragments/` system (rag, booking, root). Same "clarify first, confirm between each" logic as `prompts/fragments/multi_intent.md`. Injected via `{{ shared_multi_intent }}`.

#### `agents/_fragments/rag_agent.md`
- Added `### Step 3 — Multi-intent check` with `{{ shared_multi_intent }}`
- Renumbered Steps 3→4, 4→5, 5→6, 6→7, 7→8

#### `agents/_fragments/booking_agent.md`
- Added `### Step 3 — Multi-intent check` with `{{ shared_multi_intent }}`
- Renumbered Steps 3→4, 4→5, 5→6, 6→7, 7→8, 8→9, 9→10

#### `agents/_fragments/root_agent.md`
- Step 5 replaced with `{{ shared_multi_intent }}`
- Step 7 simplified (sub-agents own the queue, root just re-routes mid-flow)

#### `tools/state/state_tools.py` — `clear_intent_queue_on_completion` function
**Old:** Wiped `pending_intents` and `current_intent` at the end of every root agent turn.
**New:** Only wipes if `pending_intents` is non-empty **and** `current_intent` is None (LLM lost track). Leaves queue intact when `current_intent` is set (sub-agent mid-flow across turns).

```python
# Old
if state.get("pending_intents"):
    state["pending_intents"] = []
    state["current_intent"] = None

# New
pending = state.get("pending_intents", [])
current = state.get("current_intent")
if pending and current is None:
    state["pending_intents"] = []
```

---

### How to replicate in sandbox

1. Replace `prompts/fragments/multi_intent.md` with the new version (Step 1–4 + Rules structure)
2. Update `prompts/templates/root_agent.md` Step 7 text only
3. Update `tools/state/state_tools.py` — `clear_intent_queue_on_completion` body
4. Recompile `agents/rag_agent_instruction.md` and `agents/booking_agent_instruction.md` by running:
   ```
   py -c "
   import re
   from pathlib import Path
   FRAGMENTS_DIR = Path('agents/_fragments')
   FILE_CACHE = {p.stem: p.read_text(encoding='utf-8') for p in FRAGMENTS_DIR.glob('*.md')}
   TOKEN_RE = re.compile(r'\{\{\s*(\w+)\s*\}\}')
   def resolve(t):
       return TOKEN_RE.sub(lambda m: FILE_CACHE[m.group(1).strip()], t)
   Path('agents/rag_agent_instruction.md').write_text(resolve(FILE_CACHE['rag_agent']), encoding='utf-8')
   Path('agents/booking_agent_instruction.md').write_text(resolve(FILE_CACHE['booking_agent']), encoding='utf-8')
   print('Done')
   "
   ```
   Or manually copy the content from `agents/_fragments/rag_agent.md` and `booking_agent.md` and expand the `{{ }}` tokens by hand.
