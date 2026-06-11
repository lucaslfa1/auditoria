import asyncio
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.automation as automation
import main
from core.classification import ClassificationResult
from main import app


TEST_AUTH_USERS = {
    "testuser": {
        "username": "TestUser",
        "password_hash": "s3cret-pass",
    }
}


class TestTriagemE2EFlow(unittest.TestCase):
    def test_triagem_upload_flows_into_automation_and_marks_queue_as_audited(self):
        captured_queue_item: dict = {}

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
                        sector_id="logistica",
                        sector_label="Logistica",
                        alert_id="LOGISTICA-PARADA",
                        alert_label="Parada Indevida - Motorista",
                        confidence=0.94,
                        operator_name="Operador Fluxo",
                        id_huawei="2447",
                        matricula="MAT-44",
                        needs_review=False,
                        review_reasons=[],
                        review_priority="low",
                    )

                    def _capture_sync(**kwargs):
                        captured_queue_item.update(
                            {
                                "input_hash": kwargs["input_hash"],
                                "nome_arquivo": kwargs["nome_arquivo"],
                                "setor_previsto": kwargs["setor_previsto"],
                                "alerta_previsto": kwargs["alerta_previsto"],
                                "confianca": kwargs["confianca"],
                                "operador_previsto": kwargs["operador_previsto"],
                                "erro": kwargs["erro"],
                                "prioridade": kwargs["prioridade"],
                                "motivos_revisao": kwargs["motivos_revisao"],
                                "metadata": kwargs["metadata"],
                                "status": "auto_resolved",
                            }
                        )
                        return 101

                    with patch.object(main, "classify_multiple_audios", return_value=[mocked_result]), patch.object(main.database, "obter_fila_revisao_classificacao_por_hash", return_value=None), patch.object(main.database, "sincronizar_fila_revisao_classificacao", side_effect=_capture_sync) as mock_sync, patch.object(main.database, "get_ligacao_auditada_por_hash", return_value=None), patch("routers.classifier.store_classified_audio", return_value="captured.wav"):
                        response = await client.post(
                            "/api/classify",
                            files=[("files", ("call.wav", b"RIFFdemo-audio", "audio/wav"))],
                        )

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(len(payload["results"]), 1)
                    self.assertEqual(payload["results"][0]["sector_id"], "logistica")
                    self.assertEqual(payload["results"][0]["alert_id"], "LOGISTICA-PARADA")
                    self.assertFalse(payload["results"][0]["needs_review"])
                    self.assertEqual(payload["results"][0]["input_hash"], captured_queue_item["input_hash"])
                    mock_sync.assert_called_once()

            fake_services = types.ModuleType("services")
            fake_services.process_audit_with_ai = AsyncMock(
                # selected_strategy obrigatoria desde a politica do candidate
                # selector (_satisfies_transcription_policy).
                return_value=(
                    SimpleNamespace(
                        score=8.5,
                        maxPossibleScore=10.0,
                        audio_quality={"transcription_provider": {"selected_strategy": "fast"}},
                    ),
                    "audit-hash-e2e",
                    False,
                )
            )

            with patch.object(automation.database, "listar_fila_revisao_classificacao", return_value=[captured_queue_item]), patch("repositories.operators.resolve_auditable_colaborador", return_value={"name": "Operador Teste", "preferredId": "", "matricula": ""}), patch("repositories.audits.get_audit_by_hash", return_value=None), patch.object(automation.database, "persist_audit_artifacts", return_value=501) as mock_persist, patch.object(automation.database, "atualizar_status_fila_revisao_classificacao") as mock_update_status, patch.object(automation, "load_classified_audio", return_value=b"RIFFdemo-audio"), patch.object(automation, "compute_input_hash", return_value="audit-hash-e2e"), patch.object(automation, "get_mime_type", return_value="audio/wav"), patch.object(automation.asyncio, "sleep", new_callable=AsyncMock), patch.dict(sys.modules, {"services": fake_services}):
                result = await automation.audit_all_pending()

            self.assertEqual(result["total"], 1)
            self.assertEqual(result["completed"], 1)
            self.assertEqual(result["failed"], 0)
            mock_persist.assert_called_once()
            mock_update_status.assert_called_once()
            _, kwargs = mock_update_status.call_args
            self.assertEqual(kwargs["status"], "audited")
            self.assertEqual(kwargs["metadata_merge"]["audit_id"], 501)
            self.assertEqual(kwargs["metadata_merge"]["audit_input_hash"], "audit-hash-e2e")

        asyncio.run(flow())


if __name__ == "__main__":
    unittest.main()
