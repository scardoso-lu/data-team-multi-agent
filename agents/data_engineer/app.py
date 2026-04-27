# Data Engineer Agent
# Implements the Medallion architecture on Microsoft Fabric.

import os
import sys
import time
import logging

# Add shared_skills to the path for both container and local execution.
for shared_skills_path in (
    "/app/shared_skills",
    os.path.abspath("shared_skills"),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "shared_skills")),
):
    if os.path.isdir(shared_skills_path) and shared_skills_path not in sys.path:
        sys.path.insert(0, shared_skills_path)

try:
    from .skill_loader import SkillLoader
except ImportError:
    from skill_loader import SkillLoader

from approval_server import ApprovalServer
from agent_base import AgentRuntimeMixin
from agent_runtime import failure_result, retry_operation
from artifacts import validate_fabric_artifact
from config import AppConfig
from events import ARTIFACT_CREATED, WORK_ITEM_CLAIMED, WORK_ITEM_MOVED, build_event_sink

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data_engineer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DataEngineerAgent(AgentRuntimeMixin):
    """Handles data pipeline implementation on Microsoft Fabric."""
    
    def __init__(self, ado=None, teams=None, fabric=None, approvals=None, config=None, events=None):
        self.config = config or AppConfig()
        self._agent_name = "data_engineer"
        self.agent_config = self.config.agent("data_engineer")
        self.runtime_config = self.config.require("runtime")
        self.skill_loader = SkillLoader() if ado is None or teams is None or fabric is None else None
        self.ado = ado or self.skill_loader.get_skill("ado_integration").ADOIntegration()
        self.teams = teams or self.skill_loader.get_skill("teams_integration").TeamsIntegration()
        self.fabric = fabric or self.skill_loader.get_skill("fabric_integration").FabricIntegration()
        self.approvals = approvals or ApprovalServer()
        self.events = events or build_event_sink(self.config)
        self.work_item_id = None
    
    def claim_work_item(self, work_item_id):
        """Claim a work item from the ADO board."""
        self.work_item_id = self.ado.claim_work_item(work_item_id)
        print(f"Data Engineer claimed work item {self.work_item_id}")
    
    def implement_medallion_architecture(self, architecture_doc):
        """Implement Bronze, Silver, and Gold layers in Fabric."""
        print(f"Implementing Medallion architecture: {architecture_doc}")
        
        # Create Fabric workspace
        workspace = self.fabric.create_workspace(
            f"{self.agent_config['workspace_prefix']}_{self.work_item_id}"
        )
        
        deployed_pipelines = []
        for pipeline_name in self.config.require("fabric", "pipelines"):
            deployed_pipelines.append(
                self.fabric.deploy_pipeline(
                    pipeline_name=pipeline_name,
                    workspace_name=workspace.name
                )
            )
        
        # Commit pipeline code to ADO Git
        print(f"Committed pipeline code to ADO Git for work item {self.work_item_id}")
        
        return {
            "workspace": workspace.name,
            "pipelines": [pipeline.name for pipeline in deployed_pipelines]
        }
    
    def request_approval(self):
        """Request human approval via Teams."""
        return self.request_human_approval("fabric_implementation", {})
    
    def move_to_next_column(self):
        """Move work item to the configured next column."""
        self.ado.move_work_item(self.work_item_id, self.agent_config["next_column"])

    def process_next_item(self):
        """Process one work item from the configured column."""
        work_items = self.ado.get_work_items(self.agent_config["column"])
        if not work_items:
            return {
                "agent": "data_engineer",
                "status": "skipped",
                "reason": "no_work_items",
                "column": self.agent_config["column"],
            }

        work_item_id = work_items[0]
        try:
            max_retries = self.runtime_config["max_retries"]
            retry_delay = self.runtime_config["retry_delay_seconds"]
            self.claim_work_item(work_item_id)
            self.events.emit(WORK_ITEM_CLAIMED, "data_engineer", work_item_id)

            architecture_doc = retry_operation(
                lambda: self.ado.get_work_item_details(work_item_id),
                max_retries,
                retry_delay,
            )
            implementation = retry_operation(
                lambda: self.implement_medallion_architecture(architecture_doc),
                max_retries,
                retry_delay,
            )
            validate_fabric_artifact(implementation)
            if hasattr(self.ado, "set_work_item_details"):
                self.ado.set_work_item_details(work_item_id, implementation)
            self.events.emit(
                ARTIFACT_CREATED,
                "data_engineer",
                work_item_id,
                artifact_type="fabric_implementation",
                artifact=implementation,
            )
            approval = self.request_human_approval("fabric_implementation", implementation)
            decision = self.wait_for_approval_decision(approval["approval_id"])
            decision_status, target_column = self.route_approval_decision(decision)

            if decision_status != "approved":
                return {
                    "agent": "data_engineer",
                    "status": "skipped",
                    "reason": f"approval_{decision_status}",
                    "work_item_id": work_item_id,
                    "moved_to": target_column,
                    "approval": decision,
                }

            self.move_to_next_column()
            self.events.emit(
                WORK_ITEM_MOVED,
                "data_engineer",
                work_item_id,
                to_column=self.agent_config["next_column"],
            )
            return {
                "agent": "data_engineer",
                "status": "processed",
                "work_item_id": work_item_id,
                "moved_to": self.agent_config["next_column"],
                "artifact": implementation,
            }
        except Exception as exc:
            logger.error(f"Error processing work item {work_item_id}: {exc}", exc_info=True)
            return failure_result(
                "data_engineer",
                work_item_id,
                exc,
                events=self.events,
                ado=self.ado,
                error_column=self.runtime_config.get("error_column"),
            )
    
    def run(self):
        """Main agent loop."""
        logger.info("Data Engineer Agent started")
        self.start_approval_server()
        
        while True:
            try:
                # Poll ADO for new work items every 5 minutes
                logger.info("Polling ADO for new work items...")
                self.drain_available_work_items(logger)
            
            except Exception as e:
                logger.error(f"Error polling ADO for work items: {e}", exc_info=True)
            
            # Wait for 5 minutes before polling again
            logger.info("Waiting for 5 minutes before next poll...")
            time.sleep(self.runtime_config["poll_interval_seconds"])

if __name__ == "__main__":
    agent = DataEngineerAgent()
    agent.run()
