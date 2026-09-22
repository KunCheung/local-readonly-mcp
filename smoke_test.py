import asyncio

from mcp import Client


async def main() -> None:
    async with Client("http://127.0.0.1:8000/mcp") as client:
        tools = await client.list_tools()
        print("Tools:")
        for tool in tools.tools:
            print(f"  - {tool.name}")

        result = await client.call_tool("list_roots", {})
        print("\nlist_roots:")
        print(result.structured_content)


if __name__ == "__main__":
    asyncio.run(main())
