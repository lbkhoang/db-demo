import asyncio
import json

from app.mcp_client import check_mcp

if __name__ == "__main__":
    print(json.dumps(asyncio.run(asyncio.wait_for(check_mcp(), 8))))
