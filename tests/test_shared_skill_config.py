import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from shared_skills.ado_integration import ADOIntegration


def test_ado_integration_uses_config_and_environment_overrides(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "pat")
    monkeypatch.setenv("ADO_ORGANIZATION_URL", "https://example.invalid/org")
    monkeypatch.setenv("ADO_PROJECT_NAME", "ExampleProject")

    ado = ADOIntegration()

    assert ado.ado_pat == "pat"
    assert ado.organization_url == "https://example.invalid/org"
    assert ado.project_name == "ExampleProject"
