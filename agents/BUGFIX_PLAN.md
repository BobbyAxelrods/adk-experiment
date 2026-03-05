# PRU Health — Bug Fix Plan

> **Status:** All 5 bugs fixed ✓
> **Files affected:** `agents/callback.py`, `agents/callbacks.py`, `tools/policy_tools/policy_tools.py`, `agents/instruction.md`, `agents/rag_agent_instruction.md`, `agents/booking_agent_instruction.md`, `agents/escalation_agent_instruction.md`

---

## BUG 1 — Callback auto-forces escalation on any no-tool response

### Location
`agents/callback.py` → `count_unrecognized_intents()`
`agents/callbacks.py` → `count_unrecognized_intents()` (same logic, old file)

### Description
The callback increments `unrecognized_intent_count` on **every turn where the model returns no tool call**. When the count hits 3, it **hard-overrides the LLM response** with a forced escalation message.

This is wrong because many valid responses produce no tool call:
- RAG agent returns a plain text answer after `query_corpus` found nothing relevant — it gracefully tells the user, no tool needed on that final turn
- Agent asks a clarifying question (e.g. "Could you clarify your policy number?")
- Agent sends a short greeting or confirmation response
- Agent responds after successfully routing to a sub-agent

All of these are counted as "unrecognized" and eventually force-escalate the user.

### Root Cause
The callback uses "no tool call = unrecognized intent" as a proxy, but this is **not a reliable signal**. A no-tool response is a valid LLM output. The intent classification belongs to the **agent prompt logic**, not the callback layer.

### Solution
1. **Remove the forced `LlmResponse` override from the callback entirely.** The callback should be a passive observer, never a response overrider.
2. The callback still increments the counter and sets `escalation_recommended = True` at threshold — but stops there.
3. The **agent prompt instructions** already have decision rules for `escalation_recommended`. Let the agent act on the flag naturally on its next turn.
4. The callback should only count turns where the agent **explicitly called `record_unrecognized_intent()`** as a signal — not infer from tool absence.

### Change
```python
# callback.py — count_unrecognized_intents
# REMOVE: the `if not has_tool_calls` block that creates forced LlmResponse
# KEEP: only passive counter increment via record_unrecognized_intent signal
# KEEP: setting escalation_recommended = True at threshold (flag only, no override)
```

---

## BUG 2 — Violation count bleeds into unrecognized intent count

### Location
`tools/policy_tools/policy_tools.py` → `flag_violation()` and `record_unrecognized_intent()`
`agents/callback.py` → `reset_unrecognized_intent()`

### Description
`flag_violation` and `record_unrecognized_intent` both write to the **same state key** `unrecognized_intent_count`. This means:
- A user who triggered 2 violations + 1 unrecognized intent = count of 3 → auto-escalates incorrectly combining two separate signals
- `reset_unrecognized_intent()` (called on sub-agent entry) wipes **both** violation and unrecognized counts in one go
- A user who has sent 2 violations, gets routed to `rag_agent`, count resets to 0 — violation history is lost

### Root Cause
Two distinct behavioural signals (policy violations vs genuinely unrecognized intents) are tracked in a single shared counter with a shared reset path.

### Solution
Separate into two independent counters with independent lifecycles:

| State Key | Incremented by | Reset by | Threshold |
|---|---|---|---|
| `unrecognized_intent_count` | `record_unrecognized_intent()` tool + callback | `reset_unrecognized_intent()` on sub-agent entry | 3 turns |
| `violation_count` | `flag_violation()` tool only | Never auto-reset (session-sticky) | 2 violations |
| `escalation_recommended` | Either counter at threshold | Manual only (`return_to_root`) | — |

```python
# policy_tools.py — flag_violation
# CHANGE: write to `violation_count`, not `unrecognized_intent_count`
# ADD: set escalation_recommended = True when violation_count >= 2

# callback.py — reset_unrecognized_intent
# CHANGE: only reset `unrecognized_intent_count`
# NEVER touch `violation_count` or `escalation_recommended`
```

