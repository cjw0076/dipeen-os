import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    params = StdioServerParameters(
        command="npx",
        args=["-y", "unity-mcp"],
        env={**os.environ},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=20)
            tools = await asyncio.wait_for(session.list_tools(), timeout=20)

    print(json.dumps({"tools": [tool.name for tool in tools.tools]}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
