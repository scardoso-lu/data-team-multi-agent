# Sprint 13 — MCP (Model Context Protocol) Integration

## Gap

LangChain's harness anatomy mentions MCP integration via `langchain-mcp-adapters`
as a first-class extensibility mechanism. MCP is an open protocol for connecting
agents to external tools, databases, and data sources through a standardised
tool-description and invocation interface.

Currently the only tools available to the LLM are those hard-coded in
`shared_skills/tools/` or `ToolRegistry`. Teams that own external data sources
(an internal SQL database, a REST API, a documentation store) cannot plug their
MCP servers in without touching core agent code. There is no adapter between
the MCP protocol and the `Tool` / `ToolRegistry` abstractions introduced in Sprint 7.

## Goal

Introduce an `MCPToolAdapter` that connects to one or more MCP servers, discovers
the tools they advertise, and registers them as `Tool` instances in a `ToolRegistry`.
Provide a `NullMCPAdapter` for offline test runs. Add configuration to
`config/default.json` for listing MCP server endpoints.

---

## User Story 13.1 — `MCPServerClient` for tool discovery

**As a** platform engineer,
**I want** a client that queries an MCP server's tool-discovery endpoint and
returns a list of tool descriptors,
**so that** I can introspect what any MCP server offers without writing
server-specific code.

### Implementation

**New file:** `shared_skills/mcp/__init__.py`

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json
import urllib.request
import urllib.error


@dataclass
class MCPToolDescriptor:
    name: str
    description: str
    parameters: Dict[str, str]
    server_url: str


