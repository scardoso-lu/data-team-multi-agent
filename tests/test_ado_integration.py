from types import SimpleNamespace
from unittest.mock import Mock

from shared_skills.ado_integration import ADOIntegration


def make_connection(work_item_client=None, wiki_client=None):
    clients = Mock()
    clients.get_work_item_tracking_client.return_value = work_item_client or Mock()
    clients.get_wiki_client.return_value = wiki_client or Mock()
    return SimpleNamespace(clients=clients)


def test_build_column_wiql_escapes_project_column_and_work_item_type(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "token")
    monkeypatch.setenv("ADO_PROJECT_NAME", "Data Team's Project")
    ado = ADOIntegration(connection=make_connection())

    wiql = ado.build_column_wiql("Architecture's Queue", ["Epic", "Feature's"])

    assert "[System.BoardColumn] = 'Architecture''s Queue'" in wiql
    assert "[System.TeamProject] = 'Data Team''s Project'" in wiql
    assert "[System.WorkItemType] IN ('Epic', 'Feature''s')" in wiql


def test_get_work_items_queries_by_wiql(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "token")
    work_item_client = Mock()
    work_item_client.query_by_wiql.return_value = SimpleNamespace(
        work_items=[SimpleNamespace(id=101), SimpleNamespace(id=202)]
    )
    ado = ADOIntegration(connection=make_connection(work_item_client=work_item_client))

    ids = ado.get_work_items("Architecture")

    assert ids == [101, 202]
    work_item_client.query_by_wiql.assert_called_once()
    assert work_item_client.query_by_wiql.call_args.kwargs == {}
    assert "Architecture" in work_item_client.query_by_wiql.call_args.args[0].query
    assert "System.WorkItemType" not in work_item_client.query_by_wiql.call_args.args[0].query


def test_get_work_items_can_optionally_filter_work_item_type(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "token")
    work_item_client = Mock()
    work_item_client.query_by_wiql.return_value = SimpleNamespace(work_items=[])
    ado = ADOIntegration(connection=make_connection(work_item_client=work_item_client))

    ado.get_work_items("Architecture", work_item_types=["Epic", "Feature"])

    assert "System.WorkItemType" in work_item_client.query_by_wiql.call_args.args[0].query


def test_claim_work_item_uses_assigned_to_patch(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "token")
    monkeypatch.setenv("ADO_ASSIGNED_TO", "agent@example.com")
    work_item_client = Mock()
    ado = ADOIntegration(connection=make_connection(work_item_client=work_item_client))

    ado.claim_work_item(101)

    document = work_item_client.update_work_item.call_args.kwargs["document"]
    assert document[0].path == "/fields/System.AssignedTo"
    assert document[0].value == "agent@example.com"
    assert work_item_client.update_work_item.call_args.kwargs["id"] == 101


def test_move_work_item_uses_configured_column_field(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "token")
    work_item_client = Mock()
    ado = ADOIntegration(connection=make_connection(work_item_client=work_item_client))

    ado.move_work_item(101, "Engineering")

    document = work_item_client.update_work_item.call_args.kwargs["document"]
    assert document[0].path == "/fields/System.BoardColumn"
    assert document[0].value == "Engineering"


def test_update_wiki_uses_project_wiki_and_page_path(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "token")
    wiki_client = Mock()
    ado = ADOIntegration(connection=make_connection(wiki_client=wiki_client))

    ado.update_wiki("content", "Architecture_101")

    wiki_client.create_or_update_page.assert_called_once_with(
        parameters={"content": "content"},
        project=ado.project_name,
        wiki_identifier=ado.project_name,
        path="/Architecture_101",
        version=None,
        version_descriptor=None,
    )


