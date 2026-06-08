"""Testes para os 8 fixes criticos da v1.3.73.

Cobre:
- #2/#5 hybrid_dual sobrevive a falha parcial e propaga sub_strategy
- #3 bonus do hybrid_dual reduzido para 1500 (e nao 50000)
- #5 merge_transcriptions_with_gpt4o retorna tupla (segments, status)
- #6 _build_alert_from_classification resolve alias BAS-POLICIAL e exige criterios no DB
- #7 _expected_direction_for_alert dispara per-alert por keyword
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.automation as automation
import core.classification as classification
from schemas import AuditAlert, AuditCriterion
from core.audit import _resolve_official_audit_alert
from core.transcription import merge_transcriptions_with_gpt4o


class TestAliasResolutionInBuildAlert(unittest.TestCase):
    """Fix #6: alias BAS-POLICIAL -> BAS-PRIORITARIO-POLICIA antes de get_criteria."""

    def test_alias_is_resolved_before_get_criteria(self):
        captured: dict[str, str] = {}

        def fake_get_criteria(_conn, alert_id):
            captured["alert_id"] = alert_id
            return [
                {"chave": "abertura", "label": "Abertura", "weight": 10, "description": ""},
            ]

        with patch("repositories.admin_criteria.get_criteria", side_effect=fake_get_criteria):
            alert = automation._build_alert_from_classification("bas", "BAS-POLICIAL")

        self.assertEqual(captured.get("alert_id"), "BAS-PRIORITARIO-POLICIA")
        self.assertEqual(alert.id, "BAS-PRIORITARIO-POLICIA")
        self.assertEqual(len(alert.criteria), 1)

    def test_runtime_blocks_when_db_criteria_are_missing(self):
        """Runtime nao pode auditar com fallback YAML ou criterios stale."""
        with patch("repositories.admin_criteria.get_criteria", return_value=[]):
            with self.assertRaises(automation.AlertWithoutOfficialCriteriaError):
                automation._build_alert_from_classification("bas", "BAS-PRIORITARIO-POLICIA")

    def test_pytest_env_alone_does_not_enable_criteria_fallback(self):
        """PYTEST_CURRENT_TEST vazado nao pode liberar criterio stale."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "case"}, clear=False):
            with patch("repositories.admin_criteria.get_criteria", return_value=[]):
                with self.assertRaises(automation.AlertWithoutOfficialCriteriaError):
                    automation._build_alert_from_classification("bas", "BAS-PRIORITARIO-POLICIA")

    def test_explicit_test_flag_is_required_for_legacy_criteria_fallback(self):
        with patch.dict(
            os.environ,
            {
                "PYTEST_CURRENT_TEST": "case",
                "AUDIT_ALLOW_OFFICIAL_CRITERIA_TEST_FALLBACK": "true",
            },
            clear=False,
        ):
            with patch("repositories.admin_criteria.get_criteria", return_value=[]):
                alert = automation._build_alert_from_classification("bas", "BAS-PRIORITARIO-POLICIA")

        self.assertEqual(alert.id, "BAS-PRIORITARIO-POLICIA")
        self.assertEqual(alert.criteria, [])

    def test_official_audit_alert_rejects_stale_payload_without_explicit_fallback(self):
        stale = AuditAlert(
            id="BAS-PRIORITARIO-POLICIA",
            label="Stale",
            context="Stale",
            criteria=[AuditCriterion(id="stale", label="Stale", weight=1)],
        )

        with patch("repositories.admin_criteria.get_criteria", return_value=[]):
            with self.assertRaises(RuntimeError):
                _resolve_official_audit_alert(stale, "bas")


class TestDirectionGuardrailKeywords(unittest.TestCase):
    """Fix #7: _expected_direction_for_alert por keyword no alert_id."""

    def test_policia_alert_expects_efetivada(self):
        result = classification._expected_direction_for_alert("BAS-PRIORITARIO-POLICIA")
        self.assertEqual(result, "efetivada")

    def test_receptiva_alert_expects_receptiva(self):
        result = classification._expected_direction_for_alert("UTI-RECEPTIVA-CLI")
        self.assertEqual(result, "receptiva")

    def test_parada_mot_alert_expects_efetivada(self):
        result = classification._expected_direction_for_alert("UTI-PARADA-MOT")
        self.assertEqual(result, "efetivada")

    def test_unknown_alert_returns_none(self):
        result = classification._expected_direction_for_alert("ALGO-NOVO-XYZ")
        self.assertIsNone(result)

    def test_empty_alert_returns_none(self):
        self.assertIsNone(classification._expected_direction_for_alert(""))
        self.assertIsNone(classification._expected_direction_for_alert(None))

    def test_guardrail_disabled_via_env_returns_none(self):
        with patch.dict(os.environ, {"DIRECTION_GUARDRAIL_ENABLED": "false"}):
            self.assertIsNone(classification._expected_direction_for_alert("BAS-PRIORITARIO-POLICIA"))


