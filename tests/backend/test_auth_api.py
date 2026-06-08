from repositories import operators
import os
import sys
import unittest
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, ANY

import httpx

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.classification import ClassificationResult  # noqa: E402
import main  # noqa: E402
from main import app, SESSION_COOKIE_NAME  # noqa: E402
from routers import auth as auth_router  # noqa: E402


TEST_AUTH_USERS = {
    "testuser": {
        "username": "TestUser",
        "password_hash": "s3cret-pass",
    }
}

ROLE_AUTH_USERS = {
    "admin": {
        "username": "Admin",
        "password_hash": "admin-pass",
        "role": "admin",
        "supervisor_name": "",
    },
    "supervisora": {
        "username": "Supervisora",
        "password_hash": "super-pass",
        "role": "supervisor",
        "supervisor_name": "Maria Silva",
    },
    "outrosupervisor": {
        "username": "OutroSupervisor",
        "password_hash": "other-pass",
        "role": "supervisor",
        "supervisor_name": "Joao Lima",
    },
}

GESTORES_AUDITS = [
    {
        "id": 1,
        "timestamp": "2026-03-03T09:00:00",
        "operator_name": "Operador A",
        "operator_id": "1",
        "score": 80.0,
        "max_score": 100.0,
        "summary": "Auditoria do supervisor correto",
        "details": "[]",
        "alert_id": "4.1.1",
        "alert_label": "Alerta A",
        "sector_id": "uti",
        "status": "pending_approval",
        "supervisor": "Maria Silva",
        "escala": "MANHA",
    },
    {
        "id": 2,
        "timestamp": "2026-03-03T08:00:00",
        "operator_name": "Operador B",
        "operator_id": "2",
        "score": 60.0,
        "max_score": 100.0,
        "summary": "Auditoria de outro supervisor",
        "details": "[]",
        "alert_id": "4.1.2",
        "alert_label": "Alerta B",
        "sector_id": "transferencia",
        "status": "pending_approval",
        "supervisor": "Joao Lima",
        "escala": "TARDE",
    },
]


