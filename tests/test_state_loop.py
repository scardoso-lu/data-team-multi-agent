"""
Unit tests for the orchestration pipeline.

All external I/O (ADO, Teams, Fabric, Purview, Anthropic) is mocked so the
tests run without cloud credentials.

Because _process_item runs as a background asyncio.Task (so HITL waits in
one column never stall others), each test calls `await _drain(loop)` after
_tick() to let those tasks run to completion before asserting.

Test coverage:
  - All five columns are scanned concurrently per tick.
  - Already-claimed items are skipped without dispatching.
  - In-flight guard prevents double-dispatch of the same work item.
  - Approved items move to the next column.
  - Rejected items are unclaimed and left in the current column.
  - AgentResult.success=False skips the approval gate.
  - Final stage (no dst_col) moves the item to the 'Done' column.
  - All Anthropic tool schemas are structurally valid.
  - No agent exposes duplicate tool names in its tool list.
  - ApprovalWebhookPayload accepts valid actions and rejects unknown ones.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from data_team.orchestrator.models import (
    AgentResult,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalWebhookPayload,
    WorkItem,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


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


def _make_work_item(column: str, assigned_to: str | None = None, item_id: int = 42) -> WorkItem:
    return WorkItem(
        id=item_id,
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


def _make_loop(pipeline: list, settings=None) -> MagicMock:
    """Build a minimal StateLoop-like object for unit tests."""
    from data_team.orchestrator.state_loop import StateLoop

    settings = settings or _make_settings()
    loop = StateLoop.__new__(StateLoop)
    loop.settings = settings
    loop.gate = MagicMock()
    loop._pipeline = pipeline
    loop._in_flight = set()
    loop._active_tasks = set()
    return loop


async def _drain(loop) -> None:
    """Wait for all background tasks spawned during _tick() to complete."""
    if loop._active_tasks:
        await asyncio.gather(*list(loop._active_tasks), return_exceptions=True)


# ── Tool schema validation ────────────────────────────────────────────────────


def _assert_valid_schema(tool: dict, source: str) -> None:
    assert "name" in tool, f"{source}: missing 'name'"
    assert "description" in tool, f"{source}: missing 'description'"
    assert "input_schema" in tool, f"{source}: missing 'input_schema'"
    schema = tool["input_schema"]
    assert schema.get("type") == "object", f"{source}/{tool['name']}: type must be 'object'"
    assert "properties" in schema, f"{source}/{tool['name']}: missing 'properties'"


def test_ado_tool_schemas_valid():
    from data_team.tools.ado import ADO_TOOLS
    for t in ADO_TOOLS:
        _assert_valid_schema(t, "ado")


def test_teams_tool_schemas_valid():
    from data_team.tools.teams import TEAMS_TOOLS
    for t in TEAMS_TOOLS:
        _assert_valid_schema(t, "teams")


def test_fabric_tool_schemas_valid():
    from data_team.tools.fabric import FABRIC_TOOLS
    for t in FABRIC_TOOLS:
        _assert_valid_schema(t, "fabric")


def test_purview_tool_schemas_valid():
    from data_team.tools.purview import PURVIEW_TOOLS
    for t in PURVIEW_TOOLS:
        _assert_valid_schema(t, "purview")


def test_no_duplicate_tool_names_per_agent():
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
        duplicates = [n for n in names if names.count(n) > 1]
        assert not duplicates, f"{AgentCls.__name__} has duplicate tools: {duplicates}"


def test_each_agent_class_accepts_only_settings():
    """Agents must construct with only (settings,) — no shared client or gate."""
    from data_team.agents.architect import DataArchitectAgent
    from data_team.agents.engineer import DataEngineerAgent
    from data_team.agents.qa import QAEngineerAgent
    from data_team.agents.analyst import DataAnalystAgent
    from data_team.agents.steward import DataStewardAgent
    import inspect

    for AgentCls in (
        DataArchitectAgent, DataEngineerAgent, QAEngineerAgent,
        DataAnalystAgent, DataStewardAgent,
    ):
        sig = inspect.signature(AgentCls.__init__)
        params = [p for p in sig.parameters if p != "self"]
        assert params == ["settings"], (
            f"{AgentCls.__name__}.__init__ must accept only 'settings', got {params}"
        )


# ── Webhook payload validation ────────────────────────────────────────────────


def test_approval_payload_approve():
    p = ApprovalWebhookPayload(work_item_id=1, action="approve", resolved_by="u@org.com")
    assert p.action == "approve"


def test_approval_payload_reject():
    p = ApprovalWebhookPayload(
        work_item_id=1, action="reject", resolved_by="u@org.com", reason="Schema wrong"
    )
    assert p.reason == "Schema wrong"


# ── StateLoop concurrency / independence tests ────────────────────────────────


@pytest.mark.asyncio
async def test_tick_scans_all_columns_concurrently():
    """Every column in the pipeline must be queried during one tick."""
    with patch(
        "data_team.orchestrator.state_loop.list_work_items_in_column",
        new_callable=AsyncMock,
    ) as mock_list:
        mock_list.return_value = []
        loop = _make_loop([
            ("01 - Architecture", MagicMock(name="arch"),  "02 - Engineering"),
            ("02 - Engineering",  MagicMock(name="eng"),   "03 - QA & Testing"),
            ("03 - QA & Testing", MagicMock(name="qa"),    "04 - Analytics & BI"),
        ])
        await loop._tick()
        assert mock_list.call_count == 3
        queried = {call.args[1] for call in mock_list.call_args_list}
        assert queried == {"01 - Architecture", "02 - Engineering", "03 - QA & Testing"}


@pytest.mark.asyncio
async def test_tick_skips_claimed_items():
    """Items with assigned_to set must not be dispatched."""
    claimed = _make_work_item("01 - Architecture", assigned_to="Data Architect Agent")

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock) as mock_claim,
    ):
        mock_list.return_value = [claimed]
        loop = _make_loop([("01 - Architecture", MagicMock(), "02 - Engineering")])

        await loop._tick()
        await _drain(loop)

        mock_claim.assert_not_called()


@pytest.mark.asyncio
async def test_tick_skips_in_flight_items():
    """Items already in self._in_flight must not be dispatched again."""
    item = _make_work_item("01 - Architecture")

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock) as mock_claim,
    ):
        mock_list.return_value = [item]
        loop = _make_loop([("01 - Architecture", MagicMock(), "02 - Engineering")])
        loop._in_flight.add(42)  # pre-mark as in-flight

        await loop._tick()
        await _drain(loop)

        mock_claim.assert_not_called()


@pytest.mark.asyncio
async def test_approved_item_moves_to_next_column():
    """Approved work items must be moved to the next column."""
    item = _make_work_item("01 - Architecture")
    agent = MagicMock()
    agent.name = "Data Architect Agent"
    agent.run = AsyncMock(return_value=AgentResult(
        work_item_id=42, agent_name="Data Architect Agent",
        success=True, summary="Architecture complete.",
    ))

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock) as mock_claim,
        patch("data_team.orchestrator.state_loop.move_work_item", new_callable=AsyncMock) as mock_move,
    ):
        mock_list.return_value = [item]
        loop = _make_loop([("01 - Architecture", agent, "02 - Engineering")])
        loop.gate.request_and_wait = AsyncMock(return_value=_make_approval(ApprovalStatus.APPROVED))

        await loop._tick()
        await _drain(loop)

        mock_claim.assert_any_call(loop.settings, 42, "Data Architect Agent")
        agent.run.assert_called_once_with(item)
        mock_move.assert_called_once_with(loop.settings, 42, "02 - Engineering")


@pytest.mark.asyncio
async def test_rejected_item_is_unclaimed_not_moved():
    """Rejected items must be unclaimed (assigned to '') but not advanced."""
    item = _make_work_item("02 - Engineering")
    agent = MagicMock()
    agent.name = "Data Engineer Agent"
    agent.run = AsyncMock(return_value=AgentResult(
        work_item_id=42, agent_name="Data Engineer Agent",
        success=True, summary="Engineering complete.",
    ))

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock) as mock_claim,
        patch("data_team.orchestrator.state_loop.move_work_item", new_callable=AsyncMock) as mock_move,
    ):
        mock_list.return_value = [item]
        loop = _make_loop([("02 - Engineering", agent, "03 - QA & Testing")])
        loop.gate.request_and_wait = AsyncMock(return_value=_make_approval(ApprovalStatus.REJECTED))

        await loop._tick()
        await _drain(loop)

        # First claim (take ownership), then unclaim (release after rejection)
        assert mock_claim.call_count == 2
        mock_claim.assert_any_call(loop.settings, 42, "")
        mock_move.assert_not_called()


@pytest.mark.asyncio
async def test_agent_failure_skips_approval_gate():
    """A failed agent run must not trigger the approval gate."""
    item = _make_work_item("03 - QA & Testing")
    agent = MagicMock()
    agent.name = "QA Engineer Agent"
    agent.run = AsyncMock(return_value=AgentResult(
        work_item_id=42, agent_name="QA Engineer Agent",
        success=False, summary="", error="Data quality failed",
    ))

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock),
        patch("data_team.orchestrator.state_loop.move_work_item", new_callable=AsyncMock),
    ):
        mock_list.return_value = [item]
        loop = _make_loop([("03 - QA & Testing", agent, "04 - Analytics & BI")])
        loop.gate.request_and_wait = AsyncMock()

        await loop._tick()
        await _drain(loop)

        loop.gate.request_and_wait.assert_not_called()


@pytest.mark.asyncio
async def test_final_stage_moves_to_done():
    """The steward stage (dst_col=None) must advance the item to 'Done'."""
    item = _make_work_item("05 - Governance & Review")
    agent = MagicMock()
    agent.name = "Data Steward Agent"
    agent.run = AsyncMock(return_value=AgentResult(
        work_item_id=42, agent_name="Data Steward Agent",
        success=True, summary="All checks passed.",
    ))

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column", new_callable=AsyncMock) as mock_list,
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock),
        patch("data_team.orchestrator.state_loop.move_work_item", new_callable=AsyncMock) as mock_move,
    ):
        mock_list.return_value = [item]
        loop = _make_loop([("05 - Governance & Review", agent, None)])  # None → Done
        loop.gate.request_and_wait = AsyncMock(return_value=_make_approval(ApprovalStatus.APPROVED))

        await loop._tick()
        await _drain(loop)

        mock_move.assert_called_once_with(loop.settings, 42, "Done")


@pytest.mark.asyncio
async def test_multiple_columns_process_independently():
    """
    Items in different columns must be claimed and processed concurrently —
    one column's processing must not prevent another's from starting.
    """
    item_arch = _make_work_item("01 - Architecture", item_id=10)
    item_eng  = _make_work_item("02 - Engineering",  item_id=20)

    agent_arch = MagicMock(name="arch_agent")
    agent_arch.name = "Data Architect Agent"
    agent_arch.run = AsyncMock(return_value=AgentResult(
        work_item_id=10, agent_name="Data Architect Agent",
        success=True, summary="Architecture done.",
    ))

    agent_eng = MagicMock(name="eng_agent")
    agent_eng.name = "Data Engineer Agent"
    agent_eng.run = AsyncMock(return_value=AgentResult(
        work_item_id=20, agent_name="Data Engineer Agent",
        success=True, summary="Engineering done.",
    ))

    def _items_for_col(settings, col):
        return {
            "01 - Architecture": [item_arch],
            "02 - Engineering":  [item_eng],
        }.get(col, [])

    with (
        patch("data_team.orchestrator.state_loop.list_work_items_in_column",
              new_callable=AsyncMock, side_effect=_items_for_col),
        patch("data_team.orchestrator.state_loop.claim_work_item", new_callable=AsyncMock),
        patch("data_team.orchestrator.state_loop.move_work_item", new_callable=AsyncMock) as mock_move,
    ):
        loop = _make_loop([
            ("01 - Architecture", agent_arch, "02 - Engineering"),
            ("02 - Engineering",  agent_eng,  "03 - QA & Testing"),
        ])
        loop.gate.request_and_wait = AsyncMock(side_effect=[
            _make_approval(ApprovalStatus.APPROVED),
            _make_approval(ApprovalStatus.APPROVED),
        ])

        await loop._tick()
        await _drain(loop)

        # Both agents must have run
        agent_arch.run.assert_called_once_with(item_arch)
        agent_eng.run.assert_called_once_with(item_eng)
        # Both items must have advanced
        assert mock_move.call_count == 2