class TestMergeTranscriptionsTupleReturn(unittest.TestCase):
    """Fix #5: merge_transcriptions_with_gpt4o agora retorna (segments, status)."""

    def test_no_credentials_returns_diarized_with_status(self):
        diarized = [{"start": "00:00", "end": "00:05", "text": "Operador: Ola"}]

        with patch("core.config.AZURE_OPENAI_ENDPOINT", ""), \
             patch("core.config.AZURE_OPENAI_KEY", ""):
            segments, status = asyncio.run(
                merge_transcriptions_with_gpt4o(diarized, "texto whisper", "Operador", "Motorista")
            )

        self.assertEqual(segments, diarized)
        self.assertEqual(status, "no_credentials")

    def test_merge_failed_exception_returns_diarized_with_status(self):
        diarized = [{"start": "00:00", "end": "00:05", "text": "Operador: Ola"}]

        with patch("core.config.AZURE_OPENAI_ENDPOINT", "http://fake"), \
             patch("core.config.AZURE_OPENAI_KEY", "fake_key"), \
             patch("openai.AsyncAzureOpenAI", side_effect=Exception("API Error")):
            segments, status = asyncio.run(
                merge_transcriptions_with_gpt4o(diarized, "texto whisper", "Operador", "Motorista")
            )

        self.assertEqual(segments, diarized)
        self.assertEqual(status, "merge_failed")

    def test_merge_success_returns_new_segments_with_status(self):
        diarized = [{"start": "00:00", "end": "00:05", "text": "Operador: Ola"}]
        expected_merged = [{"start": "00:00", "end": "00:05", "text": "Operador: Olá corrigido"}]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"transcription": [{"start": "00:00", "end": "00:05", "text": "Operador: Olá corrigido"}]}'
        
        def fake_create(*args, **kwargs):
            return mock_response
            
        mock_client.chat.completions.create = fake_create

        with patch("core.config.AZURE_OPENAI_ENDPOINT", "http://fake"), \
             patch("core.config.AZURE_OPENAI_KEY", "fake_key"), \
             patch("openai.AzureOpenAI", return_value=mock_client):
            segments, status = asyncio.run(
                merge_transcriptions_with_gpt4o(diarized, "texto whisper", "Operador", "Motorista")
            )

        self.assertEqual(segments, expected_merged)
        self.assertEqual(status, "merged")


class TestCanonicalizeAlertIdPublic(unittest.TestCase):
    """Fix #6: canonicalize_alert_id exposto como API publica."""

    def test_known_alias_is_canonicalized(self):
        self.assertEqual(classification.canonicalize_alert_id("BAS-POLICIAL"), "BAS-PRIORITARIO-POLICIA")

    def test_unknown_alert_id_is_returned_as_is(self):
        self.assertEqual(classification.canonicalize_alert_id("UTI-PARADA-MOT"), "UTI-PARADA-MOT")


if __name__ == "__main__":
    unittest.main()
