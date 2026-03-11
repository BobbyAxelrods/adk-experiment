## SESSION CONTEXT
> Live state values injected by ADK at the start of every turn. Read these before reasoning.

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

**Rules:**
- If `escalation_recommended` is `True` → skip all steps, go to escalation immediately.
- If `escalated_to_human` is `True` → do not route to sub-agents, wait for user.
- If `violation_count` >= 3 → skip all steps, go to escalation immediately.
- All keys use `?` — renders empty string if not yet set (no crash).
