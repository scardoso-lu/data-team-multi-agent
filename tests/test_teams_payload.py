import os
import sys
from unittest.mock import Mock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from shared_skills.teams_integration import TeamsIntegration


def test_teams_approval_payload_contains_approval_metadata(monkeypatch):
    monkeypatch.setenv("TEAMS_WEBHOOK", "https://example.invalid/webhook")
    response = Mock(status_code=200)

    with patch("shared_skills.teams_integration.requests.post", return_value=response) as post:
        teams = TeamsIntegration()
        result = teams.send_approval_request(
            work_item_id="1",
            agent_name="Data Architect",
            message="Review this",
            callback_url="http://agent/approve/approval-1",
            approval_id="approval-1",
            artifact_summary="Architecture ready",
            artifact_links=[{"label": "Wiki", "url": "https://example.invalid/wiki"}],
        )

    assert result is True
    payload = post.call_args.kwargs["json"]
    text = payload["sections"][0]["text"]
    actions = payload["sections"][0]["potentialAction"]

    assert "approval-1" in text
    assert "Architecture ready" in text
    assert "https://example.invalid/wiki" in text
    assert actions[0]["name"] == "Approve"
    assert actions[1]["name"] == "Reject"
    assert actions[1]["actions"][0]["target"] == "http://agent/reject/approval-1"