class TestAuthApi(unittest.TestCase):
    async def _request(self, method: str, url: str, **kwargs):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, url, **kwargs)

    def test_public_health_route_is_accessible(self):
        response = asyncio.run(self._request("GET", "/api/health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "online")

    def test_load_session_secret_uses_ephemeral_value_outside_production(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "SESSION_SECRET": ""}, clear=False):
            first = auth_router._load_session_secret()
            second = auth_router._load_session_secret()

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertNotEqual(first, "dev-session-secret-local-only")
        self.assertNotEqual(first, second)

    def test_protected_route_requires_authentication(self):
        response = asyncio.run(self._request("GET", "/api/dashboard/history"))
        self.assertEqual(response.status_code, 401)

    def test_login_me_logout_session_flow(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    bad_login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "wrong-password"},
                    )
                    self.assertEqual(bad_login.status_code, 401)

                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                    self.assertEqual(login.status_code, 200)
                    self.assertEqual(login.json()["username"], "TestUser")
                    self.assertIsNotNone(client.cookies.get(SESSION_COOKIE_NAME))

                    me = await client.get("/api/auth/me")
                    self.assertEqual(me.status_code, 200)
                    self.assertTrue(me.json()["authenticated"])
                    self.assertEqual(me.json()["username"], "TestUser")

                    logout = await client.post("/api/auth/logout")
                    self.assertEqual(logout.status_code, 200)
                    self.assertTrue(logout.json()["success"])

                    me_after_logout = await client.get("/api/auth/me")
                    self.assertEqual(me_after_logout.status_code, 200)
                    self.assertFalse(me_after_logout.json()["authenticated"])

        asyncio.run(flow())

    def test_login_cookie_can_disable_secure_flag_for_local_http(self):
        with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
            with patch.dict(os.environ, {"ENVIRONMENT": "production", "SESSION_COOKIE_SECURE": "false"}, clear=False):
                response = asyncio.run(
                    self._request(
                        "POST",
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Secure", response.headers.get("set-cookie", ""))

    def test_deleted_user_session_is_rejected(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                with patch("routers.auth.auth_users.get_user_by_username", return_value=None):
                    me = await client.get("/api/auth/me")
                    self.assertEqual(me.status_code, 200)
                    self.assertFalse(me.json()["authenticated"])

        asyncio.run(flow())

    def test_me_without_session_returns_unauthenticated_payload(self):
        response = asyncio.run(self._request("GET", "/api/auth/me"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["authenticated"])

    def test_admin_only_config_routes_block_supervisor(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "Supervisora", "password": "super-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                    get_response = await client.get("/api/configuracoes")
                    self.assertEqual(get_response.status_code, 403)

                    post_response = await client.post(
                        "/api/configuracoes",
                        json={"chave": "ia_prompt_global", "valor": "novo valor"},
                    )
                    self.assertEqual(post_response.status_code, 403)

        asyncio.run(flow())

    def test_admin_only_saved_files_routes_block_supervisor(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "Supervisora", "password": "super-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                    list_response = await client.get("/api/salvos")
                    self.assertEqual(list_response.status_code, 403)

                    create_response = await client.post(
                        "/api/salvos",
                        json={"tipo": "Auditoria", "conteudo": "teste"},
                    )
                    self.assertEqual(create_response.status_code, 403)

        asyncio.run(flow())

    def test_admin_can_read_and_update_configs(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "Admin", "password": "admin-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)):
                    with patch("main.database.get_all_configs", return_value={"ia_prompt_global": {"valor": "x", "descricao": "y"}}) as mock_get:
                        get_response = await client.get("/api/configuracoes")
                        self.assertEqual(get_response.status_code, 200)
                        self.assertIn("ia_prompt_global", get_response.json())
                        mock_get.assert_called_once()

                    with patch("main.database.update_config", return_value=True) as mock_update:
                        post_response = await client.post(
                            "/api/configuracoes",
                            json={"chave": "ia_prompt_global", "valor": "novo valor"},
                        )
                        self.assertEqual(post_response.status_code, 200)
                        self.assertEqual(post_response.json()["status"], "success")
                        mock_update.assert_called_once_with("ia_prompt_global", "novo valor", alterado_por="Admin", motivo="", origem="ui")

        asyncio.run(flow())

    def test_authenticated_user_can_read_safe_ui_theme_config(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "Supervisora", "password": "super-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)):
                    with patch("main.database.get_config_value", return_value="nstech") as mock_get:
                        response = await client.get("/api/ui/theme")
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json(), {"preset": "nstech"})
                        mock_get.assert_called_once_with("tema_visual", "corporativo")

        asyncio.run(flow())

    def test_admin_can_list_saved_files(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "Admin", "password": "admin-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                saved_items = [{"id": 1, "tipo": "Auditoria", "conteudo": "teste", "criado_por": "admin"}]
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)):
                    with patch("main.database.list_arquivos_salvos", return_value=saved_items) as mock_list:
                        with patch("main.database.count_arquivos_salvos", return_value=1) as mock_count:
                            response = await client.get("/api/salvos")
                            self.assertEqual(response.status_code, 200)
                            self.assertEqual(response.json()["total"], 1)
                            self.assertEqual(response.json()["items"], saved_items)
                            mock_list.assert_called_once_with(limit=100, offset=0, tipo=None, include_audits=True)
                            mock_count.assert_called_once_with(tipo=None, include_audits=True)

        asyncio.run(flow())

    def test_supervisor_listing_is_scoped_server_side(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    with patch.object(main.database, "get_audits_for_export", side_effect=lambda **kwargs: [a for a in GESTORES_AUDITS if a["supervisor"] == kwargs.get("supervisor")] if kwargs.get("supervisor") else GESTORES_AUDITS):
                        with patch("routers.supervisor.get_indicators_by_supervisor", return_value=[{"supervisor": "Maria Silva", "total_auditorias": 1, "media_percentual": 80.0}]):
                            with patch.object(main.database, "get_gestor_feedback", return_value=None):
                                login = await client.post(
                                    "/api/auth/login",
                                    json={"username": "Supervisora", "password": "super-pass"},
                                )
                                self.assertEqual(login.status_code, 200)

                                response = await client.get(
                                    "/api/gestores/auditorias",
                                    params={"supervisor": "Joao Lima"},
                                )
                                self.assertEqual(response.status_code, 200)

                                payload = response.json()
                                self.assertEqual(payload["kpis"]["total_auditorias"], 1)
                                self.assertEqual([audit["id"] for audit in payload["auditorias"]], [1])

        asyncio.run(flow())

    def test_supervisor_rh_supervisores_is_scoped_server_side(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "Supervisora", "password": "super-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)):
                    with patch("repositories.operators.get_supervisores_e_escalas", return_value={"Maria Silva": ["MANHA"], "Joao Lima": ["TARDE"]}):
                        response = await client.get("/api/rh/supervisores")

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"Maria Silva": ["MANHA"]})

        asyncio.run(flow())

    def test_supervisor_feedback_routes_reject_out_of_scope_audit(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    with patch("repositories.audits.get_audit_by_id", side_effect=lambda c, id: next((a for a in GESTORES_AUDITS if a["id"] == id), None)):
                        with patch.object(main.database, "save_gestor_feedback", return_value=True) as mock_save:
                            with patch.object(
                                main.database,
                                "get_gestor_feedback",
                                return_value={
                                    "id": 10,
                                    "audit_id": 1,
                                    "gestor_nome": "Maria Silva",
                                    "feedback_texto": "Bom trabalho",
                                    "pontos_melhoria": "Continuar",
                                    "criado_em": "2026-03-03 10:00:00",
                                },
                            ) as mock_get:
                                login = await client.post(
                                    "/api/auth/login",
                                    json={"username": "Supervisora", "password": "super-pass"},
                                )
                                self.assertEqual(login.status_code, 200)

                                denied_post = await client.post(
                                    "/api/gestores/feedback",
                                    json={
                                        "audit_id": 2,
                                        "gestor_nome": "Maria Silva",
                                        "feedback_texto": "Nao deveria salvar",
                                        "pontos_melhoria": "Nao aplicar",
                                    },
                                )
                                self.assertEqual(denied_post.status_code, 403)
                                mock_save.assert_not_called()

                                denied_get = await client.get("/api/gestores/feedback/2")
                                self.assertEqual(denied_get.status_code, 403)
                                mock_get.assert_not_called()

                                allowed_post = await client.post(
                                    "/api/gestores/feedback",
                                    json={
                                        "audit_id": 1,
                                        "gestor_nome": "Maria Silva",
                                        "feedback_texto": "Bom trabalho",
                                        "pontos_melhoria": "Continuar",
                                    },
                                )
                                self.assertEqual(allowed_post.status_code, 200)
                                mock_save.assert_called_once_with(1, "Maria Silva", "Bom trabalho", "Continuar")

                                allowed_get = await client.get("/api/gestores/feedback/1")
                                self.assertEqual(allowed_get.status_code, 200)
                                self.assertEqual(allowed_get.json()["audit_id"], 1)

        asyncio.run(flow())

    def test_supervisor_cannot_approve_or_contest_out_of_scope_audit(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    with patch("repositories.audits.get_audit_by_id", side_effect=lambda c, id: next((a for a in GESTORES_AUDITS if a["id"] == id), None)):
                        with patch("repositories.audits.update_audit_status") as mock_update:
                            login = await client.post(
                                "/api/auth/login",
                                json={"username": "Supervisora", "password": "super-pass"},
                            )
                            self.assertEqual(login.status_code, 200)

                            denied_approve = await client.post("/api/gestores/auditorias/2/approve")
                            self.assertEqual(denied_approve.status_code, 403)

                            denied_contest = await client.post(
                                "/api/gestores/auditorias/2/contest",
                                json={"reason": "Nao e da minha equipe"},
                            )
                            self.assertEqual(denied_contest.status_code, 403)
                            mock_update.assert_not_called()

                            allowed_approve = await client.post("/api/gestores/auditorias/1/approve")
                            self.assertEqual(allowed_approve.status_code, 200)
                            mock_update.assert_called_once_with(ANY, 1, "approved", None, None)

        asyncio.run(flow())

    def test_supervisor_cannot_approve_contestation_pending_review(self):
        async def flow():
            contested_audit = {
                **GESTORES_AUDITS[0],
                "status": "contestation_pending_review",
                "contestation_reason": "Supervisor questionou a nota",
            }
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    with patch("repositories.audits.get_audit_by_id", return_value=contested_audit):
                        with patch("repositories.audits.update_audit_status") as mock_update:
                            login = await client.post(
                                "/api/auth/login",
                                json={"username": "Supervisora", "password": "super-pass"},
                            )
                            self.assertEqual(login.status_code, 200)

                            response = await client.post("/api/gestores/auditorias/1/approve")

                            self.assertEqual(response.status_code, 400)
                            mock_update.assert_not_called()

        asyncio.run(flow())

    def test_supervisor_audio_route_is_scoped_server_side(self):
        async def flow():
            with tempfile.TemporaryDirectory() as storage_dir:
                relative_path = Path("2026") / "03" / "audit_1_test.wav"
                stored_file = Path(storage_dir) / relative_path
                stored_file.parent.mkdir(parents=True, exist_ok=True)
                stored_file.write_bytes(b"RIFFsupervisor-audio")

                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    with patch.dict(os.environ, {"AUDIT_AUDIO_STORAGE_DIR": storage_dir}, clear=False):
                        with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                            with patch("repositories.audits.get_audit_by_id", side_effect=lambda c, id: next((a for a in GESTORES_AUDITS if a["id"] == id), None)):
                                with patch.object(
                                    main.database,
                                    "get_audit_media_record",
                                    return_value={
                                        "id": 1,
                                        "audio_storage_path": str(relative_path).replace("\\", "/"),
                                        "audio_original_filename": "chamada.wav",
                                        "audio_mime_type": "audio/wav",
                                        "audio_size_bytes": len(b"RIFFsupervisor-audio"),
                                    },
                                ):
                                    login = await client.post(
                                        "/api/auth/login",
                                        json={"username": "Supervisora", "password": "super-pass"},
                                    )
                                    self.assertEqual(login.status_code, 200)

                                    allowed = await client.get("/api/audit/1/audio")
                                    self.assertEqual(allowed.status_code, 200)
                                    self.assertEqual(allowed.content, b"RIFFsupervisor-audio")

                                    denied = await client.get("/api/audit/2/audio")
                                    self.assertEqual(denied.status_code, 403)

        asyncio.run(flow())

    def test_audit_upload_rejects_unsupported_file_type(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                    self.assertEqual(login.status_code, 200)
                    with patch("routers.audit.get_operator_audit_count_for_month", return_value=0):
                        response = await client.post(
                            "/api/audit",
                            data={
                                "alert_json": json.dumps(
                                    {
                                        "id": "teste",
                                        "label": "Teste",
                                        "context": "Contexto",
                                        "criteria": [{"id": "c1", "label": "Critério", "weight": 1.0}],
                                    }
                                ),
                                "operator_name": "Test Operator",
                            },
                            files={"file": ("arquivo.txt", b"conteudo invalido", "text/plain")},
                        )
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("Formato de arquivo", response.json()["detail"])

        asyncio.run(flow())

    def test_classify_rejects_unsupported_file_type(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                    self.assertEqual(login.status_code, 200)
                    response = await client.post(
                        "/api/classify",
                        files=[("files", ("arquivo.txt", b"conteudo invalido", "text/plain"))],
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("triagem", response.json()["detail"])

        asyncio.run(flow())

    def test_classify_returns_review_flags_and_syncs_review_queue(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                    mocked_result = ClassificationResult(
                        filename="call.wav",
                        sector_id="desconhecido",
                        sector_label="Nao Identificado",
                        alert_id="desconhecido",
                        alert_label="Audio curto/sem fala",
                        confidence=0.0,
                        error="Short transcription",
                        needs_review=True,
                        review_reasons=["erro_classificacao", "setor_nao_identificado", "baixa_confianca"],
                        review_priority="high",
                    )

                    with patch.dict(os.environ, {"AZURE_OPENAI_DEPLOYMENT": "gpt-4o-test"}, clear=False):
                        with patch.object(main, "classify_multiple_audios", return_value=[mocked_result]):
                            with patch.object(main.database, "sincronizar_fila_revisao_classificacao") as mock_sync:
                                with patch.object(
                                    main.database,
                                    "get_ligacao_auditada_por_hash",
                                    return_value={
                                        "id": 321,
                                        "setor_referencia": None,
                                        "alerta_referencia": None,
                                    },
                                ):
                                    with patch.object(main.database, "registrar_resultado_classificacao") as mock_register:
                                        response = await client.post(
                                            "/api/classify",
                                            files=[("files", ("call.wav", b"RIFF....", "audio/wav"))],
                                        )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(len(payload["results"]), 1)
                    self.assertTrue(payload["results"][0]["needs_review"])
                    self.assertEqual(payload["results"][0]["review_priority"], "high")
                    self.assertIn("baixa_confianca", payload["results"][0]["review_reasons"])
                    mock_sync.assert_called_once()
                    mock_register.assert_called_once()
                    self.assertEqual(mock_register.call_args.kwargs["modelo"], "gpt-4o-test")

        asyncio.run(flow())

    def test_classify_reuses_existing_queue_item_as_repeated_call(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                    existing_queue_item = {
                        "id": 5,
                        "input_hash": "hash-repeat",
                        "nome_arquivo": "call-repeat.wav",
                        "setor_previsto": "logistica",
                        "alerta_previsto": "LOGISTICA-PARADA",
                        "confianca": 0.93,
                        "operador_previsto": "Operador Repetido",
                        "erro": None,
                        "prioridade": "low",
                        "motivos_revisao": [],
                        "metadata": {"manual_review_source": "triagem_ui"},
                        "status": "reviewed",
                        "criado_em": "2026-04-08T09:00:00",
                        "atualizado_em": "2026-04-08T09:05:00",
                    }
                    catalog = {
                        "logistica": {
                            "label": "Logistica",
                            "alerts": [
                                {"id": "LOGISTICA-PARADA", "label": "Parada Indevida - Motorista"},
                            ],
                        }
                    }

                    with patch("routers.classifier.load_audit_criteria_catalog", return_value=catalog), patch.object(main.database, "obter_fila_revisao_classificacao_por_hash", return_value=existing_queue_item) as mock_existing, patch.object(main, "classify_multiple_audios") as mock_classify, patch.object(main.database, "sincronizar_fila_revisao_classificacao") as mock_sync:
                        response = await client.post(
                            "/api/classify",
                            files=[("files", ("call-repeat.wav", b"RIFF....", "audio/wav"))],
                        )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(len(payload["results"]), 1)
                    result = payload["results"][0]
                    self.assertTrue(result["duplicate"])
                    self.assertEqual(result["duplicate_label"], "Ligacao repetida")
                    self.assertEqual(result["duplicate_reason"], "already_in_queue")
                    self.assertEqual(result["status"], "reviewed")
                    self.assertEqual(result["sector_id"], "logistica")
                    self.assertEqual(result["alert_id"], "LOGISTICA-PARADA")
                    mock_existing.assert_called_once()
                    mock_classify.assert_not_called()
                    mock_sync.assert_not_called()

        asyncio.run(flow())

    def test_dashboard_review_queue_endpoint_requires_auth_and_returns_payload(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                denied = await client.get("/api/dashboard/classificacao-revisao")
                self.assertEqual(denied.status_code, 401)

                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                    expected_payload = [
                        {
                            "id": 1,
                            "input_hash": "hash-1",
                            "nome_arquivo": "call.wav",
                            "setor_previsto": "logistica",
                            "alerta_previsto": "4.4.1",
                            "confianca": 0.64,
                            "operador_previsto": None,
                            "erro": None,
                            "prioridade": "medium",
                            "motivos_revisao": ["baixa_confianca"],
                            "metadata": {"filename_upload": "call.wav"},
                            "status": "pending",
                            "criado_em": "2026-03-04T10:00:00",
                            "atualizado_em": "2026-03-04T10:00:00",
                        }
                    ]

                    with patch.object(main.database, "listar_fila_revisao_classificacao", return_value=expected_payload) as mock_list:
                        response = await client.get(
                            "/api/dashboard/classificacao-revisao",
                            params={"limit": 8, "status": "pending", "sector_id": "logistica"},
                        )

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), expected_payload)
                    mock_list.assert_called_once_with(limit=8, status="pending", sector_id="logistica")

        asyncio.run(flow())

    def test_manual_classification_correction_requires_auth_and_persists_reviewed_result(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                denied = await client.patch(
                    "/api/classify/hash-123",
                    json={"sector_id": "logistica", "alert_id": "LOGISTICA-PARADA"},
                )
                self.assertEqual(denied.status_code, 401)

                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                    catalog = {
                        "logistica": {
                            "label": "Logistica",
                            "alerts": [
                                {"id": "LOGISTICA-PARADA", "label": "Parada Indevida - Motorista"},
                            ],
                        }
                    }
                    updated_queue_item = {
                        "nome_arquivo": "call.wav",
                        "input_hash": "hash-123",
                        "setor_previsto": "logistica",
                        "alerta_previsto": "LOGISTICA-PARADA",
                        "confianca": 0.77,
                        "operador_previsto": "Operador Teste",
                        "erro": None,
                        "status": "reviewed",
                    }

                    with patch("routers.classifier.load_audit_criteria_catalog", return_value=catalog), patch.object(main.database, "corrigir_classificacao_fila_revisao", return_value=updated_queue_item) as mock_correct, patch.object(main.database, "get_ligacao_auditada_por_hash", return_value=None):
                        response = await client.patch(
                            "/api/classify/hash-123",
                            json={"sector_id": "logistica", "alert_id": "LOGISTICA-PARADA"},
                        )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()["result"]
                    self.assertEqual(payload["input_hash"], "hash-123")
                    self.assertEqual(payload["sector_id"], "logistica")
                    self.assertEqual(payload["alert_id"], "LOGISTICA-PARADA")
                    self.assertFalse(payload["needs_review"])
                    self.assertEqual(payload["status"], "reviewed")
                    mock_correct.assert_called_once()

        asyncio.run(flow())

    def test_review_routes_are_admin_only_and_finalize_contestation(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                denied = await client.get("/api/revisao/contestacoes")
                self.assertEqual(denied.status_code, 401)

                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    supervisor_login = await client.post(
                        "/api/auth/login",
                        json={"username": "Supervisora", "password": "super-pass"},
                    )
                    self.assertEqual(supervisor_login.status_code, 200)

                    forbidden = await client.get("/api/revisao/contestacoes")
                    self.assertEqual(forbidden.status_code, 403)

                    await client.post("/api/auth/logout")

                    admin_login = await client.post(
                        "/api/auth/login",
                        json={"username": "Admin", "password": "admin-pass"},
                    )
                    self.assertEqual(admin_login.status_code, 200)

                    expected_audits = [
                        {
                            "id": 11,
                            "operator_name": "Operador Revisao",
                            "status": "contestation_pending_review",
                            "contestation_reason": "Supervisor questionou a nota",
                        }
                    ]
                    with patch("routers.review.audits.get_audits_for_export", return_value=expected_audits) as mock_list:
                        listed = await client.get("/api/revisao/contestacoes", params={"limit": 50})

                    self.assertEqual(listed.status_code, 200)
                    self.assertEqual(listed.json()["contestacoes"], expected_audits)
                    mock_list.assert_called_once_with(
                        ANY,
                        month=None,
                        year=None,
                        supervisor=None,
                        sector_id=None,
                        operator_name=None,
                        statuses=["contestation_pending_review"],
                    )

                    with patch(
                        "routers.review.audits.finalize_contestation_review",
                        return_value={
                            "audit_id": 11,
                            "status": "approved",
                            "contestation_verdict": "rejected",
                            "review_defense": "A nota original foi mantida.",
                            "reviewed_by": "Admin",
                        },
                    ) as mock_finalize:
                        finalized = await client.post(
                            "/api/revisao/auditorias/11/veredito",
                            json={"verdict": "rejected", "defense": "A nota original foi mantida."},
                        )

                    self.assertEqual(finalized.status_code, 200)
                    self.assertTrue(finalized.json()["success"])
                    mock_finalize.assert_called_once_with(
                        ANY,
                        11,
                        verdict="rejected",
                        defense="A nota original foi mantida.",
                        reviewed_by="Admin",
                        updated_details=None,
                    )

        asyncio.run(flow())

    def test_dashboard_summary_endpoint_forwards_sector_filter(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                expected_payload = {
                    "total_ligacoes": 1,
                    "classificadas": 1,
                    "qualidade": {"boa": 1, "ruim": 0, "zerada": 0, "indefinida": 0},
                    "por_setor": [{"setor": "bas", "total": 1}],
                    "taxa_acerto_setor": 100.0,
                    "taxa_acerto_alerta": 100.0,
                }

                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)):
                    with patch.object(main.database, "get_resumo_ligacoes_auditadas", return_value=expected_payload) as mock_summary:
                        response = await client.get(
                            "/api/dashboard/ligacoes-auditadas/resumo",
                            params={"sector_id": "bas"},
                        )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), expected_payload)
                mock_summary.assert_called_once_with("bas")

        asyncio.run(flow())

    def test_dashboard_imported_calls_endpoint_accepts_sector_id_alias(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    login = await client.post(
                        "/api/auth/login",
                        json={"username": "TestUser", "password": "s3cret-pass"},
                    )
                    self.assertEqual(login.status_code, 200)

                expected_payload = [{"id": 1, "nome_arquivo": "call.wav"}]

                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: TEST_AUTH_USERS.get(u)):
                    with patch.object(main.database, "listar_ligacoes_auditadas", return_value=expected_payload) as mock_list:
                        response = await client.get(
                            "/api/dashboard/ligacoes-auditadas",
                            params={"limit": 8, "sector_id": "bas"},
                        )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), expected_payload)
                mock_list.assert_called_once_with(limit=8, qualidade=None, setor="bas")

        asyncio.run(flow())

    def test_dashboard_save_requires_admin_and_queues_first_audit(self):
        payload = {
            "score": 8.0,
            "maxPossibleScore": 10.0,
            "summary": "Auditoria para revisão",
            "details": [
                {
                    "criterionId": "CR01",
                    "label": "Saudação",
                    "status": "pass",
                    "weight": 1.0,
                    "obtainedScore": 1.0,
                    "comment": "OK",
                }
            ],
            "transcription": [
                {"start": "00:00", "end": "00:03", "text": "Operador: bom dia"}
            ],
            "operatorId": "OP-100",
            "operatorName": "Operador QA",
            "timestamp": "2026-03-08T15:00:00",
            "source_type": "audio",
            "audit_scope": "call_quality",
        }

        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    supervisor_login = await client.post(
                        "/api/auth/login",
                        json={"username": "Supervisora", "password": "super-pass"},
                    )
                    self.assertEqual(supervisor_login.status_code, 200)

                    denied = await client.post("/api/dashboard/save?status=approved", json=payload)
                    self.assertEqual(denied.status_code, 403)

                await client.post("/api/auth/logout")

                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)), patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                    admin_login = await client.post(
                        "/api/auth/login",
                        json={"username": "Admin", "password": "admin-pass"},
                    )
                    self.assertEqual(admin_login.status_code, 200)

                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: ROLE_AUTH_USERS.get(u)):
                    with patch.object(
                        main.database,
                        "queue_audit_for_supervisor_review",
                        return_value={"audit_id": 10, "status": "awaiting_pair", "open_count": 1},
                    ) as mock_queue:
                        saved = await client.post("/api/dashboard/save?status=approved", json=payload)

                self.assertEqual(saved.status_code, 200)
                self.assertEqual(saved.json()["success"], True)
                self.assertEqual(saved.json()["review_status"], "awaiting_pair")
                mock_queue.assert_called_once()

        asyncio.run(flow())

    def test_generate_supervisor_accounts_skips_existing_supervisor_names(self):
        async def flow():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                auth_users = {
                    "admin": ROLE_AUTH_USERS["admin"].copy(),
                    "maria silva": {
                        "username": "Maria Silva",
                        "password_hash": "hash",
                        "role": "supervisor",
                        "supervisor_name": "Maria Silva",
                    },
                }

                # Mock do banco para login
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: auth_users.get(u)):
                    with patch("bcrypt.checkpw", side_effect=lambda p, h: p == h):
                        login = await client.post(
                            "/api/auth/login",
                            json={"username": "Admin", "password": "admin-pass"},
                        )
                        self.assertEqual(login.status_code, 200)

                # Mock do banco para criação de usuários
                with patch("routers.auth.auth_users.get_user_by_username", side_effect=lambda c, u: auth_users.get(u)):
                    with patch("repositories.operators.get_supervisores_e_escalas", return_value={"Maria Silva": ["MANHA"], "Joao Lima": ["TARDE"]}):
                        from unittest.mock import MagicMock
                        mock_conn = MagicMock()
                        mock_cursor = MagicMock()
                        mock_conn.cursor.return_value = mock_cursor
                        # Retorna os existentes ("Maria Silva", "admin")
                        mock_cursor.fetchall.return_value = [("Maria Silva", "maria silva"), (None, "admin")]
                        
                        with patch("main.database.get_connection", return_value=mock_conn):
                            with patch("main._generate_temporary_password", return_value="TempPass!234"):
                                with patch("routers.admin.auth_users.create_user", return_value=True) as mock_create_user:
                                    response = await client.post("/api/admin/generate-supervisor-accounts")
                                    
                                    self.assertEqual(response.status_code, 200)
                                    self.assertEqual(response.json()["created"], 1)
                                    self.assertEqual(response.json()["usernames"], ["Joao Lima"])
                                    self.assertEqual(
                                        response.json()["credentials"],
                                        [{"username": "Joao Lima", "temporary_password": "TempPass!234"}],
                                    )
                                    
                                    # Verifica se Joao Lima foi criado e Maria Silva ignorada
                                    from unittest.mock import ANY
                                    mock_create_user.assert_called_once_with(ANY, "Joao Lima", "TempPass!234", "supervisor", "Joao Lima")

        asyncio.run(flow())


if __name__ == "__main__":
    unittest.main()



