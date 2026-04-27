"""
Core state machine loop.

Agent independence model
────────────────────────
Every Kanban column is polled concurrently in each tick via asyncio.gather.
When an unclaimed work item is found, _process_item is fired as a background
asyncio.Task so that a 24-hour HITL wait in Column 01 never stalls Column 02
(or any other column).  An in-flight set prevents the same work item from being
dispatched twice across ticks.

Column pipeline:

    01 - Architecture  →  DataArchitectAgent   →  02 - Engineering
    02 - Engineering   →  DataEngineerAgent    →  03 - QA & Testing
    03 - QA & Testing  →  QAEngineerAgent      →  04 - Analytics & BI
    04 - Analytics & BI→  DataAnalystAgent     →  05 - Governance & Review
    05 - Governance    →  DataStewardAgent     →  Done
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from data_team.orchestrator.config import Settings
from data_team.orchestrator.models import ApprovalStatus, WorkItem
from data_team.tools.ado import claim_work_item, list_work_items_in_column, move_work_item
from data_team.hitl.approval_gate import ApprovalGate

if TYPE_CHECKING:
    from data_team.agents.base import BaseAgent

log = structlog.get_logger()

_PIPELINE_SPEC: list[tuple[str, str, str | None]] = [
    ("col_architecture", "data_team.agents.architect:DataArchitectAgent", "col_engineering"),
    ("col_engineering",  "data_team.agents.engineer:DataEngineerAgent",  "col_qa"),
    ("col_qa",           "data_team.agents.qa:QAEngineerAgent",          "col_analytics"),
    ("col_analytics",    "data_team.agents.analyst:DataAnalystAgent",    "col_governance"),
    ("col_governance",   "data_team.agents.steward:DataStewardAgent",    None),  # → Done
]


def _import_agent(path: str) -> type:
    module_path, class_name = path.rsplit(":", 1)
    import importlib
    return getattr(importlib.import_module(module_path), class_name)


class StateLoop:
    """
    Central orchestrator.  Call `await loop.run()` to start.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.gate = ApprovalGate(settings)

        # Each agent is constructed independently — owns its own Anthropic client
        self._pipeline: list[tuple[str, BaseAgent, str | None]] = []
        for src_key, agent_path, dst_key in _PIPELINE_SPEC:
            src_col = getattr(settings, src_key)
            dst_col = getattr(settings, dst_key) if dst_key else None
            AgentClass = _import_agent(agent_path)
            self._pipeline.append((src_col, AgentClass(settings), dst_col))

        # Work-item IDs currently being processed — prevents double-dispatch
        self._in_flight: set[int] = set()
        # Background tasks so we can await them on shutdown / in tests
        self._active_tasks: set[asyncio.Task] = set()

        log.info("state_loop.initialised", stages=len(self._pipeline))

    # ── Public interface ──────────────────────────────────────────────────────

    async def run(self) -> None:
        log.info("state_loop.started", interval_s=self.settings.poll_interval_seconds)
        while True:
            try:
                await self._tick()
            except Exception:
                log.exception("state_loop.tick_unhandled_error")
            await asyncio.sleep(self.settings.poll_interval_seconds)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _tick(self) -> None:
        """
        Poll every column concurrently.  Each column scan is independent — a
        slow or blocked column never delays any other.
        """
        await asyncio.gather(
            *[
                self._scan_column(src_col, agent, dst_col)
                for src_col, agent, dst_col in self._pipeline
            ],
            return_exceptions=True,  # one failing scan doesn't kill the rest
        )

    async def _scan_column(
        self, src_col: str, agent: BaseAgent, dst_col: str | None
    ) -> None:
        """
        Find the first unclaimed, not-in-flight item in this column and fire
        _process_item as a background task so this scan returns immediately.
        """
        items = await list_work_items_in_column(self.settings, src_col)
        for item in items:
            if item.assigned_to or item.id in self._in_flight:
                continue

            self._in_flight.add(item.id)
            task = asyncio.create_task(
                self._process_item_guarded(item, agent, dst_col),
                name=f"wi-{item.id}-{agent.name}",
            )
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
            break  # one item per column per scan to avoid starvation

    async def _process_item_guarded(
        self, item: WorkItem, agent: BaseAgent, dst_col: str | None
    ) -> None:
        """Thin wrapper so _in_flight is always cleaned up, even on exceptions."""
        try:
            await self._process_item(item, agent, dst_col)
        finally:
            self._in_flight.discard(item.id)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _process_item(
        self, item: WorkItem, agent: BaseAgent, dst_col: str | None
    ) -> None:
        bound = log.bind(work_item_id=item.id, agent=agent.name, column=item.column)

        # 1. Claim
        bound.info("agent.claiming")
        await claim_work_item(self.settings, item.id, agent.name)

        # 2. Execute — agent is fully self-contained, no shared state with others
        bound.info("agent.running")
        result = await agent.run(item)

        if not result.success:
            bound.error("agent.failed", error=result.error)
            await claim_work_item(self.settings, item.id, "")
            return

        bound.info("agent.succeeded", tool_calls=result.tool_calls_made)

        # 3. HITL gate — may block for minutes or hours; other agents unaffected
        approval = await self.gate.request_and_wait(
            work_item_id=item.id,
            agent_name=agent.name,
            column=item.column,
            summary=result.summary,
            artifacts=result.artifacts_created,
        )

        # 4. Advance or hold
        if approval.status == ApprovalStatus.APPROVED:
            target = dst_col if dst_col else self.settings.col_done
            await move_work_item(self.settings, item.id, target)
            bound.info("work_item.advanced", target_col=target)
        else:
            bound.warning("work_item.held", status=approval.status)
            await claim_work_item(self.settings, item.id, "")
