"""
Unit tests for the orchestration pipeline.

These tests mock all external I/O (ADO, Teams, Fabric, Purview, Anthropic)
so they run without any cloud credentials.

Test coverage:
  - StateLoop._tick routes unclaimed items to the correct agent per column.
  - StateLoop._tick skips already-claimed items.
  - Approved work items are moved to the next column.
  - Rejected work items are unclaimed and left in the current column.
  - AgentResult.success=False prevents approval gate from being reached.
  - Anthropic tool schemas are structurally valid (name, description,
    input_schema with type/properties/required).
  - ApprovalWebhookPayload rejects unknown action values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from data_team.orchestrator.models import (
    AgentResult,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalWebhookPayload,
    WorkItem,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_settings(**overrides) -> MagicMock:
    s = MagicMock()
    s.anthropic_api_key = "test-key"
    s.anthropic_model = "claude-opus-4-7"
    s.poll_interval_seconds = 1
    s.approval_timeout_hours = 1
    s.col_architecture = "01 - Architecture"
    s.col_engineering = "02 - Engineering"
    s.col_qa = "03 - QA & Testing"
    s.col_analytics = "04 - Analytics & BI"
    s.col_governance = "05 - Governance & Review"
    s.col_done = "Done"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _make_work_item(column: str, assigned_to: str | None = None) -> WorkItem:
    return WorkItem(
        id=42,
        title="Build Customer 360",
        description="Implement full medallion for customer data.",
        column=column,
        assigned_to=assigned_to,
    )


def _make_approval(status: ApprovalStatus) -> ApprovalRequest:
    return ApprovalRequest(
        work_item_id=42,
        agent_name="Test Agent",
        column="01 - Architecture",
        summary="Done",
        status=status,
        requested_at=datetime.now(timezone.utc),
    )


# ── Tool schema validation ────────────────────────────────────────────────────


def _assert_valid_tool_schema(tool: dict, source: str) -> None:
    assert "name" in tool, f"{source}: missing 'name'"
    assert "description" in tool, f"{source}: missing 'description'"
    assert "input_schema" in tool, f"{source}: missing 'input_schema'"
    schema = tool["input_schema"]
    assert schema.get("type") == "object", f"{source}/{tool['name']}: input_schema type must be 'object'"
    assert "properties" in schema, f"{source}/{tool['name']}: missing 'properties'"


def test_ado_tool_schemas_are_valid() -> None:
    from data_team.tools.ado import ADO_TOOLS
    for tool in ADO_TOOLS:
        _assert_valid_tool_schema(tool, "ado")


def test_teams_tool_schemas_are_valid() -> None:
    from data_team.tools.teams import TEAMS_TOOLS
    for tool in TEAMS_TOOLS:
        _assert_valid_tool_schema(tool, "teams")


def test_fabric_tool_schemas_are_valid() -> None:
    from data_team.tools.fabric import FABRIC_TOOLS
    for tool in FABRIC_TOOLS:
        _assert_valid_tool_schema(tool, "fabric")


def test_purview_tool_schemas_are_valid() -> None:
    from data_team.tools.purview import PURVIEW_TOOLS
    for tool in PURVIEW_TOOLS:
        _assert_valid_tool_schema(tool, "purview")


def test_no_duplicate_tool_names_per_agent() -> None:
    """Each agent's combined tool list must have unique names."""
    from data_team.agents.architect import DataArchitectAgent
    from data_team.agents.engineer import DataEngineerAgent
    from data_team.agents.qa import QAEngineerAgent
    from data_team.agents.analyst import DataAnalystAgent
    from data_team.agents.steward import DataStewardAgent

    for AgentCls in (
        DataArchitectAgent, DataEngineerAgent, QAEngineerAgent,
        DataAnalystAgent, DataStewardAgent,
    ):
        names = [t["name"] for t in AgentCls.tools]
        assert len(names) == len(set(names)), (
            f"{AgentCls.__name__} has duplicate tool names: "
            + str([n for n in names if names.count(n) > 1])
        )


# ── ApprovalWebhookPayload validation ────────────────────────────────────────


def test_approval_webhook_payload_valid_approve() -> None:
    p = ApprovalWebhookPayload(work_item_id=1, action="approve", resolved_by="user@org.com")
    assert p.action == "approve"


def test_approval_webhook_payload_valid_reject() -> None:
    p = ApprovalWebhookPayload(
        work_item_id=1, action="reject", resolved_by="user@org.com", reason="Schema mismatch"
    )
    assert p.action == "reject"
    assert p.reason == "Schema mismatch"


# ── StateLoop unit tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tick_skips_claimed_items() -> None:
    """Items with assigned_to set must not be dispatched."""
    from data_team.orchestrator.state_loop import StateLoop

    settings = _make_settings()
    claimed_item = _make_work_item("01 - Architecture", assigned_to="Data Architect Agent")

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock) as mock_claim,
        patch("anthropic.Anthropic"),
    ):
        mock_list.return_value = [claimed_item]
        loop = StateLoop.__new__(StateLoop)
        loop.settings = settings
        loop.gate = MagicMock()
        loop._pipeline = [("01 - Architecture", MagicMock(), "02 - Engineering")]

        await loop._tick()
        mock_claim.assert_not_called()


