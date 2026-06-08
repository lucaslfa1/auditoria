import sys
sys.path.append('backend')
import asyncio
import httpx
from unittest.mock import patch
from backend.main import app
from backend.tests.test_auth_api import ROLE_AUTH_USERS

async def run():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("backend.main.database.get_user_by_username", side_effect=lambda u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", return_value=True):
            login = await client.post(
                "/api/auth/login",
                json={"username": "Supervisora", "password": "super-pass"}
            )
            print("STATUS:", login.status_code)
            print("BODY:", login.text)

asyncio.run(run())
