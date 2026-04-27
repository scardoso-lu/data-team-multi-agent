import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from shared_skills.ado_integration import ADOIntegration


def make_connection(work_item_client=None, wiki_client=None):
    clients = Mock()
    clients.get_work_item_tracking_client.return_value = work_item_client or Mock()
    clients.get_wiki_client.return_value = wiki_client or Mock()
    return SimpleNamespace(clients=clients)


def test_build_column_wiql_escapes_project_and_column(monkeypatch):
    monkeypatch.setenv("ADO_PAT", "token")
    monkeypatch.setenv("ADO_PROJECT_NAME", "Data Team's Project")
    ado = ADOIntegration(connection=make_connection())

    wiql = ado.build_column_wiql("Architecture's Queue")

    assert "[System.BoardColumn] = 'Architecture''s Queue'" in wiql
    assert "[System.TeamProject] = 'Data Team''s Project'" in wiql


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
    assert work_item_client.query_by_wiql.call_args.kwargs["project"] == ado.project_name
    assert "Architecture" in work_item_client.query_by_wiql.call_args.args[0].query


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
        project=ado.project_name,
        wiki_identifier=ado.project_name,
        path="/Architecture_101",
        parameters={"content": "content"},
        version_descriptor=None,
    )
