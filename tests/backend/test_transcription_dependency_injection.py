import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.transcription import merge_transcriptions_with_gpt4o  # noqa: E402
from core.transcription import _extract_numeric_evidence  # noqa: E402
from core.transcription import _validate_merged_evidence  # noqa: E402


class TestTranscriptionDependencyInjection(unittest.TestCase):
    def test_merge_uses_injected_client_and_json_parser(self):
        diarized = [{"start": "00:00", "end": "00:05", "text": "Operador: Ola"}]
        expected = [{"start": "00:00", "end": "00:05", "text": "Operador: Ola corrigido"}]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"transcription": []}'))]
        )
        json_parser = MagicMock(return_value={"transcription": expected})

        segments, status = asyncio.run(
            merge_transcriptions_with_gpt4o(
                diarized,
                "texto whisper",
                "Operador",
                "Motorista",
                client=mock_client,
                azure_deployment="gpt-4o",
                json_parser=json_parser,
            )
        )

        self.assertEqual(status, "merged")
        self.assertEqual(segments, expected)
        mock_client.chat.completions.create.assert_called_once()
        json_parser.assert_called_once()

    def test_merge_preserves_diarization_metadata_from_source_segments(self):
        diarized = [
            {
                "start": "00:00",
                "end": "00:05",
                "text": "Operador: senha errada",
                "speaker_source_ids": [1],
                "speaker_persona_ids": [1],
                "speaker_confidence": 0.91,
                "speaker_risk": "low",
                "speaker_ambiguous": False,
            }
        ]
        merged_text_only = [{"start": "00:00", "end": "00:05", "text": "Operador: senha correta"}]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"transcription": []}'))]
        )
        json_parser = MagicMock(return_value={"transcription": merged_text_only})

        segments, status = asyncio.run(
            merge_transcriptions_with_gpt4o(
                diarized,
                "senha correta",
                "Operador",
                "Motorista",
                client=mock_client,
                azure_deployment="gpt-4o",
                json_parser=json_parser,
            )
        )

        self.assertEqual(status, "merged")
        self.assertEqual(segments[0]["text"], "Operador: senha correta")
        self.assertEqual(segments[0]["speaker_source_ids"], [1])
        self.assertEqual(segments[0]["speaker_risk"], "low")
        self.assertFalse(segments[0]["speaker_ambiguous"])

    def test_merge_rejects_result_missing_numeric_evidence_from_whisper(self):
        diarized = [
            {
                "start": "00:00",
                "end": "00:05",
                "text": "Motorista: a senha correta foi dita.",
                "speaker_source_ids": [0],
                "speaker_risk": "low",
            }
        ]
        merged_missing_number = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha correta foi dita."}]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"transcription": []}'))]
        )
        json_parser = MagicMock(return_value={"transcription": merged_missing_number})

        segments, status = asyncio.run(
            merge_transcriptions_with_gpt4o(
                diarized,
                "Motorista: a senha correta e 028-845-1365.",
                "Operador",
                "Motorista",
                client=mock_client,
                azure_deployment="gpt-4o",
                json_parser=json_parser,
            )
        )

        self.assertEqual(status, "merge_rejected_diagnostics")
        self.assertEqual(segments[0]["text"], diarized[0]["text"])
        self.assertEqual(segments[0]["speaker_source_ids"], [0])

    def test_merge_rejects_changed_timestamps_from_llm(self):
        diarized = [{"start": "00:00", "end": "00:05", "text": "Operador: Ola"}]
        merged_changed_timestamp = [{"start": "00:01", "end": "00:06", "text": "Operador: Ola corrigido"}]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"transcription": []}'))]
        )
        json_parser = MagicMock(return_value={"transcription": merged_changed_timestamp})

        segments, status = asyncio.run(
            merge_transcriptions_with_gpt4o(
                diarized,
                "Operador: Ola corrigido.",
                "Operador",
                "Motorista",
                client=mock_client,
                azure_deployment="gpt-4o",
                json_parser=json_parser,
            )
        )

        self.assertEqual(status, "merge_rejected_diagnostics")
        self.assertEqual(segments, diarized)

    def test_merge_rejects_changed_speaker_from_llm(self):
        diarized = [{"start": "00:00", "end": "00:05", "text": "Operador: Ola"}]
        merged_changed_speaker = [{"start": "00:00", "end": "00:05", "text": "Motorista: Ola corrigido"}]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"transcription": []}'))]
        )
        json_parser = MagicMock(return_value={"transcription": merged_changed_speaker})

        segments, status = asyncio.run(
            merge_transcriptions_with_gpt4o(
                diarized,
                "Operador: Ola corrigido.",
                "Operador",
                "Motorista",
                client=mock_client,
                azure_deployment="gpt-4o",
                json_parser=json_parser,
            )
        )

        self.assertEqual(status, "merge_rejected_diagnostics")
        self.assertEqual(segments, diarized)

    def test_numeric_evidence_flags_conflict_between_sources(self):
        merged = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha e 2222."}]
        diarized = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha e 1111."}]

        result = _validate_merged_evidence(merged, "Motorista: a senha e 2222.", diarized)

        self.assertTrue(result["ok"])
        self.assertTrue(result["has_diagnostics"])
        self.assertIn("numeric_conflict_between_sources", result["diagnostic_reasons"])
        self.assertTrue(result["numeric_conflict_between_sources"])
        self.assertEqual(result["source_only_numeric_sequences"], ["1111"])
        self.assertEqual(result["accurate_only_numeric_sequences"], ["2222"])

    def test_numeric_evidence_flags_source_only_numbers(self):
        merged = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha e 1111."}]
        diarized = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha e 1111."}]

        result = _validate_merged_evidence(merged, "Motorista: a senha foi dita.", diarized)

        self.assertTrue(result["ok"])
        self.assertTrue(result["has_diagnostics"])
        self.assertIn("numeric_conflict_between_sources", result["diagnostic_reasons"])
        self.assertTrue(result["numeric_conflict_between_sources"])
        self.assertEqual(result["source_only_numeric_sequences"], ["1111"])
        self.assertEqual(result["accurate_only_numeric_sequences"], [])

    def test_numeric_conflict_alone_is_reported_but_not_blocking(self):
        # v1.3.101: divergencia numerica ENTRE as fontes (diarize vs whisper) e
        # ruido de ASR, nao defeito da fusao. Deve continuar sendo REPORTADA
        # (observabilidade) mas NAO bloquear o merge. So missing/unexpected/
        # estrutura bloqueiam.
        merged = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha e 2222."}]
        diarized = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha e 1111."}]

        result = _validate_merged_evidence(merged, "Motorista: a senha e 2222.", diarized)

        self.assertTrue(result["has_diagnostics"])  # ainda reporta
        self.assertIn("numeric_conflict_between_sources", result["diagnostic_reasons"])
        self.assertEqual(result.get("is_blocking"), False)  # mas nao bloqueia

    def test_missing_numeric_evidence_is_blocking(self):
        # Contraste: numero do whisper SUMIR na fusao e defeito real -> bloqueia.
        merged = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha foi dita."}]
        diarized = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha foi dita."}]

        result = _validate_merged_evidence(merged, "Motorista: a senha e 028-845-1365.", diarized)

        self.assertEqual(result.get("is_blocking"), True)
        self.assertIn("missing_numeric_sequences_from_whisper", result["diagnostic_reasons"])

    def test_merge_accepts_when_only_sources_disagree_on_number(self):
        # Regressao do gate (v1.3.101): a fusao copiou corretamente o numero do
        # whisper (Versao B = fonte de verdade do numero); estrutura/missing/
        # unexpected OK. O unico diagnostico e a divergencia diarize-vs-whisper.
        # Antes: numeric_conflict disparava merge_rejected_diagnostics (falso-
        # positivo que matava hybrid_dual em audio ruidoso). Agora: "merged".
        diarized = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha e 1111."}]
        merged_uses_whisper_number = [{"start": "00:00", "end": "00:05", "text": "Motorista: a senha e 2222."}]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"transcription": []}'))]
        )
        json_parser = MagicMock(return_value={"transcription": merged_uses_whisper_number})

        segments, status = asyncio.run(
            merge_transcriptions_with_gpt4o(
                diarized,
                "Motorista: a senha e 2222.",
                "Operador",
                "Motorista",
                client=mock_client,
                azure_deployment="gpt-4o",
                json_parser=json_parser,
            )
        )

        self.assertEqual(status, "merged")
        self.assertEqual(segments[0]["text"], "Motorista: a senha e 2222.")

    def test_extract_numeric_evidence_normalizes_separators(self):
        self.assertEqual(
            _extract_numeric_evidence("senha 028-845-1365 e CPF 123.456.789-00"),
            {"0288451365", "12345678900"},
        )


if __name__ == "__main__":
    unittest.main()
