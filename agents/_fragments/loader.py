"""
Fragment loader for agent instructions.

Usage:
    from agents._fragments.loader import load_instruction

    instruction = load_instruction("root_agent")   # loads _fragments/root_agent.md
                                                   # and resolves all {{ fragment_name }} tokens
"""

import re
from pathlib import Path

_FRAGMENTS_DIR = Path(__file__).parent


def _load_raw(filename: str) -> str:
    """Read a .md file from the _fragments directory."""
    path = _FRAGMENTS_DIR / f"{filename}.md"
    return path.read_text(encoding="utf-8")


def load_instruction(agent_name: str) -> str:
    """
    Load an agent instruction file and resolve all {{ fragment_name }} tokens
    with the content of the matching shared_*.md fragment file.

    Args:
        agent_name: filename without extension, e.g. "root_agent", "rag_agent"

    Returns:
        Fully resolved instruction string ready to pass to Agent(instruction=...)
    """
    template = _load_raw(agent_name)
    return _resolve(template)


def _resolve(template: str) -> str:
    """Replace every {{ fragment_name }} token with the file content of that fragment."""
    def replacer(match: re.Match) -> str:
        fragment_name = match.group(1).strip()
        try:
            return _load_raw(fragment_name)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Fragment '{{ {fragment_name} }}' referenced in template "
                f"but '{fragment_name}.md' was not found in {_FRAGMENTS_DIR}"
            )

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replacer, template)
