from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.db import database_status
from app.search import search_documents as retrieve

mcp = FastMCP(
    "rag-pg",
    host="0.0.0.0",
    port=8001,
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["mcp-server:8001", "localhost:8001", "127.0.0.1:8001"],
    ),
)


@mcp.tool()
async def system_status() -> dict:
    """Check database connection and pgvector availability."""
    return await database_status()


@mcp.tool()
def search_documents(query: str, mode: str = "hybrid", top_k: int = 6) -> dict:
    """Search evidence across all ready documents."""
    return retrieve(query, mode, top_k)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
