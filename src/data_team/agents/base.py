"""
BaseAgent — abstract foundation for all five data-team agents.

Each concrete agent subclass declares:
  • name          — display name used in ADO assignments and Teams messages
  • system_prompt — injected as the cached system block for every Claude call
  • tools         — Anthropic tool schema list (subset of ADO/Teams/Fabric/Purview)

The run() method drives the standard agentic loop:
  1. Send work-item context to Claude with the agent's tool list.
  2. Execute every tool_use block returned by Claude.
  3. Feed tool results back; repeat until stop_reason == "end_turn".
  4. Return an AgentResult with a summary and list of created artifacts.

Agent independence guarantee
────────────────────────────
Every agent owns its own `anthropic.Anthropic` client created at construction
time. No shared mutable state exists between agent instances. The HITL gate and
ADO state-loop are entirely external to this class — agents never touch them.

Prompt caching: the system block carries cache_control=ephemeral so repeated
tool-use rounds within one run() call hit the Anthropic cache.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

import anthropic
import structlog

from data_team.orchestrator.config import Settings
from data_team.orchestrator.models import AgentResult, WorkItem

log = structlog.get_logger()

_MAX_TOOL_ROUNDS = 30  # safety cap against runaway tool loops


class BaseAgent(ABC):
    name: str
    system_prompt: str
    tools: list[dict[str, Any]]

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Each agent owns its client — no cross-agent shared state
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # ── Public interface ──────────────────────────────────────────────────────

    async def run(self, work_item: WorkItem) -> AgentResult:
        bound = log.bind(agent=self.name, work_item_id=work_item.id)
        bound.info("agent.run.start")

        messages: list[dict] = [
            {"role": "user", "content": self._build_user_message(work_item)}
        ]
        artifacts: list[str] = []
        tool_calls_made = 0

        for _round in range(_MAX_TOOL_ROUNDS):
            response = self._client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=8192,
                system=[
                    {
                        "type": "text",
                        "text": self.system_prompt,
                        # Cache the (large) system prompt across rounds
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=self.tools,
                messages=messages,
            )

            # Append assistant turn verbatim so the conversation stays consistent
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                summary = self._extract_text(response)
                bound.info("agent.run.complete", rounds=_round + 1)
                return AgentResult(
                    work_item_id=work_item.id,
                    agent_name=self.name,
                    success=True,
                    summary=summary,
                    artifacts_created=artifacts,
                    tool_calls_made=tool_calls_made,
                )

            if response.stop_reason != "tool_use":
                return AgentResult(
                    work_item_id=work_item.id,
                    agent_name=self.name,
                    success=False,
                    summary="",
                    error=f"Unexpected stop_reason: {response.stop_reason}",
                )

            # ── Execute all tool calls in this round ──────────────────────────
            tool_results: list[dict] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tool_calls_made += 1
                bound.info("tool.call", tool=block.name)
                try:
                    result = await self._dispatch(block.name, block.input)
                    # Track artifact references returned by tools
                    if isinstance(result, dict) and "artifact" in result:
                        artifacts.append(str(result["artifact"]))
                    content = json.dumps(result, default=str)
                except Exception as exc:
                    bound.exception("tool.error", tool=block.name)
                    content = json.dumps({"error": str(exc)})

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        return AgentResult(
            work_item_id=work_item.id,
            agent_name=self.name,
            success=False,
            summary="",
            error=f"Exceeded maximum tool rounds ({_MAX_TOOL_ROUNDS})",
        )

    # ── Subclass hooks ────────────────────────────────────────────────────────

    @abstractmethod
    async def _dispatch(self, tool_name: str, tool_input: dict) -> Any:
        """Route a tool_use block to the correct implementation."""

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_user_message(self, item: WorkItem) -> str:
        return (
            f"## Work Item #{item.id}: {item.title}\n\n"
            f"**Description:**\n{item.description}\n\n"
            f"**Acceptance Criteria:**\n{item.acceptance_criteria}\n\n"
            f"**Current Board Column:** {item.column}\n\n"
            "Please complete your responsibilities for this work item, "
            "using the tools available to you. "
            "When all work is done, provide a concise summary of everything you did "
            "and every artifact you produced."
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""
