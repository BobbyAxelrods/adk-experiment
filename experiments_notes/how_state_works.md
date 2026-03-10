# How State Works in Google ADK — And How Agents Actually Understand It

---

## The Core Question

> "If we define state like `frustration_count: 0`, how does the agent know what
> to do with it? Is it from the function docstring? Or the key name itself?"

**Short answer: Neither alone. It's the combination of 3 things:**

1. **Function docstring** — tells the LLM *when* to call the tool
2. **Instruction (prompt)** — tells the LLM *what state keys mean* and *what to do when they change*
3. **Tool return value** — tells the LLM *what happened* so it can decide the next action

State keys sitting silently in `session.state` mean **nothing** to the agent
unless they are surfaced via one of the mechanisms below.

---

## How ADK Wires Everything Together

```
┌─────────────────────────────────────────────────────┐
│                   ADK Runner                        │
│                                                     │
│  1. Builds the LLM prompt from:                     │
│     - agent.instruction (your .md, with {key}       │
│       template vars already substituted)            │
│     - conversation history (prior turns)            │
│     - tool schemas (from FunctionTool docstrings)   │
│                                                     │
│  2. LLM generates a response:                       │
│     - text reply, OR                                │
│     - function_call (tool name + args)              │
│                                                     │
│  3. ADK executes the tool                           │
│     - tool reads/writes tool_context.state          │
│     - tool returns a dict                           │
│                                                     │
│  4. ADK feeds tool result back to LLM               │
│     - LLM sees the dict and decides next action     │
│                                                     │
│  5. Callbacks fire at lifecycle hooks               │
│     - before/after model, before/after agent        │
│     - can also read/write state                     │
└─────────────────────────────────────────────────────┘
```

---

## STATE MANIPULATION — All The Ways You Can Work With State

### 1. Template Variable Injection in Instructions `{key}` ← BEST for reading

ADK automatically substitutes `{key}` in instruction strings with
`session.state["key"]` **before** sending to the LLM. This is the cleanest
way to make the agent aware of current state values at the start of every turn.

```python
# In your agent definition:
agent = Agent(
    instruction="""
    ## CURRENT SESSION CONTEXT
    - Language: {language}
    - Escalation recommended: {escalation_recommended}
    - Violation count: {violation_count}
    - Pending intents: {pending_intents?}

    Handle the user's request accordingly.
    """
)
```

**Rules:**
- `{key}` — key MUST exist in state or ADK throws an error
- `{key?}` — optional key, renders as empty string if missing
- Value must be a string or convert cleanly to string
- **Cannot use raw `{...}` for literal JSON** — use `InstructionProvider` for that

---

### 2. InstructionProvider — for dynamic or complex instructions

When your instruction needs literal curly braces (e.g. JSON examples) or
runtime-computed content, pass a **function** instead of a string:

```python
from google.adk.agents.readonly_context import ReadonlyContext

def build_instruction(context: ReadonlyContext) -> str:
    lang = context.state.get("language", "english")
    violations = context.state.get("violation_count", 0)
    return f"""
    You are a Pru Health assistant. Current language: {lang}.
    Violation count: {violations}.
    Output format example: {{"status": "ok", "result": "..."}}
    """

agent = Agent(instruction=build_instruction)
```

**When ADK sees a function as `instruction`:**
- It calls the function every turn with the current `ReadonlyContext`
- ADK skips automatic `{key}` substitution — YOU control all interpolation
- Use this when you need literal `{` in the output (JSON examples, code snippets)

**Selective injection with `inject_session_state`:**
```python
from google.adk.agents import instructions_utils

async def build_instruction(context: ReadonlyContext) -> str:
    template = "Language: {language}. Use JSON like: {\"key\": \"value\"}."
    return await instructions_utils.inject_session_state(template, context)
    # Only {language} is replaced — {"key": "value"} is left as-is
```

---

### 3. `output_key` on Agent — simplest write

Saves the agent's final text response directly to a state key automatically.
No tool needed. No callback needed.

```python
agent = Agent(
    output_key="last_agent_response"   # auto-writes to session.state
)
# After the agent responds, session.state["last_agent_response"] = "<full response text>"
```

**Use case:** Passing one agent's full response as input context to the next
agent in a sequential pipeline.

**Limitation:** Saves the full text response only — not structured data.
Not useful for writing specific flag values like `escalation_recommended`.

---

### 4. `ToolContext.state` in Tool Functions ← WHAT YOU USE NOW

The recommended way to read/write state inside tool functions.
Changes are automatically tracked by the ADK event system and persisted correctly.

```python
def track_frustration(tool_context: ToolContext) -> dict:
    # READ
    count = tool_context.state.get("frustration_count", 0) + 1
    # WRITE
    tool_context.state["frustration_count"] = count
    tool_context.state["escalation_recommended"] = count >= 3
    # RETURN — this is what the LLM sees to decide next action
    return {"frustration_count": count, "escalation_recommended": count >= 3}
```

**State scopes via key prefix:**

| Prefix | Scope | Lifetime | Use case |
|---|---|---|---|
| *(none)* | Session | Current session | Frustration count, current intent, language |
| `user:` | User | All sessions for this user | User preferences, name |
| `app:` | App-wide | All users | Global config, shared templates |
| `temp:` | Invocation | Current turn only | Inter-tool data, intermediate results |

```python
# Examples of scoped keys
tool_context.state["frustration_count"] = 2          # session scope
tool_context.state["user:preferred_language"] = "malay"  # user scope
tool_context.state["temp:policy_result"] = data       # temp: gone after this turn
```

---

