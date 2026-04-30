import json
import sys
import time


WORK_ITEM_CLAIMED = "work_item_claimed"
ARTIFACT_CREATED = "artifact_created"
APPROVAL_REQUESTED = "approval_requested"
APPROVAL_RECEIVED = "approval_received"
APPROVAL_REJECTED = "approval_rejected"
APPROVAL_TIMED_OUT = "approval_timed_out"
WORK_ITEM_MOVED = "work_item_moved"
AGENT_FAILED = "agent_failed"
ARTIFACT_CORRECTION_ATTEMPTED = "artifact_correction_attempted"
LLM_CALL_STARTED = "llm_call_started"
LLM_CALL_COMPLETED = "llm_call_completed"
LLM_CALL_FAILED = "llm_call_failed"


class EventRecorder:
    """In-memory event sink used by the local harness and tests."""

    def __init__(self):
        self.events = []

    def emit(self, event_type, agent, work_item_id=None, **payload):
        event = {
            "type": event_type,
            "agent": agent,
            "work_item_id": work_item_id,
            "timestamp": time.time(),
            "payload": payload,
        }
        self.events.append(event)
        return event


class NullEventRecorder:
    """No-op event sink for production defaults."""

    def emit(self, event_type, agent, work_item_id=None, **payload):
        return {
            "type": event_type,
            "agent": agent,
            "work_item_id": work_item_id,
            "payload": payload,
        }


class StdoutJsonEventSink:
    """Writes events as JSON lines to stdout."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout

    def emit(self, event_type, agent, work_item_id=None, **payload):
        event = {
            "type": event_type,
            "agent": agent,
            "work_item_id": work_item_id,
            "timestamp": time.time(),
            "payload": payload,
        }
        self.stream.write(json.dumps(event, sort_keys=True) + "\n")
        self.stream.flush()
        return event


class FileJsonEventSink:
    """Appends events as JSON lines to a file."""

    def __init__(self, path):
        self.path = path

    def emit(self, event_type, agent, work_item_id=None, **payload):
        event = {
            "type": event_type,
            "agent": agent,
            "work_item_id": work_item_id,
            "timestamp": time.time(),
            "payload": payload,
        }
        with open(self.path, "a", encoding="utf-8") as event_file:
            event_file.write(json.dumps(event, sort_keys=True) + "\n")
        return event


def build_event_sink(config):
    """Build an event sink from config."""
    sink_type = config.get("events", "sink", default="null")
    if sink_type == "memory":
        return EventRecorder()
    if sink_type == "stdout":
        return StdoutJsonEventSink()
    if sink_type == "file":
        return FileJsonEventSink(config.require("events", "file_path"))
    return NullEventRecorder()
