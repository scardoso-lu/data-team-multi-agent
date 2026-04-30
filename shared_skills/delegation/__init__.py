from events import (
    AGENT_DELEGATION_COMPLETED,
    AGENT_DELEGATION_FAILED,
    AGENT_DELEGATION_STARTED,
    ARTIFACT_CREATED,
)


class AgentTaskDispatcher:
    """In-process dispatcher for bounded subagent work."""

    def __init__(self, agent_factory, events=None, parent_agent="root", depth=0):
        self.agent_factory = agent_factory
        self.events = events
        self.parent_agent = parent_agent
        self.depth = depth

    def dispatch(self, agent_key, payload, work_item_id=None):
        child_depth = self.depth + 1
        if self.events is not None:
            self.events.emit(
                AGENT_DELEGATION_STARTED,
                self.parent_agent,
                work_item_id,
                child_agent=agent_key,
                depth=child_depth,
            )
        try:
            agent = self.agent_factory(agent_key)
            if self.events is not None:
                agent.events = self.events
            if work_item_id is not None:
                agent.work_item_id = work_item_id
            artifact = agent.execute_stage(payload)
            agent.validate_artifact(artifact)
            if self.events is not None:
                self.events.emit(
                    ARTIFACT_CREATED,
                    agent_key,
                    work_item_id,
                    artifact_type=getattr(agent, "artifact_type", None),
                    artifact=artifact,
                    delegated=True,
                    parent_agent=self.parent_agent,
                    depth=child_depth,
                )
                self.events.emit(
                    AGENT_DELEGATION_COMPLETED,
                    self.parent_agent,
                    work_item_id,
                    child_agent=agent_key,
                    depth=child_depth,
                )
            return artifact
        except Exception as exc:
            if self.events is not None:
                self.events.emit(
                    AGENT_DELEGATION_FAILED,
                    self.parent_agent,
                    work_item_id,
                    child_agent=agent_key,
                    depth=child_depth,
                    error=str(exc),
                )
            raise