---

## BUG 3 — unrecognized_intent_count starts effectively at 1 on first chat

### Location
`agents/callback.py` → `count_unrecognized_intents()`
`tools/policy_tools/policy_tools.py` → `record_unrecognized_intent()`
`agents/agent.py` → `INITIAL_STATE`

### Description
On the very first user message, the count is already at 2 after 1 turn. This happens because:

1. `INITIAL_STATE` initialises `unrecognized_intent_count` to `0` in `agent.py` — but this is only a local Python dict, **not actually injected into the ADK session state at startup**. The ADK session state starts empty.
2. The callback checks `if "unrecognized_intent_count" not in state` and sets it to `0` — this is the first read.
3. BUT: the prompt instruction says **"MUST call a tool for EVERY turn"** and includes `record_unrecognized_intent()` as a required fallback tool.
4. The agent calls `record_unrecognized_intent()` (via the instruction rule) which increments from `0` → `1`.
5. The callback then also fires on the same turn and increments from `1` → `2`.
6. Result: after a single first message, the count is already `2` — one step away from triggering escalation.

### Root Cause
**Double-counting**: both the tool (`record_unrecognized_intent`) and the callback (`count_unrecognized_intents`) increment the same counter independently on the same turn. They were designed as two separate mechanisms but were never coordinated.

### Solution
**Pick one authoritative counter mechanism, eliminate the other:**
- **Option A (Recommended):** The callback is the sole counter. Remove all counter logic from `record_unrecognized_intent()` tool — it becomes a no-op signal tool (just returns current counts for the agent to read). The callback increments based on a dedicated signal: the presence of a `record_unrecognized_intent` function call in the response.
- **Option B:** The tool is the sole counter. The callback becomes purely a reader/observer with no write behaviour.

**Option A is better** because the callback has visibility over all agent turns including sub-agents, while the tool only fires when the agent explicitly calls it.

```python
# callback.py — count_unrecognized_intents
# CHANGE: only increment when the response contains a `record_unrecognized_intent` function call
# This way: callback counts only when agent explicitly signals unrecognized intent
# No double-counting, no false positives on plain text responses

# policy_tools.py — record_unrecognized_intent
# CHANGE: remove the counter increment logic
# KEEP: just return current state counts so agent can read them
```

---

## BUG 4 — Unsupported language triggers forced escalation via callback

### Location
`agents/callback.py` → `count_unrecognized_intents()`
`agents/instruction.md` — language handling instruction

### Description
When a user writes in an unsupported language (e.g. French, Spanish):
1. The agent cannot determine intent from the foreign-language input
2. The agent either produces no tool call (just a polite text reply) OR calls `record_unrecognized_intent()`
3. The callback counts this as an "unrecognized intent" and increments the counter
4. If this happens multiple times (user keeps replying in unsupported language), the counter hits threshold and triggers forced escalation
5. The user gets escalated to a live agent — not because of a real problem, but because they typed in French

This is the **same root cause as Bug 1** (callback conflates no-tool response with unrecognized intent) but is worth tracking separately because it has a specific user-facing impact.

### Root Cause
Language detection is handled at the prompt level ("if unsupported, inform the user in English"), but the callback does not distinguish between "unsupported language" and "genuinely confused agent". Both look the same to the callback: a text response with no tool call.

### Solution
1. The instruction should tell the agent to call `detect_language(language)` on **every unsupported language detection** — this produces a tool call, which the callback treats as a "recognized" turn (counter reset).
2. After Bug 1 fix, the callback will no longer auto-escalate on no-tool responses anyway, which eliminates the escalation path.
3. Add `detect_language` to the `disallowed_tools` set in the callback (it should not count as a "success tool" that resets the counter, since the user's actual intent still hasn't been resolved).

```markdown
# instruction.md — Language Handling section
# ADD: explicit rule — always call detect_language() when unsupported language is detected
# This ensures the callback sees a tool call and does not count the turn as unrecognized

# callback.py — disallowed_tools set
# ADD: "detect_language" to disallowed_tools so it doesn't reset unrecognized_intent_count
# (language detection ≠ intent resolved)
```

