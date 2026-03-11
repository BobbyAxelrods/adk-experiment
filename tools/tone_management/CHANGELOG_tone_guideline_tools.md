# Changelog — tone_guideline_tools.py

---

## [v6] 2026-03-11 — Wire to Agents, Expose as FunctionTool
**Files:** `tone_guideline_tools_v2.py`, `agents/agent.py`, `agents/booking_agent.py`, `agents/escalation_agent.py`, `agents/policy_agent.py`, `agents/rag_agent.py`, `agents/vas_agent.py`

### Changed (`tone_guideline_tools_v2.py`)
- Added `FunctionTool` import from `google.adk.tools`
- Internal function renamed to `_get_tone_guideline` (private)
- `get_tone_guideline = FunctionTool(func=_get_tone_guideline)` — exposed as ADK-compatible tool, same pattern as old `tone_guideline_tools.py`

### Changed (all agents)
- Swapped import: `tone_guideline_tools.response_tone_guideline` → `tone_guideline_tools_v2.get_tone_guideline` across all 5 agents
- Tool reference updated in each agent's tools list accordingly
- Stale comment referencing `response_tone_guideline` removed from `rag_agent.py`

---

## [v5] 2026-03-11 — Remove Redundant Mappings
**File:** `tone_guideline_tools_v2.py`

### Removed
- `_FILE_STEM` dict — was mapping 7 categories, 4 of which were identical to their enum value; redundant
- `_STRING_ALIASES` dict — loose string resolution is not needed when tone comes from state as a `ToneCategory` enum
- String fallback path in `get_tone_guideline()` — signature tightened to `ToneCategory` only

### Added
- `_STEM_OVERRIDES` — replaces both dicts; only holds the 3 categories where the file stem differs from the enum value (`SYSTEM_GENERAL→foundation`, `HEALTH_ASSURANCE→health_reassurance`, `SPECIALITY_CARE→special_care`)

### Changed
- Stem resolution: `_STEM_OVERRIDES.get(category, category.value)` — enum value is the default, override only when needed

---

## [v4] 2026-03-11 — Direct State Read, No Assembler
**File:** `tone_guideline_tools_v2.py`

### Removed
- `TONE_DESCRIPTIONS` dict — descriptions were header overhead; tone is already known from state, no need to re-describe it in the output
- `_resolve()` helper function — inlined directly into `get_tone_guideline()`; wasn't complex enough to warrant its own function
- All output formatting/assembly logic (headers, `parts` list, section labels) — pure content is sufficient

### Changed
- `response_tone_guideline()` renamed to `get_tone_guideline()` — name reflects what it actually does
- Return value is now raw content only: `foundation + specific` joined with a blank line, or just `foundation` if category maps to it — no wrapping markup

---

## [v3] 2026-03-11 — In-Memory Load & State Injection
**Files:** `tone_guideline_tools_v2.py`, `prompts/manager.py`

### Removed
- `import os` from `tone_guideline_tools_v2.py` — no file I/O remains in this file
- `_load_tone_file()` function — replaced entirely by `prompt_manager.get_tone_group()`
- `.md` extensions from file references — `_FILE_MAP` renamed to `_FILE_STEM`, values are now bare stems (`"fallback"`, `"foundation"`) not filenames

### Added (`tone_guideline_tools_v2.py`)
- Imports `prompt_manager` from `prompts.manager` — all content now served from in-memory store
- `_FILE_STEM` dict — replaces `_FILE_MAP`; maps each `ToneCategory` to a filename stem for `get_tone_group()` lookup

### Added (`prompts/manager.py`)
- `self.tone_group_dir` — path to `../tone_group/` resolved at init
- `self._tone_groups: Dict[str, str]` — in-memory store for all tone group markdown files
- `load_all()` extended — walks `tone_group/` on startup and loads all `.md` files keyed by stem
- `get_tone_group(filename_stem)` — O(1) dict lookup; returns empty string if stem not found

### Changed
- `response_tone_guideline()` is now a pure string assembler — resolve category → O(1) memory lookup → string join; zero disk reads at call time
- Output header shortened: `## RESPONSE TONE GUIDELINES: X` → `## TONE: X` (token reduction)
- Output section headers shortened: `### FOUNDATION GUIDELINES` → `### FOUNDATION`, `### X GUIDELINES` → `### X`
- Removed `import re` from `manager.py` — was unused

### Architecture
- Tone group is now resolved **upstream** before calling `response_tone_guideline()` (state injection pattern)
- Call-time cost: dict lookup (O1) + string join only — no I/O, no parsing

---

## [v2] 2026-03-11 — Simplification & Restructure
**File:** `tone_guideline_tools_v2.py`

### Removed
- `user_mood` parameter from `response_tone_guideline()` — mood detection is no longer part of the tone selection logic
- `PEACE_OF_MIND_FORMULA` constant — already defined in `foundation.md`; removed duplication
- Hardcoded "CORE RULES" section in the output string — same reason, lives in `foundation.md`
- `_resolve_tone_file()` function — replaced by a cleaner split into `_resolve_category()` + `_FILE_MAP`
- `Optional` import — no longer needed after removing `user_mood`
- Inline `if/elif` chain for string matching inside the resolver — replaced by a flat dict lookup

### Added
- `TONE_DESCRIPTIONS` dict — one-line situational description per tone group, derived from each group's trigger scenarios; injected into the guideline output as "When to use"
- `_STRING_ALIASES` dict — flat mapping of all known string variants to their `ToneCategory` enum, replaces fragile `if/elif` substring matching
- `_FILE_MAP` dict — explicit enum-to-filename mapping, previously mixed into `TONE_GROUP_FILE_MAP` with a string key duplicate (`"foundation"`)

### Changed
- `response_tone_guideline(tone_category, user_mood)` → `response_tone_guideline(tone_category)` — signature simplified, mood param dropped
- `_resolve_tone_file()` split into two focused functions:
  - `_resolve_category()` — normalises string or enum input to a `ToneCategory`
  - `_load_tone_file()` — loads a markdown file by filename (replaces `_load_tone_markdown()`, same logic)
- `TONE_GROUP_FILE_MAP` renamed to `_FILE_MAP` and made private; removed the redundant `"foundation"` string key
- Output format simplified: header + "When to use" description → foundation guidelines → category-specific guidelines (no numbered sections, no mood block)

### Not changed
- `ToneCategory` enum values — identical to v1
- File resolution logic for `SYSTEM_GENERAL` still maps to `foundation.md` and skips loading specific guidelines

---

## [v1] — Original
**File:** `tone_guideline_tools.py`

Initial implementation. Supported `user_mood` parameter, inlined PEACE_OF_MIND_FORMULA and core rules into output, used `if/elif` string resolver.
