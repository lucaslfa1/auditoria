"""Persistência da troca de tipo de alerta no PUT /api/salvos.

Mesmo estilo dos demais testes de router: mocka a camada de banco e verifica
que o endpoint chama os updaters de alerta com os argumentos certos. Cobre o
caminho vinculado (auditoria) e o comum, e garante que SEM alerta no payload
nada de alerta é tocado (comportamento legado intacto).
"""
import os
import sys
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers.saved_files import ArquivoSalvoUpdate, atualizar_salvo  # noqa: E402

_ADMIN = {"username": "admin", "role": "admin"}


class TestSavedFilesAlertEdit(unittest.TestCase):
    @patch("routers.saved_files.database.update_arquivo_alert_label")
    @patch("routers.saved_files.database.update_audit_by_id", return_value={"updated": True, "rag_payload": None})
    @patch("routers.saved_files.database.update_audit_alert")
    @patch("routers.saved_files.audits.get_audit_by_id", return_value={"id": 42})
    @patch(
        "routers.saved_files.database.get_arquivo_salvo",
        return_value={"id": 7, "tipo": "auditoria", "audit_id": 42},
    )
    def test_linked_audit_persists_alert_to_audit_and_archive(
        self,
        _mock_get_item,
        _mock_get_audit,
        mock_update_alert,
        _mock_update_audit,
        mock_update_archive_label,
    ):
        payload = ArquivoSalvoUpdate(
            conteudo="resumo",
            alert_id="UTI-PARADA-MOT",
            alert_label="Parada Indevida - Motorista",
        )

        resp = atualizar_salvo(7, payload, BackgroundTasks(), _user=_ADMIN)

        self.assertTrue(resp["success"])
        mock_update_alert.assert_called_once_with(42, "UTI-PARADA-MOT", "Parada Indevida - Motorista")
        mock_update_archive_label.assert_called_once_with(7, "Parada Indevida - Motorista")

    @patch("routers.saved_files.database.update_arquivo_alert_label")
    @patch("routers.saved_files.database.update_audit_by_id", return_value={"updated": True, "rag_payload": None})
    @patch("routers.saved_files.database.update_audit_alert")
    @patch("routers.saved_files.audits.get_audit_by_id", return_value={"id": 42})
    @patch(
        "routers.saved_files.database.get_arquivo_salvo",
        return_value={"id": 7, "tipo": "auditoria", "audit_id": 42},
    )
    def test_linked_audit_without_alert_leaves_alert_untouched(
        self,
        _mock_get_item,
        _mock_get_audit,
        mock_update_alert,
        _mock_update_audit,
        mock_update_archive_label,
    ):
        payload = ArquivoSalvoUpdate(conteudo="resumo")  # sem alerta

        atualizar_salvo(7, payload, BackgroundTasks(), _user=_ADMIN)

        mock_update_alert.assert_not_called()
        mock_update_archive_label.assert_not_called()

    @patch("routers.saved_files.database.update_arquivo_alert_label")
    @patch("routers.saved_files.database.update_arquivo_salvo", return_value=True)
    @patch(
        "routers.saved_files.database.get_arquivo_salvo",
        return_value={"id": 9, "tipo": "texto", "audit_id": None},
    )
    def test_plain_file_persists_alert_label_to_archive(
        self,
        _mock_get_item,
        _mock_update_file,
        mock_update_archive_label,
    ):
        payload = ArquivoSalvoUpdate(conteudo="nota", alert_label="Outro Alerta")

        resp = atualizar_salvo(9, payload, BackgroundTasks(), _user=_ADMIN)

        self.assertTrue(resp["success"])
        mock_update_archive_label.assert_called_once_with(9, "Outro Alerta")


if __name__ == "__main__":
    unittest.main()
