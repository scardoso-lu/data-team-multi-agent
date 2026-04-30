from mcp import MCPServerClient


def build_null_mcp_client(name="null"):
    return MCPServerClient(name=name, tools=[])
