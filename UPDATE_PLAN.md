# PRU Health — Pending Update Plan

> Based on comparison of `sample_data.txt.md` (reference) vs current codebase state.
> All bug fixes (Bugs 1–7) are already applied and are NOT listed here.
> This plan covers only remaining structural/content gaps.

---

## 1. `agents/instruction.md` — Safety rules stale reference

**File:** `agents/instruction.md`

**Issue:** SAFETY & ESCALATION RULES section still says `violation_count >= 2` triggers escalation, but the threshold was updated to `>= 3`.

**What to update:**
- Line: `violation_count >= 2 in state → escalation_recommended is already True; escalate immediately.`
- Change to: `violation_count >= 3`

---

## 2. `agents/policy_agent_instruction.md` — Old format, not aligned with new schema

**File:** `agents/policy_agent_instruction.md`

**Issue:** Still uses the original unstructured format from before Bug 5 was fixed. Does not follow the IDENTITY → SCOPE → WORKFLOW → TOOLS → RESPONSE FORMAT → SAFETY → LANGUAGE schema used by all other instruction files.

**What to update:**
- Remove `load_supported_languages` tool reference (tool does not exist in codebase)
- Remove `transfer_to_agent` instruction (not an ADK pattern — root agent handles routing)
- Update supported languages: currently says "English, Cantonese, Bahasa Indonesia, Traditional Chinese" — should be "English, Malay, Cantonese" (aligned with `SUPPORTED_LANGUAGES` in `policy_tools.py`)
- Restructure to match the new schema
- Add explicit citation format for `query_corpus` results: filename, page, reference link

---

## 3. `agents/vas_agent_instruction.md` — Old format, not aligned with new schema

**File:** `agents/vas_agent_instruction.md`

**Issue:** Same as `policy_agent_instruction.md` — unstructured, old format. Also has:
- `transfer_to_agent` instruction (invalid)
- Wrong supported languages (Bahasa Indonesia, Traditional Chinese)
- No citation format for corpus results
- Personal policy output format block is included but VAS agent has no `policy_mcp_tool`-equivalent — misleading

**What to update:**
- Restructure to new schema
- Remove `transfer_to_agent`
- Remove personal policy output format (VAS agent doesn't do policy lookups)
- Fix supported languages to: English, Malay, Cantonese
- Add corpus citation format: filename, page, reference link

---

## 4. `agents/policy_mcp_prompt.py` — Minimal, no output format

**File:** `agents/policy_mcp_prompt.py`

**Issue:** The prompt only says "read and output the `data` object" — gives the LLM no formatting instruction. The output will be raw JSON dump, not the required policy block format.

**What to update:**
- Add the required output format after fetching data:
  ```
  ## Policy [policy_id]:
    - [Product_name]: [product_url]
  ## Value Added Service (if exist):
    - vas_1
  ```
- Add instruction to use `product_url` and `product_vas` fields from enriched state (set by `after_tool_update_state_user_policy` callback)

---

## 5. `agents/evaluation_agent_instruction.md` — `transfer_to_agent` invalid reference

**File:** `agents/evaluation_agent_instruction.md`

**Issue:** Instructs to run `transfer_to_agent` after every execution — this is not a valid ADK tool or pattern.

**What to update:**
- Remove `transfer_to_agent` instruction
- Replace with: "After returning evaluation results, the root agent will handle further routing."

---

## 6. `agents/vas_agent.py` — Missing callbacks

**File:** `agents/vas_agent.py`

**Issue:** `vas_agent` has no `before_agent_callback` or `after_model_callback`. All other sub-agents have these. Without them, `unrecognized_intent_count` is not reset on entry and violations are not tracked.

**What to update:**
- Add `before_agent_callback=reset_unrecognized_intent`
- Add `after_model_callback=count_unrecognized_intents`
- Add import: `from .callback import reset_unrecognized_intent, count_unrecognized_intents`
- Add missing tools: `record_unrecognized_intent`, `track_frustration` (referenced in VAS instruction but not in tools list)

---

## 7. `agents/policy_agent.py` — Missing callbacks

**File:** `agents/policy_agent.py`

**Issue:** Same as `vas_agent.py` — no `before_agent_callback` or `after_model_callback`.

**What to update:**
- Add `before_agent_callback=reset_unrecognized_intent`
- Add `after_model_callback=count_unrecognized_intents`
- Add import: `from .callback import reset_unrecognized_intent, count_unrecognized_intents`

---

## 8. `agents/evaluation_agent.py` — Missing callbacks

**File:** `agents/evaluation_agent.py`

**Issue:** No callbacks. Evaluation agent can receive user messages and should track unrecognized intents.

**What to update:**
- Add `before_agent_callback=reset_unrecognized_intent`
- Add `after_model_callback=count_unrecognized_intents`
- Add import: `from .callback import reset_unrecognized_intent, count_unrecognized_intents`

---

## 9. `tools/escalation_tools/escalation_tools.py` — Old duplicate directory still exists

**File:** `tools/escalation_tools/escalation_tools.py`

**Issue:** The old `tools/escalation_tools/` directory still exists alongside the new canonical `tools/mcp_escalation/`. The old file is the pre-fix version — it still has the forced `LlmResponse` override and `escalate_to_human`. Nothing in the new codebase imports from it anymore, but it's dead code that could cause confusion.

**What to update:**
- Delete `tools/escalation_tools/escalation_tools.py` and `tools/escalation_tools/__init__.py`
- Confirm no remaining imports point to it (already verified — only `agents/callbacks.py` did, which is now deleted)

---

## 10. `agents/agent.py` — `INITIAL_STATE` missing `violation_count`

**File:** `agents/agent.py`

**Issue:** `INITIAL_STATE` does not initialise `violation_count`. The callback initialises it lazily, but explicit initialisation in `INITIAL_STATE` is cleaner and consistent.

**What to update:**
- Add `"violation_count": 0` to `INITIAL_STATE`

---

## Summary Table

| # | File | Type | Priority |
|---|---|---|---|
| 1 | `agents/instruction.md` | Stale threshold reference | Low |
| 2 | `agents/policy_agent_instruction.md` | Full restructure + citation format | High |
| 3 | `agents/vas_agent_instruction.md` | Full restructure + citation format | High |
| 4 | `agents/policy_mcp_prompt.py` | Add output format | High |
| 5 | `agents/evaluation_agent_instruction.md` | Remove invalid `transfer_to_agent` | Low |
| 6 | `agents/vas_agent.py` | Add callbacks + missing tools | Medium |
| 7 | `agents/policy_agent.py` | Add callbacks | Medium |
| 8 | `agents/evaluation_agent.py` | Add callbacks | Medium |
| 9 | `tools/escalation_tools/` | Delete old directory | Low |
| 10 | `agents/agent.py` | Add `violation_count` to `INITIAL_STATE` | Low |

---

## Suggested Fix Order

1. Items 6, 7, 8 — callbacks on remaining agents (quick code changes, high correctness impact)
2. Item 10 — `INITIAL_STATE` cleanup (one line)
3. Item 4 — `policy_mcp_prompt.py` output format (affects policy lookup display)
4. Items 2, 3 — instruction restructure (prompt quality, medium effort)
5. Item 5 — evaluation agent instruction cleanup (minor)
6. Item 1 — instruction.md threshold fix (one line)
7. Item 9 — delete old escalation_tools directory (cleanup)