### 5. `CallbackContext.state` in Callbacks

Same API as ToolContext — callbacks use `callback_context.state`:

```python
def count_unrecognized_intents(callback_context: CallbackContext, llm_response: LlmResponse):
    state = callback_context.state
    state["unrecognized_intent_count"] = state.get("unrecognized_intent_count", 0) + 1
```

---

### 6. `EventActions.state_delta` — programmatic bulk update

For writing multiple keys outside a tool/callback context (e.g. from application code):

```python
from google.adk.events import Event, EventActions

state_changes = {
    "language": "malay",
    "user:preferred_language": "malay",
    "temp:cache": intermediate_data
}
actions = EventActions(state_delta=state_changes)
event = Event(actions=actions)
await session_service.append_event(session, event)
```

**When to use:** Initializing state from external data before a session starts,
or updating state from outside the agent loop (e.g. webhook handler).

---

### 7. ❌ NEVER do this — direct session mutation

```python
# WRONG — bypasses event tracking, won't persist, causes race conditions
session = await session_service.get_session(...)
session.state["key"] = value
```

Always use `tool_context.state`, `callback_context.state`, or `EventActions.state_delta`.

---

## The 3 Mechanisms the LLM Uses to Know State

### Mechanism 1: `{key}` Template Injection → LLM sees it upfront

```markdown
## SESSION CONTEXT
Language: {language}
Escalation recommended: {escalation_recommended}
Pending intents: {pending_intents?}
```

The LLM sees the **actual values** baked into the system prompt before it
even starts reasoning. Most reliable. Zero tool call overhead.

---

### Mechanism 2: Tool Return Dict → LLM sees it after tool executes

```python
def track_frustration(tool_context: ToolContext) -> dict:
    ...
    return {
        "frustration_count": count,
        "escalation_recommended": True,
        "hint": "Frustration threshold reached. Consider calling escalation_agent."
    }
```

`tool_context.state["escalation_recommended"] = True` **alone is invisible to the LLM.**
The LLM only acts because the return dict says `escalation_recommended: True`
AND the instruction says "if escalation_recommended is True → transfer."

---

### Mechanism 3: Conversation History → LLM infers from prior turns

If a tool was called in a previous turn, the LLM has that tool response in its
history and can infer state. This is fragile for long sessions — don't rely on it.

---

## What Actually Happens Turn-by-Turn (Your System)

```
User sends: "I'm really frustrated, what does my policy cover?"
    │
    ▼
ADK builds LLM prompt:
    ├── system: root_agent.md WITH {language} → "english", {violation_count} → "0"
    │           already substituted before LLM sees it
    ├── history: [prior turns]
    ├── tools: [track_frustration schema, detect_language schema, ...]
    └── user: "I'm really frustrated, what does my policy cover?"
    │
    ▼
LLM reasons:
    "User sounds frustrated → call track_frustration()
     Also a policy question → route to rag_agent after"
    │
    ▼
LLM generates: function_call(track_frustration, args={})
    │
    ▼
ADK executes track_frustration():
    - reads  tool_context.state["frustration_count"] → 0
    - writes tool_context.state["frustration_count"] = 1
    - returns {"frustration_count": 1, "escalation_recommended": False}
    │
    ▼
ADK feeds return dict back to LLM as function_response
    │
    ▼
LLM reasons:
    "escalation_recommended=False, not at threshold yet.
     Policy question → transfer to rag_agent"
    │
    ▼
[after_model_callback: count_unrecognized_intents fires]
    │
    ▼
ADK transfers to rag_agent
```

---

## The Gap in Your Current Codebase

Your `root_agent.md` Step 1:
```markdown
Check if `user_name`, `language`, `escalation_recommended`, `violation_count` are set.
```

The LLM **cannot actually see these values** — your instructions don't use `{key}` injection yet.
The LLM can only infer them from conversation history (fragile).

**Fix — add a SESSION CONTEXT block to `root_agent.md`:**
```markdown
## SESSION CONTEXT
- Language: {language}
- Escalation recommended: {escalation_recommended}
- Violation count: {violation_count}
- Frustration count: {frustration_count}
- Pending intents: {pending_intents?}
- Current intent: {current_intent?}
```

This makes the LLM see real values at the start of every turn with zero overhead.

---

## Key Naming — Does It Matter?

**For the LLM: only clarity matters, not the name itself.**
The LLM understands `frustration_count` because:
1. The instruction says "if `frustration_count` >= 3, escalate"
2. The tool returns `{"frustration_count": 3, "hint": "Threshold reached"}`

If you named it `fc`, it would work equally well as long as both the instruction
and tool returns used `fc` consistently. Human-readable names help you write
clearer instructions, which in turn guides the LLM better.

**For the codebase: use constants from `keys.py`** — key names are strings,
typos silently create new keys instead of raising errors.

---

## Summary Table

| Mechanism | What it does | LLM sees it? | Best for |
|---|---|---|---|
| `{key}` in instruction | Injects state value into system prompt | Yes — upfront | Reading state at turn start |
| `InstructionProvider` fn | Full control over instruction string | Yes — upfront | Dynamic instructions, literal `{}` |
| `output_key` | Saves agent text response to state | No (writes only) | Passing responses between pipeline agents |
| `tool_context.state` | Read/write in tool functions | Only via return dict | All state mutations |
| `callback_context.state` | Read/write in callbacks | No (passive) | Counters, guards, resets |
| `EventActions.state_delta` | Bulk write outside agent loop | No (writes only) | Init from external data |
| Direct `session.state =` | ❌ Bypasses event system | — | NEVER |
