"""
Core state machine loop.

Every `poll_interval_seconds` the loop queries each Kanban column for unclaimed
work items, dispatches the appropriate agent, then blocks at the HITL gate until
a human approves or rejects before advancing the ticket.

Column pipeline (order matters — each entry is the source column):

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

# (source_column, agent_class_import_path, target_column | None)
_PIPELINE_SPEC: list[tuple[str, str, str | None]] = [
    ("col_architecture", "data_team.agents.architect:DataArchitectAgent", "col_engineering"),
    ("col_engineering",  "data_team.agents.engineer:DataEngineerAgent",  "col_qa"),
    ("col_qa",           "data_team.agents.qa:QAEngineerAgent",          "col_analytics"),
    ("col_analytics",    "data_team.agents.analyst:DataAnalystAgent",    "col_governance"),
    ("col_governance",   "data_team.agents.steward:DataStewardAgent",    None),  # → Done
]


def _import_agent(path: str) -> type:
    """Lazy-import agent classes to avoid circular deps at module load."""
    module_path, class_name = path.rsplit(":", 1)
    import importlib
    return getattr(importlib.import_module(module_path), class_name)


class StateLoop:
    """
    The central orchestrator.  Instantiate once and call `await loop.run()`.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.gate = ApprovalGate(settings)

        # Build pipeline at runtime so agent modules are only imported once
        import anthropic
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        self._pipeline: list[tuple[str, BaseAgent, str | None]] = []
        for src_key, agent_path, dst_key in _PIPELINE_SPEC:
            src_col = getattr(settings, src_key)
            dst_col = getattr(settings, dst_key) if dst_key else None
            AgentClass = _import_agent(agent_path)
            agent = AgentClass(settings, self._client, self.gate)
            self._pipeline.append((src_col, agent, dst_col))

        log.info("state_loop.initialised", stages=len(self._pipeline))

    # ── Public interface ──────────────────────────────────────────────────────

    async def run(self) -> None:
        """Run forever, polling ADO on each interval tick."""
        log.info("state_loop.started", interval_s=self.settings.poll_interval_seconds)
        while True:
            try:
                await self._tick()
            except Exception:
                log.exception("state_loop.tick_unhandled_error")
            await asyncio.sleep(self.settings.poll_interval_seconds)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _tick(self) -> None:
        """Single poll cycle — process one unclaimed item per stage."""
        for src_col, agent, dst_col in self._pipeline:
            items = await list_work_items_in_column(self.settings, src_col)
            for item in items:
                if item.assigned_to:
                    # Already claimed; another run of the loop will pick it up
                    # once the agent unclaims it (or it moves columns).
                    continue
                await self._process_item(item, agent, dst_col)
                break  # Process one item per column per tick to avoid starvation

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _process_item(
        self,
        item: WorkItem,
        agent: BaseAgent,
        dst_col: str | None,
    ) -> None:
        bound = log.bind(work_item_id=item.id, agent=agent.name, src_col=item.column)

        # 1. Claim
        bound.info("agent.claiming")
        await claim_work_item(self.settings, item.id, agent.name)

        # 2. Execute
        bound.info("agent.running")
        result = await agent.run(item)

        if not result.success:
            bound.error("agent.failed", error=result.error)
            # Unclaim so a human can investigate or re-queue
            await claim_work_item(self.settings, item.id, "")
            return

        bound.info("agent.succeeded", tool_calls=result.tool_calls_made)

        # 3. HITL gate — blocks until approved, rejected, or timed out
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
            bound.warning(
                "work_item.held",
                status=approval.status,
                reason=approval.rejection_reason,
            )
            # Unclaim so an engineer can re-work and re-queue
            await claim_work_item(self.settings, item.id, "")
