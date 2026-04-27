# Purview Integration Skill
# Handles interactions with Microsoft Purview for data governance.

from azure.purview.scanning import PurviewScanningClient
from azure.identity import DefaultAzureCredential

from config import AppConfig

class PurviewIntegration:
    """Handles Microsoft Purview data governance tasks."""
    
    def __init__(self):
        self.config = AppConfig()
        self.account_name = self.config.from_env("purview", "account_name_env")
        self.credential = DefaultAzureCredential()
        self.scanning_client = PurviewScanningClient(
            account_name=self.account_name,
            credential=self.credential
        )
    
    def register_data_source(self, source_name, source_type):
        """Register a data source in Purview."""
        data_source = self.scanning_client.data_sources.begin_register(
            source_name=source_name,
            source_type=source_type
        ).result()
        print(f"Registered data source: {data_source.name}")
        return data_source
    
    def scan_data_source(self, source_name):
        """Trigger a scan of a registered data source."""
        scan = self.scanning_client.scans.begin_create(
            source_name=source_name,
            scan_name=f"scan_{source_name}"
        ).result()
        print(f"Started scan: {scan.scan_name}")
        return scan
    
    def publish_metadata(self, metadata):
        """Publish metadata to Purview."""
        response = self.scanning_client.metadata.begin_publish(
            metadata=metadata
        ).result()
        print(f"Published metadata to Purview")
        return response
