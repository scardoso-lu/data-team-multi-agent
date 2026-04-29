import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

for path in (
    ROOT_DIR,
    os.path.join(ROOT_DIR, "shared_skills"),
):
    if path not in sys.path:
        sys.path.insert(0, path)
