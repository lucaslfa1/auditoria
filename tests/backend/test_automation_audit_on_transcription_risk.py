"""Auto-auditar no modo automacao quando o unico bloqueio e qualidade de transcricao.

Antes: item com alerta valido travado por risco de diarizacao (troca de falante,
score baixo) ia para needs_manual_triage e esperava um humano. Agora, gateado por
AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK (default ON), a automacao audita mesmo assim
(criado_por='automacao', status awaiting_pair). Transcricao que FALHA de vez (erro)
continua em triagem porque nao existe transcricao para auditar.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import automation
from core.automation_cache import AuditCacheGatekeeper, TranscriptionFallbackGatekeeper
from db.domain_constants import (
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_AUDITED,
    SOURCE_TYPE_AUDIO,
)


def _audio_pipeline_ctx():
    return SimpleNamespace(
        source_type=SOURCE_TYPE_AUDIO,
        to_audit_metadata=lambda: {"origin": "automation"},
    )


class TestAuditOnTranscriptionRiskFlag(unittest.TestCase):
    def test_flag_default_on_quando_env_ausente(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK", None)
            self.assertTrue(automation._audit_on_transcription_risk_enabled())

    def test_flag_off_quando_env_false(self):
        with patch.dict(os.environ, {"AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK": "false"}, clear=False):
            self.assertFalse(automation._audit_on_transcription_risk_enabled())

    def test_flag_on_quando_env_true(self):
        with patch.dict(os.environ, {"AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK": "true"}, clear=False):
            self.assertTrue(automation._audit_on_transcription_risk_enabled())


class TestFreshTranscriptionGate(unittest.TestCase):
    """check_new_audit_quality: transcricao recem-gerada com flag de risco."""

    def _run(self, flag_value):
        # transcription_provider.selected_strategy e obrigatorio desde a
        # politica do candidate selector (_satisfies_transcription_policy):
        # sem ele o gate trata como "transcricao ausente" e descarta antes
        # de chegar na flag testada aqui.
        result = SimpleNamespace(
            audio_quality={
                "diarization": {"swap_risk": "medium"},
                "transcription_provider": {"selected_strategy": "fast"},
            }
        )
        ctx = _audio_pipeline_ctx()
        with patch.object(
            automation,
            "_automatic_audio_transcription_review_reasons",
            return_value=["risco_medio_de_troca_de_falante"],
        ), patch.object(automation, "_mark_item_status") as mock_mark, patch.dict(
            os.environ, {"AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK": flag_value}, clear=False
        ):
            out = TranscriptionFallbackGatekeeper.check_new_audit_quality(
                result, "queue-1", "call.wav", "audit-hash-1", ctx
            )
        return out, mock_mark

    def test_flag_off_estaciona_em_triagem(self):
        out, mock_mark = self._run("false")
        self.assertIsNotNone(out)
        self.assertEqual(out["status"], "blocked_transcription_quality")
        mock_mark.assert_called_once()
        self.assertEqual(mock_mark.call_args.args[1], REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE)

    def test_flag_on_segue_para_auditoria(self):
        out, mock_mark = self._run("true")
        self.assertIsNone(out)
        mock_mark.assert_not_called()


class TestCachedTranscriptionGate(unittest.TestCase):
    """check_existing_audit: auditoria em cache cuja transcricao pede revisao."""

    def _run(self, flag_value):
        # Ver nota em TestFreshTranscriptionGate: selected_strategy obrigatoria
        # para o cache ser elegivel (_satisfies_transcription_policy).
        existing = SimpleNamespace(
            audio_quality={
                "diarization": {"swap_risk": "medium"},
                "transcription_provider": {"selected_strategy": "fast"},
            },
            id=123,
        )
        ctx = _audio_pipeline_ctx()
        with patch("repositories.audits.get_audit_by_hash", return_value=existing), patch(
            "core.automation_cache.attach_pipeline_context_to_audio_quality",
            side_effect=lambda aq, _ctx: aq,
        ), patch.object(
            automation,
            "_automatic_audio_transcription_review_reasons",
            return_value=["risco_medio_de_troca_de_falante"],
        ), patch.object(automation, "_mark_item_status") as mock_mark, patch.object(
            automation.database, "persist_audit_artifacts", return_value=999
        ) as mock_persist, patch.dict(
            os.environ, {"AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK": flag_value}, clear=False
        ):
            out = AuditCacheGatekeeper.check_existing_audit(
                None, "audit-hash-1", ctx, b"audio", "audio/wav", "call.wav", "queue-1"
            )
        return out, mock_mark, mock_persist

    def test_flag_off_estaciona_e_nao_persiste(self):
        out, mock_mark, mock_persist = self._run("false")
        self.assertEqual(out["status"], "blocked_transcription_quality")
        self.assertEqual(mock_mark.call_args.args[1], REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE)
        mock_persist.assert_not_called()

    def test_flag_on_audita_como_automacao(self):
        out, mock_mark, mock_persist = self._run("true")
        self.assertEqual(out["status"], "audited")
        self.assertEqual(out["audit_id"], 999)
        mock_persist.assert_called_once()
        self.assertEqual(mock_persist.call_args.kwargs.get("criado_por"), "automacao")
        self.assertEqual(mock_mark.call_args.args[1], REVIEW_QUEUE_STATUS_AUDITED)


class TestTranscriptionFailureRetry(unittest.TestCase):
    """Falha de transcricao e transitoria (instabilidade do Azure): re-tenta ate o limite
    e, esgotado, DESCARTA permanente — nao prende em triagem. Rollback via
    AUTOMATION_TRANSCRIPTION_FAILURE_RETRY=false."""

    def test_primeira_falha_retenta_com_flag_on(self):
        ctx = _audio_pipeline_ctx()
        with patch.object(automation, "_mark_item_status") as mock_mark, patch.dict(
            os.environ,
            {"AUTOMATION_TRANSCRIPTION_FAILURE_RETRY": "true", "AUTOMATION_TRANSIENT_RETRY_LIMIT": "3"},
            clear=False,
        ):
            out = TranscriptionFallbackGatekeeper.handle_transcription_runtime_error(
                RuntimeError("timeout no Azure: transcricao falhou"),
                "queue-1",
                "call.wav",
                ctx,
                metadata={"automation_transient_retries": 0},
            )
        self.assertEqual(out["status"], "retry_transcription_failed")
        mock_mark.assert_called_once()
        # retry volta para ready (auto_resolved), nao pending, senao nao e re-auditado
        self.assertEqual(mock_mark.call_args.args[1], automation.REVIEW_QUEUE_STATUS_AUTO_RESOLVED)

    def test_descarta_quando_esgota_retries(self):
        ctx = _audio_pipeline_ctx()
        with patch.object(
            automation.database,
            "descartar_item_automacao",
            return_value={"discarded": True, "tombstone": True, "attempts": 1},
        ) as mock_disc, patch.dict(
            os.environ,
            {
                "AUTOMATION_TRANSCRIPTION_FAILURE_RETRY": "true",
                "AUTOMATION_TRANSIENT_RETRY_LIMIT": "3",
                "AUTOMATION_DISCARD_IMPOSSIBLE_TRANSCRIPTION": "true",
            },
            clear=False,
        ):
            out = TranscriptionFallbackGatekeeper.handle_transcription_runtime_error(
                RuntimeError("hybrid_dual falhou"),
                "queue-1",
                "call.wav",
                ctx,
                metadata={"automation_transient_retries": 2},  # next=3 >= 3 -> esgotou
            )
        self.assertEqual(out["status"], "discarded_transcription_failed")
        mock_disc.assert_called_once()
        # politica (v1.3.111): falha de transcricao no automatico = descarte PERMANENTE
        self.assertTrue(mock_disc.call_args.kwargs["tombstone"])

    def test_default_sem_retry_descarta_na_primeira_falha(self):
        # Default novo AUTOMATION_TRANSIENT_RETRY_LIMIT=1: a 1a falha ja esgota o
        # retry e descarta, sem re-auditar (politica "auditar e so uma vez").
        ctx = _audio_pipeline_ctx()
        with patch.object(
            automation.database,
            "descartar_item_automacao",
            return_value={"discarded": True, "tombstone": True, "attempts": 1},
        ) as mock_disc, patch.dict(
            os.environ,
            {"AUTOMATION_TRANSCRIPTION_FAILURE_RETRY": "true", "AUTOMATION_TRANSIENT_RETRY_LIMIT": "1"},
            clear=False,
        ):
            out = TranscriptionFallbackGatekeeper.handle_transcription_runtime_error(
                RuntimeError("hybrid_dual falhou"),
                "queue-1",
                "call.wav",
                ctx,
                metadata={"automation_transient_retries": 0},  # 1a falha; limit=1 -> sem retry
            )
        self.assertEqual(out["status"], "discarded_transcription_failed")
        mock_disc.assert_called_once()

    def test_flag_off_estaciona_em_triagem(self):
        ctx = _audio_pipeline_ctx()
        with patch.object(automation, "_mark_item_status") as mock_mark, patch.dict(
            os.environ, {"AUTOMATION_TRANSCRIPTION_FAILURE_RETRY": "false"}, clear=False
        ):
            out = TranscriptionFallbackGatekeeper.handle_transcription_runtime_error(
                RuntimeError("timeout no Azure: transcricao falhou"),
                "queue-1",
                "call.wav",
                ctx,
            )
        self.assertEqual(out["status"], "blocked_transcription_quality")
        mock_mark.assert_called_once()
        self.assertEqual(mock_mark.call_args.args[1], REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE)


class TestTranscriptionIsEmpty(unittest.TestCase):
    """Finding 1 (revisao GPT): so transcricao GENUINAMENTE vazia vira descarte permanente;
    qualidade ruim mas COM conteudo (selector rejeitado, conteudo curto, poucas falas) NAO
    some — segue para o auditor."""

    @staticmethod
    def _aq(**tq):
        return {"transcription_quality": tq}

    def test_vazia_por_motivo(self):
        from core.transcription_quality import transcription_is_empty
        aq = self._aq(blocking_reasons=["transcricao_vazia"], metrics={"segment_count": 0})
        self.assertTrue(transcription_is_empty(aq))

    def test_vazia_por_segment_count_zero(self):
        from core.transcription_quality import transcription_is_empty
        aq = self._aq(blocking_reasons=[], metrics={"segment_count": 0})
        self.assertTrue(transcription_is_empty(aq))

    def test_segmento_sem_texto_e_vazia(self):
        from core.transcription_quality import attach_transcription_quality_gate, transcription_is_empty
        aq = attach_transcription_quality_gate({}, [{"text": ""}])
        self.assertTrue(transcription_is_empty(aq))

    def test_segmento_com_espacos_e_vazia(self):
        from core.transcription_quality import attach_transcription_quality_gate, transcription_is_empty
        aq = attach_transcription_quality_gate({}, [{"text": "   "}])
        self.assertTrue(transcription_is_empty(aq))

    def test_selector_rejeitado_com_conteudo_nao_e_vazia(self):
        from core.transcription_quality import transcription_is_empty
        aq = self._aq(audit_readiness="blocked", blocking_reasons=["selector_rejected"], metrics={"segment_count": 12})
        self.assertFalse(transcription_is_empty(aq))

    def test_conteudo_insuficiente_nao_e_vazia(self):
        from core.transcription_quality import transcription_is_empty
        aq = self._aq(audit_readiness="blocked", blocking_reasons=["conteudo_transcrito_insuficiente"], metrics={"segment_count": 3})
        self.assertFalse(transcription_is_empty(aq))

    def test_conteudo_curto_com_texto_real_nao_e_vazia(self):
        from core.transcription_quality import attach_transcription_quality_gate, transcription_is_empty
        aq = attach_transcription_quality_gate({}, [{"text": "Operador: Alo."}])
        self.assertFalse(transcription_is_empty(aq))

    def test_review_required_nao_e_vazia(self):
        from core.transcription_quality import transcription_is_empty
        aq = self._aq(audit_readiness="review_required", blocking_reasons=[], metrics={"segment_count": 20})
        self.assertFalse(transcription_is_empty(aq))


if __name__ == "__main__":
    unittest.main()
