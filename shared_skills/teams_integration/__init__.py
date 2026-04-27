# Teams Integration Skill
# Handles approval requests and notifications via Microsoft Teams.

import requests
import json

from config import AppConfig

class TeamsIntegration:
    """Handles Microsoft Teams approval requests and notifications."""
    
    def __init__(self):
        self.config = AppConfig()
        self.webhook_url = self.config.from_env("teams", "webhook_env")
    
    def send_approval_request(
        self,
        work_item_id,
        agent_name,
        message,
        callback_url,
        approval_id=None,
        artifact_summary=None,
        artifact_links=None,
    ):
        """Send an approval request to Microsoft Teams."""
        artifact_links = artifact_links or []
        link_text = "\n".join(
            f"- [{link.get('label', link.get('url'))}]({link.get('url')})"
            for link in artifact_links
        )
        approval_text = message
        if approval_id:
            approval_text += f"\n\nApproval ID: {approval_id}"
        if artifact_summary:
            approval_text += f"\n\nArtifact: {artifact_summary}"
        if link_text:
            approval_text += f"\n\nLinks:\n{link_text}"

        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0076D7",
            "summary": "Approval Request",
            "sections": [{
                "activityTitle": f"Approval Request from {agent_name}",
                "activitySubtitle": f"Work Item: {work_item_id}",
                "text": approval_text,
                "potentialAction": [{
                    "@type": "ActionCard",
                    "name": "Approve",
                    "inputs": [{
                        "@type": "TextInput",
                        "id": "approval",
                        "isMultiline": False,
                        "title": "Enter 'Approve' to proceed"
                    }],
                    "actions": [{
                        "@type": "HttpPOST",
                        "name": "Submit",
                        "target": callback_url
                    }]
                }, {
                    "@type": "ActionCard",
                    "name": "Reject",
                    "inputs": [{
                        "@type": "TextInput",
                        "id": "comments",
                        "isMultiline": True,
                        "title": "Rejection comments"
                    }],
                    "actions": [{
                        "@type": "HttpPOST",
                        "name": "Submit",
                        "target": callback_url.replace("/approve/", "/reject/")
                    }]
                }]
            }]
        }
        
        response = requests.post(
            self.webhook_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload)
        )
        
        if response.status_code == 200:
            print(f"Approval request sent for work item {work_item_id}")
            return True
        else:
            print(f"Failed to send approval request: {response.text}")
            return False
    
    def send_notification(self, title, message):
        """Send a generic notification to Microsoft Teams."""
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0076D7",
            "summary": title,
            "sections": [{
                "activityTitle": title,
                "text": message
            }]
        }
        
        response = requests.post(
            self.webhook_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload)
        )
        
        if response.status_code == 200:
            print(f"Notification sent: {title}")
            return True
        else:
            print(f"Failed to send notification: {response.text}")
            return False
