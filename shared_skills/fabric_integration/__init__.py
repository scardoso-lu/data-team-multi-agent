# Fabric Integration Skill
# Handles interactions with Microsoft Fabric for data engineering tasks.

from azure.identity import DefaultAzureCredential
from azure.mgmt.fabric import FabricManagementClient
import os

from config import AppConfig

class FabricIntegration:
    """Handles Microsoft Fabric data engineering tasks."""
    
    def __init__(self):
        self.config = AppConfig()
        self.subscription_id = self.config.from_env("azure", "subscription_id_env")
        self.resource_group_name = os.getenv(
            "AZURE_RESOURCE_GROUP_NAME",
            self.config.require("azure", "resource_group_name")
        )
        self.credential = DefaultAzureCredential()
        self.fabric_client = FabricManagementClient(self.credential, self.subscription_id)
    
    def create_workspace(self, workspace_name):
        """Create a new Fabric workspace."""
        workspace = self.fabric_client.workspaces.begin_create(
            workspace_name=workspace_name,
            resource_group_name=self.resource_group_name
        ).result()
        print(f"Created workspace: {workspace.name}")
        return workspace
    
    def deploy_pipeline(self, pipeline_name, workspace_name):
        """Deploy a data pipeline to Fabric."""
        pipeline = self.fabric_client.pipelines.begin_create(
            pipeline_name=pipeline_name,
            workspace_name=workspace_name,
            pipeline_definition={"properties": {}}
        ).result()
        print(f"Deployed pipeline: {pipeline.name}")
        return pipeline
    
    def run_dataflow(self, dataflow_name, workspace_name):
        """Run a dataflow in Fabric."""
        dataflow_run = self.fabric_client.dataflows.begin_run(
            dataflow_name=dataflow_name,
            workspace_name=workspace_name
        ).result()
        print(f"Started dataflow run: {dataflow_run.run_id}")
        return dataflow_run