---

## BUG 5 — Agent prompts are unstructured and inconsistent

### Location
`agents/instruction.md`, `agents/rag_agent_instruction.md`, `agents/booking_agent_instruction.md`, `agents/escalation_agent_instruction.md`

### Description
The agent instructions have multiple structural issues:
- **Root agent (`instruction.md`):** Lists `record_unrecognized_intent()` as a mandatory call on every turn — this directly causes the double-counting in Bug 3. Also mixes AVAILABLE TOOLS, DECISION RULES, and SCOPE sections in non-deterministic order that confuses the model.
- **RAG agent (`rag_agent_instruction.md`):** Only 12 lines. No structured workflow. References `policy_mcp_tool` directly but the agent now uses `policy_mcp_agent` as an AgentTool — mismatched.
- **Booking agent (`booking_agent_instruction.md`):** Only 8 lines. No decision tree, no error handling, no scope definition.
- **Escalation agent (`escalation_agent_instruction.md`):** References `check_agent_availability`, `request_callback`, `leave_message` but these tools were removed from the new `escalation_agent.py` tools list. Instruction and agent are out of sync.
- All instructions repeat the same MULTILINGUAL and IDENTITY blocks verbatim — should be in a shared base and referenced once.

### Solution
Restructure all instructions to follow a consistent schema:

```
## IDENTITY
## SCOPE (what you handle / what you don't)
## WORKFLOW (numbered steps — deterministic decision tree)
## TOOLS (what each tool does, when to call it)
## RESPONSE FORMAT
## SAFETY & ESCALATION RULES
## LANGUAGE & TONE (shared base reference)
```

Specific fixes per file:
- **`instruction.md`**: Remove `record_unrecognized_intent()` from "MUST call a tool every turn" rule. Replace with: call appropriate sub-agent OR call `response_tone_guideline` for greetings. Only call `record_unrecognized_intent()` explicitly for true out-of-scope.
- **`rag_agent_instruction.md`**: Expand with full workflow. Update `policy_mcp_tool` references to use `policy_mcp_agent` sub-agent pattern.
- **`booking_agent_instruction.md`**: Add full workflow with steps, scope, and escalation path.
- **`escalation_agent_instruction.md`**: Sync tool list with actual tools in `escalation_agent.py` (remove `check_agent_availability`, `request_callback`, `leave_message` references or add them back to the agent).

---

## BUG 6 — Corpus miss triggers unnecessary escalation to human agent

### Location
`agents/rag_agent_instruction.md` → WORKFLOW step 2

### Description
When a user asks about something not found in the corpus (e.g. "what is greenline"), the RAG agent:
1. Calls `query_corpus` → gets no relevant result
2. Follows the instruction "If corpus returns no relevant result → call `escalate_to_human`"
3. Creates an escalation ticket and routes to a human agent

