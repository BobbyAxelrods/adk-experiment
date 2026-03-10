"""
Fragment loader for agent instructions.

All fragments and resolved agent instructions are loaded once at module import time
and cached in memory. Subsequent calls to load_instruction() are pure dict lookups —
no disk I/O, no regex on every request.

Usage:
    from agents._fragments.loader import load_instruction

    instruction = load_instruction("root_agent")
"""

import re
from pathlib import Path

_FRAGMENTS_DIR = Path(__file__).parent

# ── 1. Load all .md files from _fragments/ into memory at import time ──────────
_FILE_CACHE: dict[str, str] = {
    path.stem: path.read_text(encoding="utf-8")
    for path in _FRAGMENTS_DIR.glob("*.md")
}

# ── 2. Resolve {{ token }} references ─────────────────────────────────────────
_TOKEN_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _resolve(template: str) -> str:
    def replacer(match: re.Match) -> str:
        name = match.group(1).strip()
        if name not in _FILE_CACHE:
            raise KeyError(
                f"Fragment '{{{{ {name} }}}}' not found. "
                f"Available: {sorted(_FILE_CACHE.keys())}"
            )
        return _FILE_CACHE[name]

    return _TOKEN_RE.sub(replacer, template)


# ── 3. Resolve every agent instruction at import time and cache the result ─────
_AGENT_NAMES = [
    "root_agent",
    "rag_agent",
    "booking_agent",
    "policy_agent",
    "escalation_agent",
    "vas_agent",
    "policy_mcp_agent",
    "evaluation_agent",
]

_INSTRUCTION_CACHE: dict[str, str] = {}

for _name in _AGENT_NAMES:
    if _name not in _FILE_CACHE:
        raise FileNotFoundError(
            f"Agent instruction file '{_name}.md' not found in {_FRAGMENTS_DIR}"
        )
    _INSTRUCTION_CACHE[_name] = _resolve(_FILE_CACHE[_name])


# ── 4. Public API ──────────────────────────────────────────────────────────────
def load_instruction(agent_name: str) -> str:
    """
    Return the fully resolved instruction string for the given agent.
    Result is served from in-memory cache — no disk I/O at call time.

    Args:
        agent_name: e.g. "root_agent", "rag_agent", "booking_agent"

    Returns:
        Fully resolved instruction string ready to pass to Agent(instruction=...)
    """
    if agent_name not in _INSTRUCTION_CACHE:
        raise KeyError(
            f"No instruction found for '{agent_name}'. "
            f"Available agents: {sorted(_INSTRUCTION_CACHE.keys())}"
        )
    return _INSTRUCTION_CACHE[agent_name]
