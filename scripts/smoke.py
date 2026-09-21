import asyncio
import json

import httpx

from app.mcp_client import check_mcp


async def main():
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get("http://app:8000/health/ready")
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))
    print(json.dumps(await check_mcp(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
