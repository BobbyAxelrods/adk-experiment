# _fragments — Centralized Agent Instruction Fragments

This folder is the single source of truth for all shared agent instruction content.
Edit here → changes apply to every agent that uses the fragment.

---

## Fragment Files (shared across all agents)

| File | Controls |
|---|---|
| `shared_identity.md` | Who we are — "Pru Health Team", never identify as AI/Gemini/GPT |
| `shared_violation_check.md` | 3-category violation table + action (flag → transfer to root) |
| `shared_peace_of_mind_formula.md` | Empathise → Guide → Reassure + sentence rules + jargon blacklist |
| `shared_language_rules.md` | Supported languages, respond in user's language, unsupported → root |
| `shared_escalation_rules.md` | Human request, frustration, violation_count, escalation_recommended |
| `shared_return_to_root.md` | When and how to transfer_to_agent("pru_master_orchestrator") |

---

## Agent Instruction Files (composed = shared fragments + agent-specific logic)

| File | Agent | What's unique |
|---|---|---|
| `root_agent.md` | pru_master_orchestrator | Routing table, 6-step orchestration workflow, detect_language |
| `rag_agent.md` | rag_agent | Corpus query flow, citation format (📄 Source), policy_mcp_agent routing |
| `booking_agent.md` | booking_agent | 8-step booking flow, provider search, availability, book_appointment |
| `policy_agent.md` | policy_agent | General vs personal policy intent split, policy_mcp_tool usage |
| `escalation_agent.md` | escalation_agent | 7-step de-escalation, tone group selection (speciality_care first) |
| `vas_agent.md` | vas_agent | VAS-specific corpus query, citation format |
| `policy_mcp_agent.md` | policy_mcp_agent | Authentication gate, MCP tool steps |

---

## How to use fragments in code

```python
# agents/_fragments/loader.py (to be created)
from pathlib import Path

_dir = Path(__file__).parent

def fragment(name: str) -> str:
    return (_dir / f"{name}.md").read_text(encoding="utf-8")

# Usage in any agent file:
from agents._fragments.loader import fragment

instruction = f"""
{fragment("shared_identity")}

## SCOPE
[agent-specific scope]

## WORKFLOW
{fragment("shared_violation_check")}
[agent-specific steps]

{fragment("shared_peace_of_mind_formula")}
{fragment("shared_language_rules")}
{fragment("shared_escalation_rules")}
{fragment("shared_return_to_root")}
"""
```

---

## Known Inconsistencies Fixed Here

| Issue | Fix Applied |
|---|---|
| Language list mismatch (policy_agent had Bahasa/Traditional Chinese, others had Malay) | Standardised to EN/Malay/Cantonese in all agents. See note in `policy_agent.md` |
| Violation table had 3 rows in some, 4 rows in others (Style manipulation was separate) | Merged into 3 canonical categories in `shared_violation_check.md` |
| IDENTITY was at bottom in VAS and Policy agents | Moved to top in all agent files |
| Jargon blacklist missing in RAG, Policy, VAS, Escalation agents | Now in `shared_peace_of_mind_formula.md`, applied to all |
| Section header style inconsistent (## 1., ### Step N —, ### Step N:) | Standardised to `### Step N —` across all agent-specific files |
