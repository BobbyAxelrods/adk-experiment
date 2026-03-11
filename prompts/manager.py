import os
from typing import Dict, Optional

class PromptManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.base_dir = os.path.dirname(__file__)
        self.fragments_dir = os.path.join(self.base_dir, "fragments")
        self.templates_dir = os.path.join(self.base_dir, "templates")
        self.tone_group_dir = os.path.join(os.path.dirname(self.base_dir), "tone_group")

        self._fragments: Dict[str, str] = {}
        self._templates: Dict[str, str] = {}
        self._tone_groups: Dict[str, str] = {}
        self._cache: Dict[str, str] = {}

        self.load_all()
        self._initialized = True

    def load_all(self):
        """Pre-load all fragments, templates, and tone group files into memory."""
        # Load fragments
        if os.path.exists(self.fragments_dir):
            for filename in os.listdir(self.fragments_dir):
                if filename.endswith(".md"):
                    name = filename[:-3]
                    with open(os.path.join(self.fragments_dir, filename), "r", encoding="utf-8") as f:
                        self._fragments[name.upper()] = f.read()

        # Load templates
        if os.path.exists(self.templates_dir):
            for filename in os.listdir(self.templates_dir):
                if filename.endswith(".md"):
                    name = filename[:-3]
                    with open(os.path.join(self.templates_dir, filename), "r", encoding="utf-8") as f:
                        self._templates[name] = f.read()

        # Load tone groups (keyed by filename stem matching ToneCategory enum values, e.g. "system_general", "fallback")
        if os.path.exists(self.tone_group_dir):
            for filename in os.listdir(self.tone_group_dir):
                if filename.endswith(".md"):
                    name = filename[:-3]
                    with open(os.path.join(self.tone_group_dir, filename), "r", encoding="utf-8") as f:
                        self._tone_groups[name] = f.read()

    def get_tone_group(self, filename_stem: str) -> str:
        """Return pre-loaded tone group content by filename stem (e.g. 'fallback', 'foundation')."""
        return self._tone_groups.get(filename_stem, "")

    def get_instruction(self, template_name: str, **kwargs) -> str:
        """
        Get composed instruction for an agent.
        1. Injects fragments via {{FRAGMENT_NAME}}.
        2. Preserves ADK/LLM placeholders like {user_name?}.
        3. Optionally replaces passed kwargs if explicitly found as {{key}}.
        """
        if template_name in self._cache and not kwargs:
            return self._cache[template_name]

        template = self._templates.get(template_name)
        if not template:
            return f"Template {template_name} not found"

        # 1. Inject Fragments (Static) - and keep it as a string
        composed = template
        for name, content in self._fragments.items():
            placeholder = f"{{{{{name}}}}}"
            if placeholder in composed:
                composed = composed.replace(placeholder, content)

        # 2. Inject Dynamic Values (Safe)
        # We avoid .format() because ADK uses {var?} placeholders which 
        # python's .format() treats as a KeyError. 
        # Instead, we only replace if the user explicitly passes kwargs 
        # that match a double-bracket pattern or we just let ADK handle them later.
        for key, value in kwargs.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in composed:
                composed = composed.replace(placeholder, str(value))

        if not kwargs:
            self._cache[template_name] = composed

        return composed

# Global instance
prompt_manager = PromptManager()
