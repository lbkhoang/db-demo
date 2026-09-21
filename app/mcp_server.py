from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.db import database_status
from app.search import search_documents as retrieve, read_version_evidence
from app.documents import list_versions
from uuid import UUID

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
def search_documents(query: str, mode: str = "hybrid", version_ids: list[str] | None = None, top_k: int = 6) -> dict:
    """Search policy evidence. Empty version_ids uses only latest ready versions."""
    return retrieve(query, mode, version_ids, top_k)


@mcp.tool()
def compare_document_versions(version_ids: list[str]) -> dict:
    """Read complete evidence from two versions of the same short document for comparison."""
    return read_version_evidence(version_ids)


@mcp.tool()
def list_document_versions(document_id: str) -> dict:
    """List available versions of a document, including ingestion status."""
    return {"versions": [
        {"id": str(row["id"]), "filename": row["filename"], "status": row["status"]}
        for row in list_versions(UUID(document_id))
    ]}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
