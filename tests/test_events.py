import json
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (ROOT_DIR, os.path.join(ROOT_DIR, "shared_skills")):
    if path not in sys.path:
        sys.path.insert(0, path)

from events import FileJsonEventSink, StdoutJsonEventSink, WORK_ITEM_CLAIMED, build_event_sink


class TinyConfig:
    def __init__(self, values):
        self.values = values

    def get(self, *keys, default=None):
        value = self.values
        for key in keys:
            if key not in value:
                return default
            value = value[key]
        return value

    def require(self, *keys):
        value = self.get(*keys)
        if value is None:
            raise KeyError(keys)
        return value


def test_stdout_json_event_sink_writes_json_line(capsys):
    sink = StdoutJsonEventSink()

    sink.emit(WORK_ITEM_CLAIMED, "agent", "1")

    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == WORK_ITEM_CLAIMED
    assert payload["agent"] == "agent"
    assert payload["work_item_id"] == "1"


def test_file_json_event_sink_appends_json_line(tmp_path):
    path = tmp_path / "events.jsonl"
    sink = FileJsonEventSink(path)

    sink.emit(WORK_ITEM_CLAIMED, "agent", "1")

    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["type"] == WORK_ITEM_CLAIMED


def test_build_event_sink_from_config(tmp_path):
    path = tmp_path / "events.jsonl"
    config = TinyConfig({"events": {"sink": "file", "file_path": str(path)}})

    sink = build_event_sink(config)
    sink.emit(WORK_ITEM_CLAIMED, "agent", "1")

    assert path.exists()
