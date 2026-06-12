import asyncio
import json
import os
import sys
from unittest.mock import patch


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services import AuditAlert, AuditCriterion, process_audit_with_ai


MOCK_TRANSCRIPTION = [
    {"start": "00:00", "end": "00:05", "text": "Operador: Bom dia, aqui é o operador João da Opentech."},
    {"start": "00:05", "end": "00:10", "text": "Motorista: Bom dia, sou o motorista Carlos."},
    {"start": "00:10", "end": "00:15", "text": "Operador: Por favor, me informe a sua senha de atendimento."},
    {"start": "00:15", "end": "00:20", "text": "Motorista: A senha é a contra-senha do dia."},
    {"start": "00:20", "end": "00:25", "text": "Operador: Obrigado, confirmado. Estou vendo que o senhor parou em local não autorizado."},
]


async def run_mock_test():
    print("--- Starting Mock End-to-End Test ---")

    print("\n[1] Mocking Transcription Service...")
    with patch("services.transcribe_audio", return_value=MOCK_TRANSCRIPTION), patch(
        "services.database.get_audit_by_hash",
        return_value=None,
    ), patch("services.database.save_audit"):
        alert = AuditAlert(
            id="4.1.10",
            label="Parada Indevida",
            context="Motorista parou em local de risco.",
            criteria=[
                AuditCriterion(id="1", label="Solicitar Senha", weight=50.0, description="Pedir senha no inicio"),
                AuditCriterion(id="2", label="Verificar Local", weight=50.0, description="Confirmar se o local é seguro"),
            ],
        )

        print("[2] Processing Audit (with mocked audio)...")
        print("    (This step would call the AI services with the mock transcription)")
        print(f"    Mock Input: {json.dumps(MOCK_TRANSCRIPTION, indent=2)}")

        mock_evaluation_result = {
            "summary": "Atendimento correto, solicitou senha.",
            "details": [
                {"criterionId": "1", "status": "pass", "comment": "Solicitou senha em 00:10"},
                {"criterionId": "2", "status": "pass", "comment": "Verificou local em 00:20"},
            ],
        }

        with patch("services.evaluate_with_azure", return_value=mock_evaluation_result):
            result, _, _ = await process_audit_with_ai(
                audio_file=b"dummy",
                mime_type="audio/wav",
                alert=alert,
                operator_name="João",
                operator_id="123",
                sector_id="test_sector",
            )

            print("\n[3] Audit Result:")
            print(f"    Score: {result.score} / {result.maxPossibleScore}")
            print(f"    Summary: {result.summary}")
            print(f"    Details: {len(result.details)} items")

            assert result.score == 100.0
            print("\n[SUCCESS] Mock Test Passed!")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_mock_test())
