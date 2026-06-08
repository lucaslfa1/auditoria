import asyncio
import os
import sys
import unittest
from unittest.mock import patch

import httpx


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main  # noqa: E402
from main import app  # noqa: E402
from routers import auth as auth_router  # noqa: E402


TEST_USER = {
    "testuser": {
        "username": "TestUser",
        "password_hash": "hash",
        "role": "admin",
        "supervisor_name": "",
    }
}


class _FakeClient:
    host = "127.0.0.1"


class _FakeRequest:
    def __init__(self, *, cookies=None, headers=None):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.client = _FakeClient()


class TestHttpSecurity(unittest.TestCase):
    async def _request(self, method: str, url: str, **kwargs):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, **kwargs)

    def setUp(self):
        auth_router._LOGIN_ATTEMPTS.clear()
        self.addCleanup(auth_router._LOGIN_ATTEMPTS.clear)

    def test_health_response_sets_security_headers(self):
        response = asyncio.run(self._request("GET", "/api/health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(response.headers.get("x-frame-options"), "DENY")
        self.assertEqual(response.headers.get("referrer-policy"), "no-referrer")

    def test_cors_preflight_uses_explicit_allowed_methods(self):
        response = asyncio.run(
            self._request(
                "OPTIONS",
                "/api/health",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "DELETE",
                },
            )
        )

        allow_methods = response.headers.get("access-control-allow-methods", "")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("*", allow_methods)
        self.assertIn("DELETE", allow_methods)
        self.assertIn("GET", allow_methods)
        self.assertIn("POST", allow_methods)

    def test_global_rate_limit_key_prefers_authenticated_session(self):
        first = _FakeRequest(
            cookies={auth_router.SESSION_COOKIE_NAME: "session-a"},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        second = _FakeRequest(
            cookies={auth_router.SESSION_COOKIE_NAME: "session-b"},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )

        first_key = main._resolve_rate_limit_key(first)
        second_key = main._resolve_rate_limit_key(second)

        self.assertTrue(first_key.startswith("session:"))
        self.assertTrue(second_key.startswith("session:"))
        self.assertNotEqual(first_key, second_key)

    def test_global_rate_limit_key_falls_back_to_ip_without_session(self):
        request = _FakeRequest(headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.1"})

        self.assertEqual(main._resolve_rate_limit_key(request), "ip:203.0.113.10")

    def test_global_rate_limit_sweep_caps_high_cardinality_keys(self):
        main._GLOBAL_RATE_LIMIT.clear()
        self.addCleanup(main._GLOBAL_RATE_LIMIT.clear)

        for index in range(5):
            main._GLOBAL_RATE_LIMIT[f"ip:{index}"] = [100.0 + index]

        main._sweep_global_rate_limit(now=200.0, cutoff=50.0, max_keys=3)

        self.assertEqual(list(main._GLOBAL_RATE_LIMIT.keys()), ["ip:2", "ip:3", "ip:4"])

    def test_database_initialization_runs_once_from_startup_helper(self):
        original_initialized = main._DB_INITIALIZED
        main._DB_INITIALIZED = False
        self.addCleanup(setattr, main, "_DB_INITIALIZED", original_initialized)

        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "", "ENVIRONMENT": "development"}, clear=False):
            with patch("main.database.init_db") as mock_init_db:
                main._initialize_database_once()
                main._initialize_database_once()

        mock_init_db.assert_called_once()

    def test_database_initialization_retries_after_tolerated_runtime_error(self):
        original_initialized = main._DB_INITIALIZED
        main._DB_INITIALIZED = False
        self.addCleanup(setattr, main, "_DB_INITIALIZED", original_initialized)

        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "", "ENVIRONMENT": "development"}, clear=False):
            with patch("main.logger.exception"):
                with patch("main.database.init_db", side_effect=RuntimeError("bootstrap failed")) as mock_init_db:
                    main._initialize_database_once()
                    main._initialize_database_once()

        self.assertEqual(mock_init_db.call_count, 2)
        self.assertFalse(main._DB_INITIALIZED)

    def test_database_initialization_skips_under_pytest(self):
        original_initialized = main._DB_INITIALIZED
        main._DB_INITIALIZED = False
        self.addCleanup(setattr, main, "_DB_INITIALIZED", original_initialized)

        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "tests/test_http_security.py::case"}, clear=False):
            with patch("main.database.init_db") as mock_init_db:
                main._initialize_database_once()

        mock_init_db.assert_not_called()
        self.assertFalse(main._DB_INITIALIZED)

    def test_login_rate_limit_blocks_repeated_failures(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch.dict(
                    os.environ,
                    {
                        "ENABLE_LOGIN_RATE_LIMIT": "true",
                        "LOGIN_RATE_LIMIT_MAX_ATTEMPTS": "2",
                        "LOGIN_RATE_LIMIT_WINDOW_SECONDS": "60",
                    },
                    clear=False,
                ):
                    with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, username: TEST_USER.get(username)):
                        with patch("bcrypt.checkpw", return_value=False):
                            first = await client.post(
                                "/api/auth/login",
                                json={"username": "TestUser", "password": "wrong-1"},
                            )
                            second = await client.post(
                                "/api/auth/login",
                                json={"username": "TestUser", "password": "wrong-2"},
                            )
                            third = await client.post(
                                "/api/auth/login",
                                json={"username": "TestUser", "password": "wrong-3"},
                            )

            self.assertEqual(first.status_code, 401)
            self.assertEqual(second.status_code, 401)
            self.assertEqual(third.status_code, 429)
            self.assertEqual(third.json()["detail"], "Muitas tentativas de login. Tente novamente mais tarde.")
            self.assertTrue(int(third.headers["retry-after"]) >= 1)

        asyncio.run(flow())
