import json
from pathlib import Path


class WorkspaceManager:
    """Manages per-agent, per-work-item local workspaces."""

    def __init__(self, root="logs/workspaces"):
        self.root = Path(root)

    def workspace_for(self, agent_key, work_item_id):
        safe_work_item = str(work_item_id).replace("/", "_").replace("\\", "_")
        return self.root / agent_key / safe_work_item

    def ensure_workspace(self, agent_key, work_item_id):
        path = self.workspace_for(agent_key, work_item_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve(self, agent_key, work_item_id, relative_path):
        workspace = self.ensure_workspace(agent_key, work_item_id).resolve()
        target = (workspace / relative_path).resolve()
        if workspace != target and workspace not in target.parents:
            raise ValueError("path escapes workspace")
        return target

    def write_text(self, agent_key, work_item_id, relative_path, content):
        target = self.resolve(agent_key, work_item_id, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        return target

    def read_text(self, agent_key, work_item_id, relative_path):
        return self.resolve(agent_key, work_item_id, relative_path).read_text(encoding="utf-8")

    def list_files(self, agent_key, work_item_id):
        workspace = self.ensure_workspace(agent_key, work_item_id)
        return sorted(
            str(path.relative_to(workspace))
            for path in workspace.rglob("*")
            if path.is_file()
        )

    def write_artifact_sidecar(self, agent_key, work_item_id, artifact):
        return self.write_text(
            agent_key,
            work_item_id,
            "artifact.json",
            json.dumps(artifact, indent=2, sort_keys=True, default=str),
        )

    def cleanup(self, agent_key, work_item_id):
        workspace = self.workspace_for(agent_key, work_item_id)
        if not workspace.exists():
            return False
        for path in sorted(workspace.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        workspace.rmdir()
        return True
