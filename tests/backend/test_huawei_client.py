import asyncio
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.huawei_client import (
    DEFAULT_TOKEN_TTL_SECONDS,
    OAUTH_DIRECT_MODES,
    TOKEN_REFRESH_BUFFER_SECONDS,
    HuaweiAICCClient,
)


def _make_oauth_client(**overrides) -> HuaweiAICCClient:
    defaults = dict(
        cms_url="https://brazilsaas.aicccloud.com:28443",
        fs_url="https://brazilsaas.aicccloud.com:28443",
        cc_id=1,
        vdn=25,
        ak="proxy-ak",
        sk="proxy-sk",
        app_key="proxy-app-key",
        app_secret="proxy-app-secret",
        auth_mode="oauth_direct",
        direct_app_key="00000000-0000-4000-8000-000000000000",
        direct_app_secret="test-direct-secret",
        tenant_space_id="test-tenant",
    )
    defaults.update(overrides)
    return HuaweiAICCClient(**defaults)


class TestHuaweiClient(unittest.TestCase):
    def test_normalize_querycalls_row_enriches_duration_and_reason_code(self):
        row = {
            "callId": "1776893157-197118",
            "callBegin": 1776893157000,
            "callEnd": 1776893255000,
            "leaveReason": 16,
        }

        normalized = HuaweiAICCClient._normalize_querycalls_row(row)

        self.assertEqual(normalized["duration"], 98)
        self.assertEqual(normalized["duracao"], 98)
        self.assertEqual(normalized["beginTime"], 1776893157000)
        self.assertEqual(normalized["endTime"], 1776893255000)
        self.assertEqual(normalized["callReasonCode"], "16")

    def test_normalize_querycalls_row_accepts_huawei_duration_fields(self):
        row = {
            "callId": "1776893157-197118",
            "beginTime": "2026-04-22 18:25:57",
            "endTime": "2026-04-22 18:27:35",
            "callDuration": "98",
        }

        normalized = HuaweiAICCClient._normalize_querycalls_row(row)

        self.assertEqual(normalized["duration"], 98)
        self.assertEqual(normalized["duracao"], 98)

    def test_normalize_querycalls_row_promotes_native_talk_reason(self):
        row = {
            "callId": "1776893157-197118",
            "talkReason": "CONTROLE DE TEMPERATURA",
            "leaveReason": "16",
        }

        normalized = HuaweiAICCClient._normalize_querycalls_row(row)

        self.assertEqual(normalized["callReason"], "CONTROLE DE TEMPERATURA")
        self.assertEqual(normalized["callReasonCode"], "16")

    @patch.dict(os.environ, {"HUAWEI_TIMEZONE": "UTC"}, clear=False)
    def test_coerce_huawei_datetime_string_accepts_epoch_millis(self):
        result = HuaweiAICCClient._coerce_huawei_datetime_string(1776893157000)

        self.assertEqual(result, "2026-04-22 21:25:57")

    def test_querycalls_payload_uses_supported_huawei_contract(self):
        async def _run():
            client = _make_oauth_client()

            class _FakeResponse:
                status_code = 200

                @staticmethod
                def json():
                    return {"resultCode": "0100000", "resultDesc": {"data": [{"callId": "call-1"}]}}

            with patch.object(client, "_post_json", new=AsyncMock(return_value=_FakeResponse())) as post:
                result = await client.buscar_historico_chamadas(
                    1000,
                    2000,
                    agent_id="unsupported-agent",
                    media_type="VOICE",
                    call_direction="INBOUND",
                    limit=100,
                    offset=100,
                )

            self.assertEqual(result, [{"callId": "call-1"}])
            _, payload = post.await_args.args
            self.assertEqual(
                payload,
                {
                    "ccId": 1,
                    "vdn": 25,
                    "beginDate": "1000",
                    "endDate": "2000",
                    "isCallIn": "true",
                },
            )

        asyncio.run(_run())


