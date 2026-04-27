# Approval callback server
# Handles lightweight approval callbacks without requiring Flask.

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class ApprovalServer:
    """Tracks Teams approval callbacks for a single agent process."""

    def __init__(self):
        self._approved_work_items = set()
        self._lock = threading.Lock()
        self._server = None
        self._thread = None

    def approve(self, work_item_id):
        """Record approval for a work item."""
        with self._lock:
            self._approved_work_items.add(str(work_item_id))

    def create_approval(self, record):
        self.approve(record["approval_id"])
        approved = dict(record)
        approved["status"] = "approved"
        return approved

    def wait_for_decision(self, approval_id, timeout_seconds, poll_seconds):
        approved = self.wait_for_approval(approval_id, timeout_seconds, poll_seconds)
        return {
            "approval_id": approval_id,
            "status": "approved" if approved else "timed_out",
            "decided_by": None,
            "comments": None,
        }

    def is_approved(self, work_item_id):
        """Return whether a work item has been approved."""
        with self._lock:
            return str(work_item_id) in self._approved_work_items

    def wait_for_approval(self, work_item_id, timeout_seconds, poll_seconds):
        """Wait until a work item is approved or the timeout expires."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.is_approved(work_item_id):
                return True
            time.sleep(poll_seconds)
        return self.is_approved(work_item_id)

    def start(self, host, port):
        """Start a background HTTP server for /approve/<work_item_id>."""
        if self._server:
            return self._server.server_address

        approval_server = self

        class ApprovalHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                parsed_path = urlparse(self.path)
                parts = parsed_path.path.strip("/").split("/")

                if len(parts) == 2 and parts[0] == "approve" and parts[1]:
                    approval_server.approve(parts[1])
                    self._send_json(200, {"approved": True, "work_item_id": parts[1]})
                    return

                self._send_json(404, {"error": "not_found"})

            def do_GET(self):
                parsed_path = urlparse(self.path)
                parts = parsed_path.path.strip("/").split("/")

                if len(parts) == 2 and parts[0] == "approved" and parts[1]:
                    self._send_json(
                        200,
                        {
                            "approved": approval_server.is_approved(parts[1]),
                            "work_item_id": parts[1],
                        },
                    )
                    return

                self._send_json(404, {"error": "not_found"})

            def log_message(self, format, *args):
                return

            def _send_json(self, status_code, payload):
                response = json.dumps(payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        self._server = ThreadingHTTPServer((host, port), ApprovalHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self._server.server_address

    def stop(self):
        """Stop the background HTTP server if it is running."""
        if not self._server:
            return

        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
