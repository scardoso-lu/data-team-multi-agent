"""
Entry point.

Starts two concurrent tasks:
  1. FastAPI webhook server — receives Teams Adaptive Card approval responses.
  2. ADO state-loop — polls the Kanban board and dispatches agents.

The ApprovalGate singleton is shared between the StateLoop and the FastAPI
router via `app.state.gate` so webhook callbacks resolve the same in-flight
approval records the loop is waiting on.

In production replace the FastAPI webhook server with an Azure Function
(HTTP trigger, Python v2 programming model) writing to the same Azure Table
Storage — the ApprovalGate.resolve() contract is unchanged.
"""

import asyncio

import uvicorn
from fastapi import FastAPI

from data_team.orchestrator.config import get_settings
from data_team.orchestrator.state_loop import StateLoop
from data_team.hitl.webhook import router as approval_router

app = FastAPI(title="Data-Team Multi-Agent Orchestrator", version="0.1.0")
app.include_router(approval_router, prefix="/webhook")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


async def _run_all() -> None:
    settings = get_settings()

    loop = StateLoop(settings)
    # Share the loop's gate with the webhook router so Teams callbacks resolve
    # the same Table Storage records the loop is waiting on.
    app.state.gate = loop.gate

    server_config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(server_config)

    await asyncio.gather(
        server.serve(),
        loop.run(),
    )


if __name__ == "__main__":
    asyncio.run(_run_all())