class TestOauthDirectMode(unittest.TestCase):
    """Cobre o fluxo HUAWEI_AUTH_MODE=oauth_direct (Bearer + tokenByAkSk)."""

    def test_token_alias_recognized(self):
        self.assertIn("token", OAUTH_DIRECT_MODES)
        self.assertIn("oauth_direct", OAUTH_DIRECT_MODES)

    def test_auth_base_url_strips_cms_port(self):
        client = _make_oauth_client()
        self.assertEqual(
            client.auth_base_url,
            "https://brazilsaas.aicccloud.com",
        )

    def test_auth_base_url_explicit_override(self):
        client = _make_oauth_client(auth_base_url="https://custom.example.com/")
        self.assertEqual(client.auth_base_url, "https://custom.example.com")

    def test_direct_credentials_fallback_to_legacy_when_missing(self):
        client = _make_oauth_client(direct_app_key=None, direct_app_secret=None)
        self.assertEqual(client.direct_app_key, client.app_key)
        self.assertEqual(client.direct_app_secret, client.app_secret)

    def test_token_alias_uses_oauth_path(self):
        async def _run():
            client = _make_oauth_client(auth_mode="token")
            with patch.object(client, "_get_token_by_aksk", new=AsyncMock(return_value="tok")) as mock_token:
                headers = await client._build_auth_headers("POST", "https://x", {})
            mock_token.assert_awaited_once()
            self.assertEqual(headers["Authorization"], "Bearer tok")
            self.assertEqual(headers["X-APP-Key"], client.direct_app_key)
            self.assertEqual(headers["X-TenantSpaceID"], client.tenant_space_id)

        asyncio.run(_run())

    def test_build_headers_omits_tenant_when_unset(self):
        async def _run():
            client = _make_oauth_client(tenant_space_id="")
            with patch.object(client, "_get_token_by_aksk", new=AsyncMock(return_value="tok")):
                headers = await client._build_auth_headers("POST", "https://x", {})
            self.assertNotIn("X-TenantSpaceID", headers)
            self.assertEqual(headers["X-APP-Key"], client.direct_app_key)

        asyncio.run(_run())

    def test_token_cache_is_reused_until_expiration(self):
        async def _run():
            client = _make_oauth_client()

            class _FakeResponse:
                status_code = 200

                @staticmethod
                def json():
                    return {"AccessToken": "abc123", "expiresIn": 3600}

            class _FakeAsyncClient:
                outer_calls = 0

                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return None

                async def post(self, *args, **kwargs):
                    type(self).outer_calls += 1
                    return _FakeResponse()

            with patch("core.huawei_client.httpx.AsyncClient", _FakeAsyncClient):
                first = await client._get_token_by_aksk()
                second = await client._get_token_by_aksk()

            self.assertEqual(first, "abc123")
            self.assertEqual(second, "abc123")
            self.assertEqual(_FakeAsyncClient.outer_calls, 1)

        asyncio.run(_run())

    def test_token_cache_refetches_after_expiry(self):
        async def _run():
            client = _make_oauth_client()
            client._cached_token = "expired"
            client._token_expires_at = time.monotonic() - 5

            class _FakeResponse:
                status_code = 200

                @staticmethod
                def json():
                    return {"AccessToken": "fresh", "expiresIn": 600}

            class _FakeAsyncClient:
                outer_calls = 0

                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return None

                async def post(self, *args, **kwargs):
                    type(self).outer_calls += 1
                    return _FakeResponse()

            with patch("core.huawei_client.httpx.AsyncClient", _FakeAsyncClient):
                token = await client._get_token_by_aksk()

            self.assertEqual(token, "fresh")
            self.assertEqual(_FakeAsyncClient.outer_calls, 1)

        asyncio.run(_run())

    def test_token_refresh_buffer_constant_is_sane(self):
        self.assertGreater(DEFAULT_TOKEN_TTL_SECONDS, TOKEN_REFRESH_BUFFER_SECONDS)

    def test_baixar_gravacao_por_callid_retries_short_id_on_failure(self):
        from unittest.mock import MagicMock
        async def _run():
            client = _make_oauth_client()
            
            # Primeira chamada (ID longo) retorna erro 0300028
            # Segunda chamada (ID curto) retorna o WAV
            resp_fail = MagicMock()
            resp_fail.status_code = 200
            resp_fail.headers = {"content-type": "application/json"}
            resp_fail.json.return_value = {"resultCode": "0300028", "resultDesc": "param error"}
            
            resp_success = MagicMock()
            resp_success.status_code = 200
            resp_success.headers = {"content-type": "audio/wav"}
            resp_success.content = b"fake-wav-content-" + b"x" * 100
            
            with patch.object(client, "_post_json", side_effect=[resp_fail, resp_success]) as mock_post:
                audio = await client.baixar_gravacao_por_callid("12345-67890")
                
            self.assertEqual(audio, resp_success.content)
            self.assertEqual(mock_post.call_count, 2)
            # Verifica se o segundo payload usou o ID curto
            self.assertEqual(mock_post.call_args_list[1][0][1]["msgBody"]["callId"], "67890")

        asyncio.run(_run())


class TestExtractCallDirection(unittest.TestCase):
    def test_top_level_iscallin_true(self):
        from core.huawei_direction import extract_is_call_in_from_response

        self.assertTrue(extract_is_call_in_from_response({"isCallIn": "true"}))

    def test_top_level_iscallin_false(self):
        from core.huawei_direction import extract_is_call_in_from_response

        self.assertFalse(extract_is_call_in_from_response({"isCallIn": "false"}))

    def test_nested_iscallin_in_result_data(self):
        from core.huawei_direction import extract_is_call_in_from_response

        self.assertTrue(
            extract_is_call_in_from_response({"resultCode": "0", "resultData": {"isCallIn": "true"}})
        )

    def test_absent_direction_returns_none(self):
        from core.huawei_direction import extract_is_call_in_from_response

        self.assertIsNone(
            extract_is_call_in_from_response({"resultData": {"callId": "x", "duration": 10}})
        )


class TestConsultarDirecaoChamada(unittest.TestCase):
    def test_returns_inbound_from_detail_response(self):
        async def _run():
            client = _make_oauth_client()

            class _FakeResp:
                status_code = 200

                @staticmethod
                def json():
                    return {"resultCode": "0100000", "resultData": {"isCallIn": "true"}}

            with patch.object(client, "_post_json", new=AsyncMock(return_value=_FakeResp())):
                return await client.consultar_direcao_chamada("1762523104-538062")

        self.assertTrue(asyncio.run(_run()))

    def test_returns_none_when_response_has_no_direction(self):
        async def _run():
            client = _make_oauth_client()

            class _FakeResp:
                status_code = 200

                @staticmethod
                def json():
                    return {"resultCode": "0100000", "resultData": {"callId": "x"}}

            with patch.object(client, "_post_json", new=AsyncMock(return_value=_FakeResp())):
                return await client.consultar_direcao_chamada("x")

        self.assertIsNone(asyncio.run(_run()))

    def test_returns_none_when_post_raises(self):
        # Robustez: se a Huawei lanca (rate limit/rede), nao propaga — devolve
        # None para o chamador cair nas defesas seguintes (pre-triagem por audio).
        async def _run():
            client = _make_oauth_client()
            with patch.object(client, "_post_json", new=AsyncMock(side_effect=RuntimeError("boom"))):
                return await client.consultar_direcao_chamada("x")

        self.assertIsNone(asyncio.run(_run()))


if __name__ == "__main__":
    unittest.main()
