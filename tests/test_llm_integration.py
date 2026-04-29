import subprocess
from unittest.mock import Mock

from llm_integration import LLMCommand, LocalLLMClient, extract_json


class ConfigStub:
    def get(self, *keys, default=None):
        values = {
            ("llm", "providers"): ["claude"],
            ("llm", "timeout_seconds"): 5,
        }
        return values.get(keys, default)


def test_extract_json_from_plain_json():
    assert extract_json('{"status": "ok"}') == {"status": "ok"}


def test_extract_json_from_wrapped_output():
    text = 'Here is the result:\n{"checks": ["a", "b"]}\nDone.'
    assert extract_json(text) == {"checks": ["a", "b"]}


def test_complete_json_uses_first_available_cli(monkeypatch):
    monkeypatch.setattr("llm_integration.shutil.which", lambda executable: executable)
    run = Mock(
        return_value=subprocess.CompletedProcess(
            args=["codex"],
            returncode=0,
            stdout='{"architecture": "ready"}',
            stderr="",
        )
    )
    monkeypatch.setattr("llm_integration.subprocess.run", run)

    client = LocalLLMClient(commands=(LLMCommand("codex", ("codex", "exec", "-")),))

    assert client.complete_json("build", {"x": 1}, fallback={}) == {"architecture": "ready"}
    run.assert_called_once()
    assert run.call_args.kwargs["input"] is not None
    assert run.call_args.kwargs["check"] is False


def test_complete_json_skips_missing_cli(monkeypatch):
    def which(executable):
        return executable if executable == "claude" else None

    monkeypatch.setattr("llm_integration.shutil.which", which)
    run = Mock(
        return_value=subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout='{"provider": "claude"}',
            stderr="",
        )
    )
    monkeypatch.setattr("llm_integration.subprocess.run", run)

    client = LocalLLMClient(
        commands=(
            LLMCommand("codex", ("codex", "exec", "-")),
            LLMCommand("claude", ("claude", "-p", "{prompt}")),
        )
    )

    assert client.complete_json("build", {}, fallback={}) == {"provider": "claude"}
    assert run.call_args.args[0][0] == "claude"
    assert run.call_args.kwargs["input"] is None


def test_client_filters_configured_providers():
    client = LocalLLMClient(config=ConfigStub())

    assert {command.provider for command in client.commands} == {"claude"}
    assert client.timeout_seconds == 5


def test_complete_json_returns_fallback_when_cli_fails(monkeypatch):
    monkeypatch.setattr("llm_integration.shutil.which", lambda executable: executable)
    monkeypatch.setattr(
        "llm_integration.subprocess.run",
        Mock(
            return_value=subprocess.CompletedProcess(
                args=["codex"],
                returncode=1,
                stdout="",
                stderr="not authenticated",
            )
        ),
    )

    client = LocalLLMClient(commands=(LLMCommand("codex", ("codex", "exec", "-")),))

    assert client.complete_json("build", {}, fallback={"safe": True}) == {"safe": True}
