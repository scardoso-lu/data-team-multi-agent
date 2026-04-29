import importlib.util
import os
import sys
from pathlib import Path


class SkillLoader:
    """Load shared skill modules from the repository or SHARED_SKILLS_DIR."""

    def __init__(self, skills_dir=None):
        self.skills_dir = str(skills_dir or self._default_skills_dir())
        self.skills = {}

    def _default_skills_dir(self):
        candidates = [
            os.getenv("SHARED_SKILLS_DIR"),
            Path(__file__).resolve().parents[1] / "shared_skills",
            Path.cwd() / "shared_skills",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.is_dir():
                return path
        raise FileNotFoundError("No shared_skills directory found.")

    def load_skill(self, skill_name):
        skill_path = Path(self.skills_dir) / skill_name
        init_file = skill_path / "__init__.py"

        if not init_file.exists():
            raise FileNotFoundError(f"Skill {skill_name} not found in {self.skills_dir}")

        module_name = skill_name
        if module_name in sys.modules:
            del sys.modules[module_name]

        spec = importlib.util.spec_from_file_location(module_name, init_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        self.skills[skill_name] = module
        return module

    def get_skill(self, skill_name):
        if skill_name not in self.skills:
            return self.load_skill(skill_name)
        return self.skills[skill_name]
