import re
from pathlib import Path

_FRAGMENTS_DIR = Path(__file__).parent

def _load_main(filename:str) -> str:
    path = f"{filename}.md"
    return path.read_text(encoding="utf-8")

def load_main_instructions(file_name):
    template = _load_main(file_name)
    return _fragment(template)

def _fragment(template: str) -> str:
    """
    Replace token of the {{fragment_name}} with fragment content
    Build a lookup table : read every **md file in fragment dir and store its text by file stem name 
    Normalized and uppercase 
    Match token name in template using regex to capture gragment name 
    each regex match take captured name normalize it  

    Case insensitive and match against markdown files in FRAGMENT_DIR (filename stem -> contents ) 
    """
    fragments:Dict[str, str] = {}
    if _FRAGMENTS_DIR.exists():
        for p in _FRAGMENTS_DIR.glob("*.md"):
            fragments[p.stem.upper()] = p.read_text(encoding="utf-8")

    pattern = re.compile(r"{{\s*([^}]+)\s*}}")

    def _repl(match:re.Match) -> str:
        key = match.group(1).strip().upper()
        return fragments.get(key, "")

    return pattern.sub(_repl,template)
