import asyncio
import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.transcription import transcribe_audio


class TestHybridDualRobustness(unittest.IsolatedAsyncioTestCase):
    """Testa a resiliência do motor hybrid_dual a falhas parciais."""

    def _segments(self, label: str) -> list[dict]:
        return [
            {"start": "00:00", "end": "00:05", "text": f"{label} abertura"},
            {"start": "00:06", "end": "00:12", "text": f"{label} desenvolvimento"},
            {"start": "00:13", "end": "00:18", "text": f"{label} fechamento"},
        ]

    async def test_hybrid_dual_success_both(self):
        """Ambos funcionam: Whisper e Diarize. Deve fundir e retornar sub_strategy=hybrid_dual."""
        diarize_segments = self._segments("Diarize OK")
        whisper_segments = self._segments("Whisper OK")
        merged_segments = self._segments("Merged OK")

        with patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=diarize_segments), \
             patch("core.transcription.transcribe_audio_azure", return_value=whisper_segments), \
             patch("core.transcription.prepare_audio_for_azure", return_value=MagicMock(audio_file=b"audio", mime_type="audio/wav")), \
             patch("core.transcription.merge_transcriptions_with_gpt4o", return_value=(merged_segments, "merged")), \
             patch("core.transcription.AI_PROVIDER_PRIORITY", "azure"), \
             patch("core.transcription.AZURE_SPEECH_KEY", "fake_key"), \
             patch("core.transcription._resolve_azure_gpt4o_diarize_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._resolve_azure_whisper_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._transcription_candidate_is_acceptable", return_value=True), \
             patch.dict(os.environ, {
                 "AZURE_TRANSCRIPTION_ENGINE": "hybrid_dual",
                 "AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL": "true",
             }):
            
            segments, metadata = await transcribe_audio(
                b"audio_bytes", "audio/wav", "Operador", "Motorista", return_metadata=True
            )
            sub_strategy = metadata["selected_strategy"]

        self.assertEqual(segments, merged_segments)
        self.assertEqual(sub_strategy, "hybrid_dual")

    async def test_hybrid_dual_validates_gpt4o_merge_before_accepting_candidate(self):
        """O caminho premium deve validar a transcricao fundida, nao o Diarize cru."""
        diarize_segments = self._segments("Operador: senha errada")
        whisper_segments = self._segments("senha correta 028-845-1365")
        merged_segments = self._segments("Operador: senha correta 028-845-1365")
        validator_inputs = []

        def validate_candidate(segments, _diarization_reference):
            validator_inputs.append(segments)
            return segments == merged_segments

        with patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=diarize_segments), \
             patch("core.transcription.transcribe_audio_azure", return_value=whisper_segments), \
             patch("core.transcription.prepare_audio_for_azure", return_value=MagicMock(audio_file=b"audio", mime_type="audio/wav")), \
             patch("core.transcription.deduplicate_transcription_segments", side_effect=lambda segments: segments), \
             patch("core.transcription.merge_transcriptions_with_gpt4o", return_value=(merged_segments, "merged")) as mock_merge, \
             patch("core.transcription.AI_PROVIDER_PRIORITY", "azure"), \
             patch("core.transcription.AZURE_SPEECH_KEY", "fake_key"), \
             patch("core.transcription._resolve_azure_gpt4o_diarize_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._resolve_azure_whisper_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._should_use_gpt4o_diarize_as_primary_for_audio", return_value=False), \
             patch("core.transcription._transcription_candidate_is_acceptable", side_effect=validate_candidate), \
             patch("core.transcription._score_transcription_candidate", return_value=1000), \
             patch.dict(os.environ, {
                 "AZURE_TRANSCRIPTION_ENGINE": "hybrid_dual",
                 "AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL": "true",
             }):

            segments, metadata = await transcribe_audio(
                b"audio_bytes", "audio/wav", "Operador", "Motorista", return_metadata=True
            )

        mock_merge.assert_awaited_once()
        self.assertEqual(segments, merged_segments)
        self.assertEqual(metadata["selected_strategy"], "hybrid_dual")
        self.assertEqual(validator_inputs[0], merged_segments)

    async def test_hybrid_dual_accepts_real_merge_when_metadata_is_preserved(self):
        """Sem metadados preservados, a fusao premium cai como diarizacao high-risk."""
        diarize_segments = [
            {
                "start": "00:00",
                "end": "00:06",
                "text": "Operador: Bom dia, aqui e da Opentech Rastreamento.",
                "speaker_source_ids": [1],
                "speaker_risk": "low",
            },
            {
                "start": "00:07",
                "end": "00:13",
                "text": "Motorista: Bom dia, estou parado no posto de gasolina.",
                "speaker_source_ids": [0],
                "speaker_risk": "low",
            },
            {
                "start": "00:14",
                "end": "00:21",
                "text": "Operador: O contato e sobre um botao de panico gerado.",
                "speaker_source_ids": [1],
                "speaker_risk": "low",
            },
            {
                "start": "00:22",
                "end": "00:30",
                "text": "Motorista: A senha correta e 028-845-1365.",
                "speaker_source_ids": [0],
                "speaker_risk": "low",
            },
        ]
        whisper_segments = [
            {"start": "00:00", "end": "00:30", "text": "senha correta 028-845-1365 botao de panico posto de gasolina"}
        ]
        merged_text_only = [
            {**{k: segment[k] for k in ("start", "end")}, "text": segment["text"].replace("errada", "correta")}
            for segment in diarize_segments
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps({"transcription": merged_text_only}, ensure_ascii=False)
                    )
                )
            ]
        )

        with patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=diarize_segments), \
             patch("core.transcription.transcribe_audio_azure", return_value=whisper_segments), \
             patch("core.transcription.prepare_audio_for_azure", return_value=MagicMock(audio_file=b"audio", mime_type="audio/wav")), \
             patch("core.transcription._build_azure_merge_client", return_value=mock_client), \
             patch("core.config.AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com"), \
             patch("core.config.AZURE_OPENAI_KEY", "fake_key"), \
             patch("core.config.AZURE_OPENAI_DEPLOYMENT", "gpt-4o"), \
             patch("core.transcription.AI_PROVIDER_PRIORITY", "azure"), \
             patch("core.transcription.AZURE_SPEECH_KEY", "fake_key"), \
             patch("core.transcription._resolve_azure_gpt4o_diarize_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._resolve_azure_whisper_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._should_use_gpt4o_diarize_as_primary_for_audio", return_value=False), \
             patch.dict(os.environ, {
                 "AZURE_TRANSCRIPTION_ENGINE": "hybrid_dual",
                 "AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL": "true",
             }):

            segments, metadata = await transcribe_audio(
                b"audio_bytes", "audio/wav", "Operador", "Motorista", return_metadata=True
            )

        self.assertEqual(metadata["selected_strategy"], "hybrid_dual")
        self.assertEqual(segments[0]["speaker_source_ids"], [1])
        self.assertEqual(segments[1]["speaker_source_ids"], [0])
        self.assertEqual(metadata["attempts"][0]["status"], "accepted")

    async def test_hybrid_dual_fails_whisper_blocks_in_strict_mode(self):
        """Whisper falhando invalida o hybrid_dual em modo estrito."""
        diarize_segments = [{"start": "00:00", "end": "00:05", "text": "Diarize OK"}]

        with patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=diarize_segments), \
             patch("core.transcription.transcribe_audio_azure", side_effect=Exception("Whisper Down")), \
             patch("core.transcription.merge_transcriptions_with_gpt4o") as mock_merge, \
             patch("core.transcription.AI_PROVIDER_PRIORITY", "azure"), \
             patch("core.transcription.AZURE_SPEECH_KEY", "fake_key"), \
             patch("core.transcription._resolve_azure_gpt4o_diarize_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._resolve_azure_whisper_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._transcription_candidate_is_acceptable", return_value=True), \
             patch.dict(os.environ, {
                 "AZURE_TRANSCRIPTION_ENGINE": "hybrid_dual",
                 "AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL": "true",
             }):
            
            with self.assertRaises(RuntimeError) as ctx:
                await transcribe_audio(
                    b"audio_bytes", "audio/wav", "Operador", "Motorista", return_metadata=True
                )

        mock_merge.assert_not_called()
        self.assertIn("Whisper falhou", str(ctx.exception))

    async def test_hybrid_dual_fails_diarize_blocks_in_strict_mode(self):
        """Diarize falhando invalida o hybrid_dual em modo estrito."""
        whisper_segments = [{"start": "00:00", "end": "00:05", "text": "Whisper OK"}]

        with patch("core.transcription.transcribe_audio_gpt4o_diarize", side_effect=Exception("Diarize Down")), \
             patch("core.transcription.transcribe_audio_azure", return_value=whisper_segments), \
             patch("core.transcription.merge_transcriptions_with_gpt4o") as mock_merge, \
             patch("core.transcription.AI_PROVIDER_PRIORITY", "azure"), \
             patch("core.transcription.AZURE_SPEECH_KEY", "fake_key"), \
             patch("core.transcription._resolve_azure_gpt4o_diarize_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._resolve_azure_whisper_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._transcription_candidate_is_acceptable", return_value=True), \
             patch.dict(os.environ, {
                 "AZURE_TRANSCRIPTION_ENGINE": "hybrid_dual",
                 "AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL": "true",
             }):
            
            with self.assertRaises(RuntimeError) as ctx:
                await transcribe_audio(
                    b"audio_bytes", "audio/wav", "Operador", "Motorista", return_metadata=True
                )

        mock_merge.assert_not_called()
        self.assertIn("Diarize falhou", str(ctx.exception))

    async def test_hybrid_dual_blocks_when_gpt4o_merge_fails_in_strict_mode(self):
        """Diarize e Whisper precisam passar pela fusao GPT-4o para serem aceitos."""
        diarize_segments = [{"start": "00:00", "end": "00:05", "text": "Diarize OK"}]
        whisper_segments = [{"start": "00:00", "end": "00:05", "text": "Whisper OK"}]

        with patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=diarize_segments), \
             patch("core.transcription.transcribe_audio_azure", return_value=whisper_segments), \
             patch("core.transcription.prepare_audio_for_azure", return_value=MagicMock(audio_file=b"audio", mime_type="audio/wav")), \
             patch("core.transcription.merge_transcriptions_with_gpt4o", return_value=(diarize_segments, "merge_failed")), \
             patch("core.transcription.AI_PROVIDER_PRIORITY", "azure"), \
             patch("core.transcription.AZURE_SPEECH_KEY", "fake_key"), \
             patch("core.transcription._resolve_azure_gpt4o_diarize_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._resolve_azure_whisper_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._transcription_candidate_is_acceptable", return_value=True), \
             patch.dict(os.environ, {
                 "AZURE_TRANSCRIPTION_ENGINE": "hybrid_dual",
                 "AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL": "true",
             }):

            with self.assertRaises(RuntimeError) as ctx:
                await transcribe_audio(
                    b"audio_bytes", "audio/wav", "Operador", "Motorista", return_metadata=True
                )

        self.assertIn("fusao GPT-4o falhou", str(ctx.exception))

    async def test_hybrid_dual_merge_failure_uses_fast_when_manual_flow_allows_it(self):
        """Upload manual usa Azure Fast quando o hybrid_dual nao fecha consenso."""
        diarize_segments = self._segments("Diarize OK")
        whisper_segments = self._segments("Whisper OK")
        fast_segments = self._segments("Fast OK")

        def transcribe_azure_side_effect(*_args, **kwargs):
            if kwargs.get("endpoint_override"):
                return whisper_segments
            return fast_segments

        with patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=diarize_segments), \
             patch("core.transcription.transcribe_audio_azure", side_effect=transcribe_azure_side_effect), \
             patch("core.transcription.prepare_audio_for_azure", return_value=MagicMock(audio_file=b"audio", mime_type="audio/wav")), \
             patch("core.transcription.merge_transcriptions_with_gpt4o", return_value=(diarize_segments, "merge_failed")), \
             patch("core.transcription.AI_PROVIDER_PRIORITY", "azure"), \
             patch("core.transcription.AZURE_SPEECH_KEY", "fake_key"), \
             patch("core.transcription._resolve_azure_gpt4o_diarize_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._resolve_azure_whisper_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._transcription_candidate_is_acceptable", return_value=True), \
             patch.dict(os.environ, {
                 "AZURE_TRANSCRIPTION_ENGINE": "hybrid_dual",
                 "AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL": "true",
                 "AZURE_TRANSCRIPTION_STRICT_HYBRID_DUAL": "true",
                 "AZURE_SPEECH_ENDPOINT": "https://speech.example.test",
             }):

            segments, metadata = await transcribe_audio(
                b"audio_bytes",
                "audio/wav",
                "Operador",
                "Motorista",
                return_metadata=True,
                allow_degraded_hybrid_fallback=True,
            )

        self.assertEqual(segments, fast_segments)
        self.assertEqual(metadata["selected_strategy"], "fast")
        self.assertEqual(metadata["attempts"][0]["strategy"], "hybrid_dual")
        self.assertEqual(metadata["attempts"][0]["effective_strategy"], "fast")

    async def test_hybrid_dual_fails_both(self):
        """Ambos falham. Deve subir exceção."""
        with patch("core.transcription.transcribe_audio_gpt4o_diarize", side_effect=Exception("Diarize Down")), \
             patch("core.transcription.transcribe_audio_azure", side_effect=Exception("Whisper Down")), \
             patch("core.transcription.AI_PROVIDER_PRIORITY", "azure"), \
             patch("core.transcription.AZURE_SPEECH_KEY", "fake_key"), \
             patch("core.transcription._resolve_azure_gpt4o_diarize_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._resolve_azure_whisper_config", return_value=("fake_endpoint", "fake_key")), \
             patch("core.transcription._transcription_candidate_is_acceptable", return_value=True), \
             patch.dict(os.environ, {
                 "AZURE_TRANSCRIPTION_ENGINE": "hybrid_dual",
                 "AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL": "true",
             }):
            
            with self.assertRaises(Exception):
                await transcribe_audio(
                    b"audio_bytes", "audio/wav", "Operador", "Motorista"
                )

if __name__ == "__main__":
    unittest.main()
