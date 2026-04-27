# Data Steward Agent
# Acts as the final gatekeeper for data governance and compliance.

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

from agent_base import AgentRuntimeMixin
from agent_runtime import failure_result, retry_operation
from artifacts import validate_governance_artifact
from config import AppConfig
from events import ARTIFACT_CREATED, WORK_ITEM_CLAIMED, WORK_ITEM_MOVED, build_event_sink

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data_steward.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DataStewardAgent(AgentRuntimeMixin):
    """Handles final governance review and compliance checks."""
    
    def __init__(self, ado=None, teams=None, purview=None, config=None, events=None):
        self.config = config or AppConfig()
        self._agent_name = "data_steward"
        self.agent_config = self.config.agent("data_steward")
        self.runtime_config = self.config.require("runtime")
        self.skill_loader = SkillLoader() if ado is None or teams is None or purview is None else None
        self.ado = ado or self.skill_loader.get_skill("ado_integration").ADOIntegration()
        self.teams = teams or self.skill_loader.get_skill("teams_integration").TeamsIntegration()
        self.purview = purview or self.skill_loader.get_skill("purview_integration").PurviewIntegration()
        self.events = events or build_event_sink(self.config)
        self.work_item_id = None
    
    def claim_work_item(self, work_item_id):
        """Claim a work item from the ADO board."""
        self.work_item_id = self.ado.claim_work_item(work_item_id)
        print(f"Data Steward claimed work item {self.work_item_id}")
    
    def audit_lifecycle(self):
        """Audit the entire data lifecycle for compliance."""
        print(f"Auditing data lifecycle for work item {self.work_item_id}")
        
        audit_results = self.config.copy_value("governance", "audit_results", default={})
        
        # Publish final metadata to Purview
        self.purview.publish_metadata(audit_results)
        
        # Post final summary to Teams
        self.teams.send_notification(
            title=self.agent_config["completion_title"].format(work_item_id=self.work_item_id),
            message=self.agent_config["completion_message"].format(work_item_id=self.work_item_id)
        )
        
        return audit_results
    
    def mark_as_done(self):
        """Move the work item to the configured terminal column."""
        self.ado.move_work_item(self.work_item_id, self.agent_config["next_column"])

    def process_next_item(self):
        """Process one work item from the configured column."""
        work_items = self.ado.get_work_items(self.agent_config["column"])
        if not work_items:
            return {
                "agent": "data_steward",
                "status": "skipped",
                "reason": "no_work_items",
                "column": self.agent_config["column"],
            }

        work_item_id = work_items[0]
        try:
            max_retries = self.runtime_config["max_retries"]
            retry_delay = self.runtime_config["retry_delay_seconds"]
            self.claim_work_item(work_item_id)
            self.events.emit(WORK_ITEM_CLAIMED, "data_steward", work_item_id)

            audit_results = retry_operation(
                self.audit_lifecycle,
                max_retries,
                retry_delay,
            )
            validate_governance_artifact(audit_results)
            if hasattr(self.ado, "set_work_item_details"):
                self.ado.set_work_item_details(work_item_id, audit_results)
            self.events.emit(
                ARTIFACT_CREATED,
                "data_steward",
                work_item_id,
                artifact_type="audit_results",
                artifact=audit_results,
            )
            self.mark_as_done()
            self.events.emit(
                WORK_ITEM_MOVED,
                "data_steward",
                work_item_id,
                to_column=self.agent_config["next_column"],
            )
            return {
                "agent": "data_steward",
                "status": "processed",
                "work_item_id": work_item_id,
                "moved_to": self.agent_config["next_column"],
                "artifact": audit_results,
            }
        except Exception as exc:
            logger.error(f"Error processing work item {work_item_id}: {exc}", exc_info=True)
            return failure_result(
                "data_steward",
                work_item_id,
                exc,
                events=self.events,
                ado=self.ado,
                error_column=self.runtime_config.get("error_column"),
            )
    
    def run(self):
        """Main agent loop."""
        logger.info("Data Steward Agent started")
        
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
    agent = DataStewardAgent()
    agent.run()
