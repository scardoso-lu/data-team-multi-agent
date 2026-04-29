from shared_skills.ado_integration import ADOIntegration


def test_ado_integration_uses_config_and_environment_overrides(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "pat")
    monkeypatch.setenv("ADO_ORGANIZATION_URL", "https://example.invalid/org")
    monkeypatch.setenv("ADO_PROJECT_NAME", "ExampleProject")

    ado = ADOIntegration()

    assert ado.ado_pat == "pat"
    assert ado.organization_url == "https://example.invalid/org"
    assert ado.project_name == "ExampleProject"
