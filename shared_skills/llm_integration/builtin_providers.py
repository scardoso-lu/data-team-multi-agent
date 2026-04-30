import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandProvider:
    name: str
    args: tuple[str, ...]

    def complete(self, prompt, timeout_seconds):
        if shutil.which(self.args[0]) is None:
            return None
        rendered = []
        prompt_as_arg = False
        for arg in self.args:
            if arg == "{prompt}":
                rendered.append(prompt)
                prompt_as_arg = True
            else:
                rendered.append(arg)
        completed = subprocess.run(
            rendered,
            input=None if prompt_as_arg else prompt,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip()
        return None


def default_providers():
    return [
        CommandProvider("codex", ("codex", "exec", "--skip-git-repo-check", "-")),
        CommandProvider("codex", ("codex", "exec", "-")),
        CommandProvider("claude", ("claude", "-p", "{prompt}")),
        CommandProvider("claude", ("claude-code", "-p", "{prompt}")),
        CommandProvider("mistral", ("mistral-vibe", "run", "--prompt", "{prompt}")),
        CommandProvider("mistral", ("mistral", "chat", "--message", "{prompt}")),
    ]