class MCPServerClient:
    """HTTP client for a single MCP server."""

    def __init__(self, server_url: str, timeout: int = 5):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout

    def list_tools(self) -> List[MCPToolDescriptor]:
        """Fetch the tool manifest from the MCP server."""
        url = f"{self.server_url}/tools"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"MCP server unreachable at {url}: {exc}") from exc

        return [
            MCPToolDescriptor(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("parameters", {}),
                server_url=self.server_url,
            )
            for t in data.get("tools", [])
        ]

    def invoke(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Invoke a tool on the MCP server and return the result as a string."""
        url = f"{self.server_url}/tools/{tool_name}"
        body = json.dumps({"arguments": arguments}).encode()
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
                return data.get("result", json.dumps(data))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            return f"ERROR: MCP invocation failed — {exc}"
```

**Acceptance criteria:**
- `list_tools()` parses a JSON response with `{"tools": [...]}` and returns
  `MCPToolDescriptor` objects.
- Network failure raises `RuntimeError` with the URL and underlying error.
- `invoke` returns the `result` string from the response, or an `ERROR:` string
  on failure.

**Tests:** `tests/test_mcp.py`
```python
def test_list_tools_parses_manifest(monkeypatch):
    manifest = {"tools": [{"name": "query_db", "description": "Run SQL",
                            "parameters": {"sql": "str"}}]}
    # Monkeypatch urllib.request.urlopen to return manifest
    ...
    client = MCPServerClient("http://localhost:8080")
    tools = client.list_tools()
    assert tools[0].name == "query_db"

def test_invoke_returns_result_string(monkeypatch):
    ...
    result = MCPServerClient("http://localhost:8080").invoke("query_db", {"sql": "SELECT 1"})
    assert result == "1 row"
```

---

## User Story 13.2 — `MCPToolAdapter` registers MCP tools in `ToolRegistry`

**As a** board agent,
**I want** an adapter that takes MCP tool descriptors and registers them as
`Tool` instances in my `ToolRegistry`,
**so that** the LLM can call MCP-provided tools by name exactly like built-in tools.

### Implementation

**File:** `shared_skills/mcp/__init__.py`

```python
from shared_skills.tools import Tool, ToolRegistry


class MCPToolAdapter:
    """Adapts an MCPServerClient into Tool instances for a ToolRegistry."""

    def __init__(self, client: MCPServerClient):
        self._client = client

    def register_all(self, registry: ToolRegistry) -> int:
        """Discover and register all tools from the MCP server. Returns count."""
        descriptors = self._client.list_tools()
        for desc in descriptors:
            registry.register(Tool(
                name=desc.name,
                description=desc.description,
                parameters=desc.parameters,
                fn=lambda **kwargs, _name=desc.name: self._client.invoke(_name, kwargs),
            ))
        return len(descriptors)
```

**File:** `shared_skills/mcp/null_adapter.py`

```python
class NullMCPAdapter:
    """No-op adapter used in tests and offline runs."""

    def register_all(self, registry) -> int:
        return 0
```

**Acceptance criteria:**
- `register_all` registers one `Tool` per descriptor and returns the count.
- The registered `Tool.fn` calls `client.invoke` with the correct tool name.
- `NullMCPAdapter.register_all` always returns 0 and leaves the registry unchanged.

**Tests:** `tests/test_mcp.py`
```python
def test_adapter_registers_tools(monkeypatch):
    descriptors = [MCPToolDescriptor("query_db", "Run SQL", {"sql": "str"}, "http://x")]
    client = MCPServerClient("http://x")
    monkeypatch.setattr(client, "list_tools", lambda: descriptors)
    monkeypatch.setattr(client, "invoke", lambda name, args: "result")
    registry = ToolRegistry()
    adapter = MCPToolAdapter(client)
    count = adapter.register_all(registry)
    assert count == 1
    assert registry.get("query_db") is not None
```

---

## User Story 13.3 — MCP server configuration in `config/default.json`

**As a** platform operator,
**I want** MCP server URLs listed in `config/default.json`,
**so that** teams can add new MCP servers without touching agent code.

### Implementation

**File:** `config/default.json`

```json
"mcp": {
  "servers": [],
  "timeout_seconds": 5
}
```

Each entry in `servers` is:
```json
{
  "name": "internal-sql",
  "url": "http://mcp-sql-server:8080",
  "enabled": true
}
```

**File:** `shared_skills/agent_base/__init__.py`

In `BoardAgent.__init__`, load MCP config and register adapters:

```python
from shared_skills.mcp import MCPServerClient, MCPToolAdapter
from shared_skills.mcp.null_adapter import NullMCPAdapter

mcp_servers = config.require("mcp", "servers") or []
for server_conf in mcp_servers:
    if not server_conf.get("enabled", True):
        continue
    client = MCPServerClient(server_conf["url"],
                             timeout=config.require("mcp", "timeout_seconds"))
    try:
        MCPToolAdapter(client).register_all(self._tool_registry)
    except RuntimeError:
        # Server unreachable — log and skip, don't crash the agent
        pass
```

**Acceptance criteria:**
- With an empty `servers` list, no MCP calls are made and the agent starts normally.
- A server with `"enabled": false` is silently skipped.
- An unreachable server logs a warning but does not raise or block agent startup.

**Tests:** `tests/test_mcp.py`
```python
def test_disabled_server_not_contacted(monkeypatch):
    contacted = []
    monkeypatch.setattr(MCPServerClient, "list_tools", lambda self: contacted.append(self.server_url) or [])
    config = AppConfig({"mcp": {"servers": [{"name": "x", "url": "http://x", "enabled": False}], "timeout_seconds": 5}})
    agent = DataArchitectAgent(..., config=config)
    assert contacted == []
```

---

## User Story 13.4 — MCP tool invocation events

**As a** platform operator,
**I want** MCP tool calls emitted as events with server URL and latency,
**so that** I can distinguish local tool calls from remote MCP calls in the
`EventRecorder` and monitor MCP server performance.

### Implementation

**File:** `shared_skills/events/__init__.py`

Add constants:
```python
MCP_TOOL_INVOKED   = "mcp_tool_invoked"
MCP_TOOL_COMPLETED = "mcp_tool_completed"
MCP_TOOL_FAILED    = "mcp_tool_failed"
```

**File:** `shared_skills/mcp/__init__.py`

Wrap `invoke` to emit events with `{"tool_name": ..., "server_url": ..., "latency_ms": ...}`.

**Acceptance criteria:**
- `EventRecorder.events` contains `mcp_tool_invoked` before the call and
  `mcp_tool_completed` (or `mcp_tool_failed`) after.
- `latency_ms` is present in every `mcp_tool_completed` event.

**Tests:** `tests/test_mcp.py`
```python
def test_mcp_invocation_events_emitted(monkeypatch):
    events = EventRecorder()
    ...
    assert any(e["type"] == "mcp_tool_invoked" for e in events.events)
    assert any(e["type"] == "mcp_tool_completed" for e in events.events)
```
