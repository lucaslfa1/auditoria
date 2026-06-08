import asyncio
import httpx
from main import app

async def run():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/auth/login",
            json={"username": "TestUser", "password": "s3cret-pass"}
        )
        print("STATUS:", response.status_code)
        print("BODY:", response.text)

asyncio.run(run())
