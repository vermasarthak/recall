import asyncio
from httpx import AsyncClient

async def main():
    async with AsyncClient() as client:
        res = await client.get("http://localhost:8000/docs")
        print(res.status_code)

asyncio.run(main())
