import unittest
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.transcription_orchestrator import (
    build_strategy_order,
    prepare_audio_for_azure,
    run_transcription_pipeline,
)


class TestTranscriptionOrchestrator(unittest.TestCase):
    def test_build_strategy_order_respects_engine_and_enabled_fallbacks(self):
        run_order = build_strategy_order(
            "whisper",
            include_sdk=False,
            include_whisper=True,
            include_gpt4o_diarize=True,
        )
        self.assertEqual(run_order, ["whisper", "fast", "gpt4o_diarize"])

    def test_build_strategy_order_prefers_fast_before_gpt4o_diarize_when_enabled(self):
        run_order = build_strategy_order(
            "fast",
            include_sdk=False,
            include_whisper=False,
            include_gpt4o_diarize=True,
        )
        self.assertEqual(run_order, ["fast", "gpt4o_diarize"])

    def test_build_strategy_order_uses_hybrid_dual_only_when_explicit(self):
        """hybrid_dual explicito roda SOZINHO na ordem de estrategias: sem
        fallback premium automatico (politica de custo v1.3.109; a degradacao
        para fast em fluxo manual e interna a estrategia, via
        allow_degraded_hybrid_fallback)."""
        run_order = build_strategy_order(
            "hybrid_dual",
            include_sdk=False,
            include_whisper=True,
            include_gpt4o_diarize=True,
        )
        self.assertEqual(run_order, ["hybrid_dual"])

    def test_prepare_audio_for_azure_converts_to_wav_when_mime_is_unsupported(self):
        wav_audio = b"wav-audio"
        prepared = prepare_audio_for_azure(
            b"raw-audio",
            "audio/flac",
            preprocess_enabled=False,
            should_preprocess_audio=lambda _size, _mime: False,
            convert_to_mp3=lambda payload, source_mime: payload + source_mime.encode("utf-8"),
            convert_to_wav=lambda _payload: wav_audio,
            accepted_mime_types={"audio/wav", "audio/mpeg"},
            log=lambda _message: None,
        )

        self.assertEqual(prepared.audio_file, wav_audio)
        self.assertEqual(prepared.mime_type, "audio/wav")

    def test_run_transcription_pipeline_returns_first_valid_result(self):
        attempts = []

        def execute_strategy(strategy):
            attempts.append(strategy)
            if strategy == "fast":
                return [{"start": "00:00", "end": "00:03", "text": "curto"}]
            return [{"start": "00:00", "end": "00:10", "text": "texto bom e suficientemente longo"}]

        result = run_transcription_pipeline(
            ["fast", "gpt4o_diarize"],
            execute_strategy=execute_strategy,
            deduplicate_segments=lambda segments: segments,
            looks_valid=lambda segments: len(segments[0]["text"]) > 10,
            score_segments=lambda segments: len(segments[0]["text"]),
            log=lambda _message: None,
        )

        self.assertEqual(attempts, ["fast", "gpt4o_diarize"])
        self.assertEqual(result[0]["text"], "texto bom e suficientemente longo")

    def test_run_transcription_pipeline_uses_best_candidate_when_all_are_weak(self):
        """Com allow_best_candidate_fallback=True (fluxo manual), todos fracos
        => devolve o melhor candidato. Sem a flag (default, automacao), o
        comportamento atual e ERRO — resultado fraco vira descarte/triagem
        em vez de auditoria de baixa qualidade (testado abaixo)."""
        result = run_transcription_pipeline(
            ["fast", "gpt4o_diarize"],
            execute_strategy=lambda strategy: [
                {"start": "00:00", "end": "00:02", "text": "curto"}
            ] if strategy == "fast" else [
                {"start": "00:00", "end": "00:05", "text": "um texto um pouco melhor"}
            ],
            deduplicate_segments=lambda segments: segments,
            looks_valid=lambda _segments: False,
            score_segments=lambda segments: len(segments[0]["text"]),
            log=lambda _message: None,
            allow_best_candidate_fallback=True,
        )

        self.assertEqual(result[0]["text"], "um texto um pouco melhor")

    def test_run_transcription_pipeline_falha_quando_todos_fracos_sem_fallback(self):
        """Modo estrito (default da automacao): todos os candidatos fracos =>
        RuntimeError, sem entregar transcricao ruim para auditoria."""
        with self.assertRaises(RuntimeError):
            run_transcription_pipeline(
                ["fast"],
                execute_strategy=lambda _strategy: [
                    {"start": "00:00", "end": "00:02", "text": "curto"}
                ],
                deduplicate_segments=lambda segments: segments,
                looks_valid=lambda _segments: False,
                score_segments=lambda segments: len(segments[0]["text"]),
                log=lambda _message: None,
            )

    def test_run_transcription_pipeline_returns_metadata_about_attempts(self):
        result, metadata = run_transcription_pipeline(
            ["fast", "gpt4o_diarize"],
            execute_strategy=lambda strategy: [
                {"start": "00:00", "end": "00:02", "text": "curto"}
            ] if strategy == "fast" else [
                {"start": "00:00", "end": "00:08", "text": "texto bom e suficientemente longo"}
            ],
            deduplicate_segments=lambda segments: segments,
            looks_valid=lambda segments: len(segments[0]["text"]) > 10,
            score_segments=lambda segments: len(segments[0]["text"]),
            log=lambda _message: None,
            return_metadata=True,
        )

        self.assertEqual(result[0]["text"], "texto bom e suficientemente longo")
        self.assertEqual(metadata["selected_strategy"], "gpt4o_diarize")
        self.assertEqual(metadata["selected_reason"], "accepted")
        self.assertEqual(metadata["attempts"][0]["strategy"], "fast")
        self.assertEqual(metadata["attempts"][0]["status"], "insufficient")
        self.assertEqual(metadata["attempts"][1]["strategy"], "gpt4o_diarize")
        self.assertEqual(metadata["attempts"][1]["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
