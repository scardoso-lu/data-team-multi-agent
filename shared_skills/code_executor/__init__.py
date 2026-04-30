import subprocess
from pathlib import Path


def _contains_traversal(value):
    text = str(value)
    return "../" in text or "..\\" in text


class CodeExecutor:
    """Runs commands inside an allowed working directory."""

    def __init__(self, allowed_cwd, timeout_seconds=30):
        self.allowed_cwd = Path(allowed_cwd).resolve()
        self.timeout_seconds = timeout_seconds

    def _resolve_cwd(self, cwd=None):
        target = (self.allowed_cwd / cwd).resolve() if cwd else self.allowed_cwd
        if target != self.allowed_cwd and self.allowed_cwd not in target.parents:
            raise ValueError("cwd escapes executor sandbox")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def run(self, args, cwd=None, input_text=None):
        if not isinstance(args, list) or not args:
            raise ValueError("args must be a non-empty list")
        if any(_contains_traversal(arg) for arg in args):
            raise ValueError("path traversal detected in command")
        completed = subprocess.run(
            [str(arg) for arg in args],
            cwd=self._resolve_cwd(cwd),
            input=input_text,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def run_python(self, code, cwd=None):
        return self.run(["python", "-c", code], cwd=cwd)

    def run_shell(self, command, cwd=None):
        return self.run(["bash", "-lc", command], cwd=cwd)
