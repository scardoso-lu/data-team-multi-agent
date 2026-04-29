"""Agent package entry points and local import bootstrap."""

import sys
from pathlib import Path


SHARED_SKILLS_DIR = Path(__file__).resolve().parents[1] / "shared_skills"
if str(SHARED_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SKILLS_DIR))
