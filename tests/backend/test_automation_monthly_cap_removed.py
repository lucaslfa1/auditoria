"""Cota mensal saiu da fase de auditoria.

Por padrao (AUTOMATION_AUDIT_IGNORE_MONTHLY_CAP ON) a IA audita tudo que presta e deixa
em awaiting_pair; a cota 2/mes e compliance apenas no ENVIO ao supervisor. Rollback (OFF)
restaura o gate monthly_capped na auditoria.
"""
import asyncio
import contextlib
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import automation


def _ctx():
    return SimpleNamespace(
        filename="c.wav",
        sector_id="logistica",
        alert_id="4.4.1",
        alert_label="",
        operator_name="Op",
        operator_id="M1",
        source_type="audio",
        media_path="c.wav",
        to_audit_metadata=lambda: {},
    )


def _item():
    return {
        "input_hash": "h-cap",
        "nome_arquivo": "c.wav",
        "setor_previsto": "logistica",
        "alerta_previsto": "4.4.1",
        "operador_previsto": "Op",
        "metadata": {"classified_audio_path": "c.wav"},
    }


class TestMonthlyCapRemoved(unittest.TestCase):
    def _run(self, env):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(automation, "repair_queue_audit_context", return_value=_ctx()))
            stack.enter_context(
                patch(
                    "core.automation_operator.OperatorGatekeeper.resolve_operator",
                    return_value=SimpleNamespace(
                        is_valid=True,
                        operator_name="Op",
                        operator_id="M1",
                        resolved_operator_dict={},
                        block_message=None,
                        block_reason=None,
                        motivos_revisao_append=[],
                        metadata_merge={},
                    ),
                )
            )
            stack.enter_context(patch.object(automation, "apply_resolved_operator"))
            stack.enter_context(patch.object(automation, "load_classified_audio", return_value=b"audio"))
            stack.enter_context(
                patch.object(
                    automation,
                    "_build_alert_from_classification",
                    return_value=SimpleNamespace(label="A", criteria=[SimpleNamespace(id="c", label="c")], id="4.4.1"),
                )
            )
            stack.enter_context(patch.object(automation, "compute_input_hash", return_value="audit-hash"))
            mock_check = stack.enter_context(
                patch(
                    "core.automation_operator.QuotaGatekeeper.check_quota",
                    return_value={
                        "block_reason": "monthly_capped",
                        "block_message": "cota atingida",
                        "motivos_revisao_append": ["cota_mensal_atingida"],
                        "metadata_merge": {},
                    },
                )
            )
            # curto-circuita no cache para nao tocar rede/IA — se chegou aqui, a cota nao barrou.
            stack.enter_context(
                patch(
                    "core.automation_cache.AuditCacheGatekeeper.check_existing_audit",
                    return_value={"status": "audited", "audit_id": 7},
                )
            )
            stack.enter_context(patch.dict(os.environ, env, clear=False))
            result = asyncio.run(automation._audit_single_item(_item()))
        return result, mock_check

    def test_flag_on_ignora_cota_e_segue_para_auditoria(self):
        result, mock_check = self._run({"AUTOMATION_AUDIT_IGNORE_MONTHLY_CAP": "true"})
        self.assertEqual(result["status"], "audited")
        mock_check.assert_not_called()

    def test_flag_off_restaura_gate_de_cota(self):
        result, mock_check = self._run({"AUTOMATION_AUDIT_IGNORE_MONTHLY_CAP": "false"})
        self.assertEqual(result["status"], "monthly_capped")
        mock_check.assert_called_once()


if __name__ == "__main__":
    unittest.main()