This is wrong. A corpus miss means the bot doesn't have that specific information — it does NOT mean the user needs a human. The query may be:
- A valid Prudential topic not yet in the corpus
- A misspelling or ambiguous term
- Genuinely out of scope (but that's `record_unrecognized_intent`, not escalation)

Observed in logs:
```
functionCall:
  name: "_escalate_to_human"
  args:
    reason: "Corpus lookup failed for 'Greenline'"
    context: "User asked: 'what is greenline'. query_corpus returned error NotFound."
```

### Root Cause
The RAG agent instruction conflates "no corpus result" with "user needs human help". These are two different situations. The instruction was written too broadly — it tells the agent to escalate whenever it can't find an answer, regardless of whether that's appropriate.

### Solution
Fix `rag_agent_instruction.md` WORKFLOW step 2:
- **Corpus miss** → respond honestly ("I couldn't find specific information on that"), offer to clarify or rephrase. Do NOT escalate. Do NOT count as unrecognized intent.
- **Only escalate** (`escalate_to_human`) if the user explicitly asks for a human OR `escalation_recommended` is already True in state.
- If the query looks genuinely out of Prudential's scope → call `record_unrecognized_intent()` instead.

```markdown
# rag_agent_instruction.md — WORKFLOW step 2
# CHANGE: corpus miss → honest "I don't have that info" response + offer to rephrase
# REMOVE: automatic escalate_to_human on corpus miss
# ADD: escalate_to_human ONLY when user explicitly requests human OR escalation_recommended=True
```

### Status
✓ Fixed — removed `escalate_to_human` from corpus miss path. Now responds with honest "I don't have that info" and asks user to rephrase.

---

## BUG 7 — `escalate_to_human` is a duplicate tool that bypasses `escalation_agent`

### Location
`tools/mcp_escalation/escalation_tools.py` — `_escalate_to_human` / `escalate_to_human`
`agents/rag_agent.py` — tools list
`agents/rag_agent_instruction.md` — tool references

### Description
`escalate_to_human` and `escalate_to_live_agent` were identical functions — both called `create_escalation_ticket` with the same logic. Having `escalate_to_human` as a direct tool on the RAG agent allowed it to:
1. Create escalation tickets directly without going through `escalation_agent`
2. Bypass the proper handoff experience (no warmth, no context gathering)
3. Generate tickets for corpus misses that had nothing to do with needing a human

Observed in logs:
```
functionCall:
  name: "_escalate_to_human"
  args:
    reason: "Corpus lookup failed for 'Greenline'"
```

### Solution
- Removed `_escalate_to_human` function and `escalate_to_human` FunctionTool from `escalation_tools.py`
- Removed `escalate_to_human` import and from RAG agent tools list in `rag_agent.py`
- Updated `rag_agent_instruction.md`: RAG agent now returns to root agent when escalation is needed — ticket creation is `escalation_agent`'s responsibility exclusively

### Status
✓ Fixed

---

## BUG 8 — Sub-agents handle violations, unsupported language, and out-of-scope themselves instead of returning to root

### Location
`agents/rag_agent.py` + `agents/rag_agent_instruction.md`
`agents/booking_agent.py` + `agents/booking_agent_instruction.md`
`agents/escalation_agent_instruction.md`

### Description
Sub-agents were given `flag_violation`, `report_violation_to_root`, `track_frustration`, `record_unrecognized_intent`, and `detect_language` tools and instructed to handle violations and unsupported languages themselves. This caused:

1. **Unsupported language in sub-agents failed** — `detect_language` is only registered on the root agent's tools list. Sub-agents trying to call it get a tool-not-found error or silently respond in the wrong language.
2. **Baby talk / violations in sub-agents not enforced** — sub-agent instruction said to call `flag_violation` but the LLM followed the user's baby-talk style instead, responding like a child. Violation was never actually flagged.
3. **`transfer_to_agent` result is always `null`** — this is expected ADK behaviour (it's a control signal, not a data return). But sub-agent instructions referenced it as if it returned data, causing confusion.

Root cause: safety enforcement was duplicated across all agents. Sub-agents each had partial, inconsistent implementations.

### Solution
- Root agent is the **sole safety enforcement layer**
- Sub-agents: remove all violation/language/frustration tools and instructions
- Sub-agents: for anything outside their scope (violations, unsupported language, gibberish, out-of-scope) → `transfer_to_agent("pru_master_orchestrator")` immediately
- Root agent instruction updated to explicitly state it handles what sub-agents pass back

### Changes
- `rag_agent.py`: removed `flag_violation`, `report_violation_to_root`, `track_frustration` from tools
- `rag_agent_instruction.md`: full rewrite — explicit "RETURN TO ROOT" section for all out-of-scope cases; language section: unsupported → transfer to root
- `booking_agent.py`: removed `record_unrecognized_intent`, `track_frustration` from tools
- `booking_agent_instruction.md`: full rewrite — same "RETURN TO ROOT" pattern
- `escalation_agent_instruction.md`: violations/baby talk → transfer to root; unsupported language → transfer to root
- `instruction.md` (root): added explicit ownership note; fixed stale `violation_count >= 2` → `>= 3`

### Status
✓ Fixed

---

## BUG 9 — Sub-agent LLM still responds to baby talk before transferring to root

### Location
`agents/rag_agent_instruction.md`
`agents/booking_agent_instruction.md`

### Description
After Bug 8 fix, sub-agents had a "RETURN TO ROOT" section but violation detection was buried after the main workflow steps. The RAG agent workflow said:

> Step 1: Is the query obviously unrelated to health insurance?
> Step 2: Query the corpus...

Baby talk like "weww weww tell me about claims" is **not obviously unrelated** — it mentions a Prudential topic. So the LLM passes Step 1, calls `query_corpus`, gets a result, and **mirrors the user's baby-talk style in its answer**. Transfer to root happens only after the response, which is already wrong.

Root cause: violation check was not the **first** thing the LLM evaluated. The step ordering allowed the LLM to process the message content before checking the communication style.

### Solution
- Added **Step 0 (violation/style check)** as the very first step in sub-agent workflows
- Includes a concrete examples table pulled from `config/policy_config.json` (`style_disallowed`, `prompt_injection`, `policy_violation` categories) so the LLM can classify using real examples, not abstract rules
- No hardcoded regex/keywords in callbacks — LLM does the classification using the examples as reference
- If any violation category matches → `transfer_to_agent("pru_master_orchestrator")` **before** any corpus query or action

### Changes
- `rag_agent_instruction.md`: added Step 1 violation table (with examples from `policy_config.json`); renumbered Steps 2–6
- `booking_agent_instruction.md`: same Step 1 violation table; renumbered Steps 2–7

### Status
✓ Fixed

---

## BUG 10 — Root agent skips `flag_violation` for `style_disallowed` — responds in baby style instead

### Location
`agents/instruction.md` — WORKFLOW
`tools/policy_tools/policy_tools.py` — `flag_violation` docstring

### Description
After Bug 9 fix, sub-agents correctly call `transfer_to_agent("pru_master_orchestrator")` for baby talk. Confirmed in event log:

```
author: "rag_agent"
transferToAgent: "pru_master_orchestrator"   ← sub-agent transferred correctly
timestamp: 1772688349

author: "pru_master_orchestrator"
functionCall: response_tone_guideline("foundation")  ← root skipped flag_violation
timestamp: 1772688372
→ responded in baby style
```

Root agent received the baby-talk message, skipped `flag_violation`, and fell through to the greeting path (`response_tone_guideline("foundation")`) — then responded in baby style.

### Root Cause
Three compounding issues:

1. **Violation check was conditional and narrow** — Step 4 said "IF abusive, sexual, or jailbreak → call `flag_violation`". Baby talk / disallowed style doesn't match "abusive, sexual, or jailbreak" in the LLM's classification, so the step was skipped entirely.

2. **Greeting path fired instead** — After skipping Step 4, the LLM reached Step 6 "Greeting or in-scope chat → call `response_tone_guideline("foundation")`". Baby talk was classified as casual/greeting, so it called tone guideline and responded in baby style.

3. **`flag_violation` docstring too vague** — The tool docstring said "Call this when the user's message violates the intended purpose." No examples. The LLM didn't associate baby-talk style requests with "violation", so it never triggered it.

### Solution
- Made violation check **unconditional (Step 3, before language check and routing)** — with explicit instruction: "ALWAYS run this before routing. Do NOT skip this step."
- Added full examples table for all violation categories (disallowed style, jailbreak, inappropriate) directly in the workflow step
- Added explicit rule: after `flag_violation`, use the `message` from the result as reply — do NOT route to any sub-agent
- Rewrote `flag_violation` docstring with concrete triggering examples so the LLM recognises baby talk, gibberish, and style manipulation as valid triggers

### Changes
- `instruction.md`: replaced conditional Step 4 with unconditional Step 3 violation table; moved language check to Step 4; renumbered all steps; removed separate transfer-back step (no longer needed — violation check now fires first regardless)
- `tools/policy_tools/policy_tools.py`: rewrote `flag_violation` docstring with explicit trigger examples for all categories

### Status
✓ Fixed — confirmed working

---

### Theory Note (for future reference)

**Why does this class of bug happen in LLM-based multi-agent systems?**

#### 1. LLM workflow steps are not code — they are soft suggestions
In a traditional system, `if violation: flag()` is guaranteed to run. In an LLM prompt, the same instruction is a *suggestion*. If the LLM classifies the input into a different category first (e.g. "greeting"), it never re-evaluates it as a violation. **Step ordering in LLM instructions is not execution order — it is priority signalling.** The LLM picks the path that best fits its classification of the input, not necessarily the first matching step.

**Fix principle:** Put the most critical check first, make it unconditional ("ALWAYS run this, do NOT skip"), and don't rely on the LLM to self-select the right branch.

#### 2. Tool docstrings are part of the prompt
The LLM decides *when* to call a tool based on its name, description, and docstring — not just the instruction. `flag_violation` had a vague docstring ("Call this when the user's message violates the intended purpose") with no examples. Baby talk does not feel like a "violation" semantically, so the LLM never triggered it. Adding concrete examples to the docstring ("talk like a baby", "uwu", "weww weww") gave the LLM the semantic anchor it needed.

**Fix principle:** Tool docstrings must include concrete triggering examples, especially for tools that handle edge-case or non-obvious inputs. The LLM uses the docstring as a classification guide.

#### 3. Sub-agent transfer-back loses intent context
When a sub-agent calls `transfer_to_agent("root")`, ADK transfers control back but the root agent only sees the original user message — not *why* the sub-agent transferred. The root agent has no automatic signal saying "a sub-agent rejected this message". So it re-evaluates the message from scratch, and may route it to the same sub-agent again (infinite loop risk), or misclassify it as a greeting.

**Fix principle:** The root agent's violation check must be comprehensive enough to catch the message independently — it cannot rely on sub-agent context. The root is the last line of defence; it must self-classify every message before routing.

#### 4. "Greeting" is a greedy LLM classification
Baby talk, gibberish, and casual style messages all superficially resemble greetings or casual conversation. The LLM will default to the "greeting" path if it doesn't have a stronger signal telling it otherwise. This is why the greeting path fired (`response_tone_guideline("foundation")`) even though the intent was clearly a style violation.

**Fix principle:** Any disallowed input category must be checked and handled *before* the greeting/routing path. Never let a catch-all path (greeting, general response) run before safety checks complete.

---

## BUG 11 — `detect_language` called 3 times when sub-agent transfers back with unsupported language

### Location
`agents/instruction.md` — WORKFLOW Step 4, LANGUAGE & TONE section

### Description
When a user writes in an unsupported language while in a sub-agent (e.g. RAG agent), the sub-agent correctly transfers back to root. However, `detect_language` was being called 3 times in a single interaction.

### Root Cause
Three separate triggers existed for the same tool call:

1. **Transfer-back turn** — root receives the unsupported language message from the sub-agent handoff and hits Step 4 → calls `detect_language` (call 1)
2. **Step 4 fires again on root's response turn** — same message re-evaluated → calls `detect_language` again (call 2)
3. **LANGUAGE & TONE section** — contained a separate independent rule: "If language switches mid-conversation, call `detect_language(language)` to update state" — the LLM treated this as an additional active trigger and called it a third time (call 3)

This is the same class of bug as Bug 10: **two instruction sections both describe the same action with no guard against double-firing.** The LLM reads both as active rules and executes both.

### Solution
- Added "ONCE only" guard to Step 4: "call `detect_language` ONCE only per turn"
- Added explicit STOP after unsupported language handling: "reply in English, then STOP. Do not route further."
- Removed the duplicate trigger from LANGUAGE & TONE section — replaced with "Language switching is handled in Step 4 — do NOT call `detect_language` again here"

### Changes
- `instruction.md` Step 4: added "ONCE only" constraint and explicit STOP for unsupported language
- `instruction.md` LANGUAGE & TONE: removed `detect_language` call instruction, replaced with pointer to Step 4

### Theory Note
**Duplicate instruction sections are a silent bug in LLM prompts.** Unlike code where a function called twice is obvious, in a prompt two sections describing the same action are both active simultaneously. The LLM doesn't deduplicate — it executes both. Any tool that should only fire once per turn needs an explicit "ONCE only" or "do NOT call again" guard, especially when the same action is described in multiple sections (workflow steps vs. general rules vs. language sections).

### Status
✓ Fixed — pending retest

---

## Summary Table

| # | Bug | File(s) | Severity | Fix Type | Status |
|---|---|---|---|---|---|
| 1 | Callback auto-forces escalation on any no-tool response | `callback.py` | High | Remove forced LlmResponse override | ✓ Fixed |
| 2 | Violation count bleeds into unrecognized intent count | `policy_tools.py`, `callback.py` | High | Separate `violation_count` key | ✓ Fixed |
| 3 | Counter starts at 2 on first chat (double-counting) | `callback.py`, `policy_tools.py` | High | Single authoritative counter — callback only | ✓ Fixed |
| 4 | Unsupported language triggers escalation | `callback.py`, `instruction.md` | Medium | `detect_language` in disallowed_tools + instruction rule | ✓ Fixed |
| 5 | Agent prompts unstructured and inconsistent | All `*_instruction.md` files | Medium | Restructure with consistent schema | ✓ Fixed |
| 6 | Corpus miss triggers unnecessary escalation to human | `rag_agent_instruction.md` | High | Remove auto-escalate on corpus miss | ✓ Fixed |
| 7 | `escalate_to_human` duplicates `escalate_to_live_agent`, bypasses escalation agent | `escalation_tools.py`, `rag_agent.py`, `rag_agent_instruction.md` | High | Remove duplicate tool, RAG agent returns to root for escalation | ✓ Fixed |
| 8 | Sub-agents handle violations/language/out-of-scope themselves — no consistent enforcement | `rag_agent`, `booking_agent`, `escalation_agent` instruction + `.py` files | High | Strip safety tools from sub-agents; root agent owns all enforcement | ✓ Fixed |
| 9 | Sub-agent LLM responds to baby talk before transferring — violation check too late in workflow | `rag_agent_instruction.md`, `booking_agent_instruction.md` | High | Add Step 1 violation table with config examples before any corpus/action step | ✓ Fixed |
| 10 | Root agent doesn't recognise `style_disallowed` as a violation — re-routes to sub-agent instead of calling `flag_violation` | `instruction.md` | High | Expand Step 4 violation check with `style_disallowed` examples; add transfer-back awareness rule | ✓ Fixed |
| 11 | `detect_language` called 3 times on unsupported language from sub-agent | `instruction.md` | Medium | Remove duplicate trigger in LANGUAGE & TONE section; add "ONCE only" guard to Step 4 | ✓ Fixed |

---

## Fix Order

1. **Bug 3 first** — establish single counter authority (callback only). This is the foundation. ✓
2. **Bug 1** — remove forced override from callback. Depends on Bug 3 fix. ✓
3. **Bug 2** — separate violation counter. Independent, can be done in parallel with 1. ✓
4. **Bug 4** — add `detect_language` to disallowed_tools. Small change, depends on Bug 1. ✓
5. **Bug 5** — restructure all instruction files. Independent but should reflect correct tool lists from Bugs 1-4. ✓
6. **Bug 6** — fix RAG agent corpus miss path. Prompt-only fix, independent. ✓
7. **Bug 7** — remove duplicate `escalate_to_human` tool, enforce escalation through `escalation_agent` only. ✓
8. **Bug 8** — strip safety tools from sub-agents; root agent is sole enforcement layer. ✓
