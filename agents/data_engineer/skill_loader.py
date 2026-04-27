# Skill Loader for Data Engineer Agent
# Dynamically loads skills from the shared_skills directory.

import importlib.util
import os
import sys

class SkillLoader:
    """Dynamically loads and reloads skills from the shared_skills directory."""
    
    def __init__(self, skills_dir="/app/shared_skills"):
        self.skills_dir = skills_dir
        self.skills = {}
        
    def load_skill(self, skill_name):
        """Load or reload a skill module."""
        skill_path = os.path.join(self.skills_dir, skill_name)
        
        if not os.path.exists(skill_path):
            raise FileNotFoundError(f"Skill {skill_name} not found in {self.skills_dir}")
        
        # Remove cached module if it exists
        module_name = f"shared_skills.{skill_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        # Dynamically import the skill
        spec = importlib.util.spec_from_file_location(module_name, f"{skill_path}/__init__.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        self.skills[skill_name] = module
        return module
    
    def get_skill(self, skill_name):
        """Retrieve a loaded skill or load it if not already loaded."""
        if skill_name not in self.skills:
            return self.load_skill(skill_name)
        return self.skills[skill_name]