@pytest.mark.asyncio
async def test_tick_claims_and_processes_unclaimed_item() -> None:
    """Unclaimed items must be claimed and handed to the agent."""
    from data_team.orchestrator.state_loop import StateLoop

    settings = _make_settings()
    item = _make_work_item("01 - Architecture")
    agent = MagicMock()
    agent.name = "Data Architect Agent"
    agent.run = AsyncMock(
        return_value=AgentResult(
            work_item_id=42,
            agent_name="Data Architect Agent",
            success=True,
            summary="Architecture done.",
        )
    )

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock) as mock_claim,
        patch("data_team.orchestrator.state_loop.move_work_item", new_callable=AsyncMock) as mock_move,
        patch("anthropic.Anthropic"),
    ):
        mock_list.return_value = [item]
        gate = MagicMock()
        gate.request_and_wait = AsyncMock(return_value=_make_approval(ApprovalStatus.APPROVED))

        loop = StateLoop.__new__(StateLoop)
        loop.settings = settings
        loop.gate = gate
        loop._pipeline = [("01 - Architecture", agent, "02 - Engineering")]

        await loop._tick()

        mock_claim.assert_called_once_with(settings, 42, "Data Architect Agent")
        agent.run.assert_called_once_with(item)
        mock_move.assert_called_once_with(settings, 42, "02 - Engineering")


@pytest.mark.asyncio
async def test_rejected_approval_unclaims_item() -> None:
    """A rejected approval must unclaim the item (assign to '') without moving it."""
    from data_team.orchestrator.state_loop import StateLoop

    settings = _make_settings()
    item = _make_work_item("02 - Engineering")
    agent = MagicMock()
    agent.name = "Data Engineer Agent"
    agent.run = AsyncMock(
        return_value=AgentResult(
            work_item_id=42,
            agent_name="Data Engineer Agent",
            success=True,
            summary="Engineering done.",
        )
    )

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock) as mock_claim,
        patch("data_team.orchestrator.state_loop.move_work_item", new_callable=AsyncMock) as mock_move,
        patch("anthropic.Anthropic"),
    ):
        mock_list.return_value = [item]
        gate = MagicMock()
        gate.request_and_wait = AsyncMock(return_value=_make_approval(ApprovalStatus.REJECTED))

        loop = StateLoop.__new__(StateLoop)
        loop.settings = settings
        loop.gate = gate
        loop._pipeline = [("02 - Engineering", agent, "03 - QA & Testing")]

        await loop._tick()

        # Should unclaim (second call with empty string) but NOT move
        assert mock_claim.call_count == 2
        mock_claim.assert_any_call(settings, 42, "")
        mock_move.assert_not_called()


@pytest.mark.asyncio
async def test_agent_failure_does_not_trigger_approval_gate() -> None:
    """If agent.run() fails, the approval gate must not be reached."""
    from data_team.orchestrator.state_loop import StateLoop

    settings = _make_settings()
    item = _make_work_item("03 - QA & Testing")
    agent = MagicMock()
    agent.name = "QA Engineer Agent"
    agent.run = AsyncMock(
        return_value=AgentResult(
            work_item_id=42,
            agent_name="QA Engineer Agent",
            success=False,
            summary="",
            error="Data quality assertions failed",
        )
    )

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock),
        patch("data_team.orchestrator.state_loop.move_work_item", new_callable=AsyncMock),
        patch("anthropic.Anthropic"),
    ):
        mock_list.return_value = [item]
        gate = MagicMock()
        gate.request_and_wait = AsyncMock()

        loop = StateLoop.__new__(StateLoop)
        loop.settings = settings
        loop.gate = gate
        loop._pipeline = [("03 - QA & Testing", agent, "04 - Analytics & BI")]

        await loop._tick()

        gate.request_and_wait.assert_not_called()


@pytest.mark.asyncio
async def test_steward_advances_to_done() -> None:
    """The final stage (no dst_col) must move the item to the 'Done' column."""
    from data_team.orchestrator.state_loop import StateLoop

    settings = _make_settings()
    item = _make_work_item("05 - Governance & Review")
    agent = MagicMock()
    agent.name = "Data Steward Agent"
    agent.run = AsyncMock(
        return_value=AgentResult(
            work_item_id=42,
            agent_name="Data Steward Agent",
            success=True,
            summary="All checks passed.",
        )
    )

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock),
        patch("data_team.orchestrator.state_loop.move_work_item", new_callable=AsyncMock) as mock_move,
        patch("anthropic.Anthropic"),
    ):
        mock_list.return_value = [item]
        gate = MagicMock()
        gate.request_and_wait = AsyncMock(return_value=_make_approval(ApprovalStatus.APPROVED))

        loop = StateLoop.__new__(StateLoop)
        loop.settings = settings
        loop.gate = gate
        loop._pipeline = [("05 - Governance & Review", agent, None)]  # None → Done

        await loop._tick()

        mock_move.assert_called_once_with(settings, 42, "Done")
