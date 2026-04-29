from unittest.mock import Mock

from shared_skills.teams_integration import TeamsIntegration


def test_approval_request_updates_devops_discussion():
    ado = Mock()
    notifications = TeamsIntegration(ado=ado)

    result = notifications.send_approval_request(
        work_item_id="1",
        agent_name="Data Architect",
        message="Review this",
        approval_id="approval-1",
        artifact_summary="Architecture ready",
        artifact_links=[{"label": "Wiki", "url": "https://example.invalid/wiki"}],
    )

    assert result is True
    ado.post_work_item_comment.assert_called_once()
    work_item_id, comment = ado.post_work_item_comment.call_args.args
    assert work_item_id == "1"
    assert "approval-1" in comment
    assert "Architecture ready" in comment
    assert "https://example.invalid/wiki" in comment
    assert "approval store" in comment


def test_notification_updates_known_devops_work_item():
    ado = Mock()
    notifications = TeamsIntegration(ado=ado)

    result = notifications.send_notification(
        title="Missing examples",
        message="Provide examples",
        work_item_id=123,
    )

    assert result is True
    ado.post_work_item_comment.assert_called_once_with(
        123,
        "Missing examples\n\nProvide examples",
    )


def test_notification_can_parse_work_item_id_from_text():
    ado = Mock()
    notifications = TeamsIntegration(ado=ado)

    result = notifications.send_notification(
        title="Work Item 1098 Needs Business Examples",
        message="Provide examples",
    )

    assert result is True
    ado.post_work_item_comment.assert_called_once()
    assert ado.post_work_item_comment.call_args.args[0] == "1098"


def test_notification_skips_when_work_item_id_is_unknown():
    ado = Mock()
    notifications = TeamsIntegration(ado=ado)

    result = notifications.send_notification(
        title="Missing examples",
        message="Provide examples",
    )

    assert result is False
    ado.post_work_item_comment.assert_not_called()