def test_create_child_work_item_uses_configured_type_and_parent_link(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "token")
    monkeypatch.setenv("ADO_ORGANIZATION_URL", "https://dev.azure.com/example")
    monkeypatch.setenv("ADO_PROJECT_NAME", "ExampleProject")
    work_item_client = Mock()
    work_item_client.get_work_item.return_value = SimpleNamespace(
        url="https://dev.azure.com/example/ExampleProject/_apis/wit/workItems/101"
    )
    work_item_client.create_work_item.return_value = SimpleNamespace(id=303)
    ado = ADOIntegration(connection=make_connection(work_item_client=work_item_client))

    child_id = ado.create_child_work_item(
        parent_work_item_id=101,
        work_item_type="User Story",
        story={
            "title": "Build output",
            "user_story": "As a data engineer...",
            "specification": "INPUT...\nOUTPUT...",
            "acceptance_criteria": [{"done": "", "item": "done"}],
        },
        target_column="Engineering",
    )

    assert child_id == 303
    work_item_client.create_work_item.assert_called_once()
    assert work_item_client.create_work_item.call_args.kwargs["type"] == "User Story"
    document = work_item_client.create_work_item.call_args.kwargs["document"]
    assert document[0].path == "/fields/System.Title"
    assert document[1].path == "/fields/System.Description"
    assert "<h2>Specification: Build output</h2>" in document[1].value
    assert "<h3>Flow Specification</h3>" in document[1].value
    assert "&#9744; done" in document[1].value
    assert document[-1].path == "/relations/-"
    assert document[-1].value["rel"] == "System.LinkTypes.Hierarchy-Reverse"
    assert document[-1].value["url"].startswith("https://dev.azure.com/example/")


def test_create_child_work_item_falls_back_to_env_parent_url(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "token")
    monkeypatch.setenv("ADO_ORGANIZATION_URL", "https://dev.azure.com/example")
    monkeypatch.setenv("ADO_PROJECT_NAME", "ExampleProject")
    work_item_client = Mock()
    work_item_client.get_work_item.return_value = SimpleNamespace(url="")
    work_item_client.create_work_item.return_value = SimpleNamespace(id=303)
    ado = ADOIntegration(connection=make_connection(work_item_client=work_item_client))

    ado.create_child_work_item(
        parent_work_item_id=101,
        work_item_type="User Story",
        story={
            "title": "Build output",
            "user_story": "As a data engineer...",
            "specification": "INPUT...\nOUTPUT...",
            "acceptance_criteria": [{"done": "", "item": "done"}],
        },
        target_column="Engineering",
    )

    document = work_item_client.create_work_item.call_args.kwargs["document"]
    assert (
        document[-1].value["url"]
        == "https://dev.azure.com/example/ExampleProject/_apis/wit/workItems/101"
    )


def test_post_work_item_specification_prepends_description(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "token")
    monkeypatch.setenv("ADO_PROJECT_NAME", "ExampleProject")
    work_item_client = Mock()
    ado = ADOIntegration(connection=make_connection(work_item_client=work_item_client))

    ado.post_work_item_specification(
        101,
        {
            "source_work_item_type": "Issue",
            "user_stories": [
                {
                    "title": "Build output",
                    "user_story": "As a data engineer...",
                    "specification": "## Flow\nContext\n\n```mermaid\nflowchart LR\n    A[Input] --> B[Output]\n```\n\n## Steps\n1. Do the work.",
                    "acceptance_criteria": [{"done": "", "item": "Implemented"}],
                }
            ],
        },
        existing_description="Existing business description.",
    )

    work_item_client.update_work_item.assert_called_once()
    document = work_item_client.update_work_item.call_args.kwargs["document"]
    assert document[0].path == "/fields/System.Description"
    assert document[0].value.startswith("<h1>Data Architect Implementation Specifications</h1>")
    assert "<h3>Flow Specification</h3>" in document[0].value
    assert "<pre><code>flowchart LR" in document[0].value
    assert "A[Input] --&gt; B[Output]" in document[0].value
    assert "&#9744; Implemented" in document[0].value
    assert "<h2>Previous Description</h2>" in document[0].value
    assert "<p>Existing business description.</p>" in document[0].value
