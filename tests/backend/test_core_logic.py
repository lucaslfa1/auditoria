import asyncio
import unittest
import json
import sys
import os
from datetime import timedelta
from unittest.mock import MagicMock, patch, AsyncMock

# Add backend directory to path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import services
import core.transcription
import core.evaluation
import core.audit
from audio.diarization_quality import (
    build_diarization_reference,
    build_diarization_quality,
    detect_audio_mime_type,
    extract_segment_speaker,
)
from services import (
    compute_input_hash,
    deduplicate_transcription_segments,
    filter_hallucinations,
    format_timestamp,
    infer_interlocutor_label,
    normalize_speaker_prefix,
    validate_transcription,
    result_from_raw,
    parse_iso_duration,
    _extract_phrase_timing_ms,
    _normalize_speaker_id,
    _transcription_looks_valid,
    _should_preprocess_audio_for_azure,
    _get_transcription_timeout_seconds,
    _get_whisper_temperature,
    _resolve_azure_whisper_config,
    _resolve_azure_gpt4o_diarize_config,
    _get_azure_gpt4o_diarize_auth_mode,
    _get_azure_gpt4o_diarize_model_name,
    _should_promote_prescan_to_gpt4o,
    _should_use_gpt4o_diarize_as_primary,
    _should_use_gpt4o_diarize_as_primary_for_audio,
    _should_discard_whisper_segment,
    _should_replace_whisper_segment_with_inaudivel,
)
from schemas import AuditCriterion, AuditAlert
from audio.speaker_detection import SpeakerDetectionService, RawPhrase, SegmentoFormatado
from core.transcription_orchestrator import PreparedAudio

class TestCoreLogic(unittest.TestCase):

    def setUp(self):
        # Create dummy criteria
        self.criteria = [
            AuditCriterion(id="CR01", label="Item 1", weight=10.0, description="Desc 1"),
            AuditCriterion(id="CR02", label="Item 2", weight=20.0, description="Desc 2"),
            AuditCriterion(id="CR03", label="Item 3", weight=5.0, description="Desc 3")
        ]
        
        # Create dummy alert
        self.alert = AuditAlert(
            id="AL01", 
            label="Teste", 
            context="Contexto", 
            criteria=self.criteria
        )

    def test_format_timestamp(self):
        """Test timestamp formatting (seconds -> MM:SS.mmm)"""
        self.assertEqual(format_timestamp(0.0), "00:00.000")
        self.assertEqual(format_timestamp(65.5), "01:05.500")

    def test_parse_iso_duration_accepts_iso_and_timespan(self):
        self.assertAlmostEqual(parse_iso_duration("PT1M5.5S"), 65.5)
        self.assertAlmostEqual(parse_iso_duration("00:01:05.500"), 65.5)

    def test_detect_audio_mime_type_prefers_magic_bytes(self):
        self.assertEqual(detect_audio_mime_type(b"ID3abc", "audio/wav"), "audio/mpeg")
        self.assertEqual(detect_audio_mime_type(b"OggSrest", "audio/wav"), "audio/ogg")
        self.assertEqual(
            detect_audio_mime_type(b"RIFF\x00\x00\x00\x00WAVEfmt ", "audio/mpeg"),
            "audio/wav",
        )

    def test_extract_phrase_timing_ms_accepts_multiple_formats(self):
        offset_ms, duration_ms = _extract_phrase_timing_ms(
            {"offsetMilliseconds": 1500, "durationMilliseconds": 500}
        )
        self.assertEqual(offset_ms, 1500)
        self.assertEqual(duration_ms, 500)

        offset_ms, duration_ms = _extract_phrase_timing_ms(
            {"offset": "PT1.5S", "duration": "PT0.5S"}
        )
        self.assertEqual(offset_ms, 1500)
        self.assertEqual(duration_ms, 500)

        offset_ms, duration_ms = _extract_phrase_timing_ms(
            {"start": 1.5, "end": 2.25}
        )
        self.assertEqual(offset_ms, 1500)
        self.assertEqual(duration_ms, 750)

    def test_normalize_speaker_id(self):
        self.assertEqual(_normalize_speaker_id(2), 2)
        self.assertEqual(_normalize_speaker_id("2"), 2)
        self.assertEqual(_normalize_speaker_id("Guest-3"), 3)
        self.assertEqual(_normalize_speaker_id(""), -1)

    def test_transcription_quality_guardrail(self):
        weak = [{"start": "00:00", "end": "00:01", "text": "sim"} for _ in range(12)]
        self.assertFalse(_transcription_looks_valid(weak))

        good = [
            {"start": "00:01", "end": "00:03", "text": "Operador: boa tarde, poderia confirmar sua placa?"},
            {"start": "00:04", "end": "00:06", "text": "Motorista: sim, ABC1D23."},
            {"start": "00:08", "end": "00:12", "text": "Operador: obrigado, vou seguir com a tratativa."},
        ]
        self.assertTrue(_transcription_looks_valid(good))

    def test_should_preprocess_audio_for_azure(self):
        env_key = "AZURE_LOSSLESS_PREPROCESS_MIN_BYTES"
        previous = os.environ.get(env_key)
        try:
            os.environ.pop(env_key, None)
            self.assertFalse(_should_preprocess_audio_for_azure(1024, "audio/wav"))
            self.assertTrue(_should_preprocess_audio_for_azure(8 * 1024 * 1024, "audio/wav"))
            self.assertFalse(_should_preprocess_audio_for_azure(1024, "audio/mpeg"))
            self.assertTrue(_should_preprocess_audio_for_azure(24 * 1024 * 1024, "audio/mpeg"))

            os.environ[env_key] = "1024"
            self.assertTrue(_should_preprocess_audio_for_azure(1024, "audio/wav"))
        finally:
            if previous is None:
                os.environ.pop(env_key, None)
            else:
                os.environ[env_key] = previous

    def test_transcription_timeout_env_bounds(self):
        previous = os.environ.get("AZURE_TRANSCRIPTION_TIMEOUT_SECONDS")
        try:
            os.environ["AZURE_TRANSCRIPTION_TIMEOUT_SECONDS"] = "15"
            self.assertEqual(_get_transcription_timeout_seconds(), 60)

            os.environ["AZURE_TRANSCRIPTION_TIMEOUT_SECONDS"] = "700"
            self.assertEqual(_get_transcription_timeout_seconds(), 700)

            os.environ["AZURE_TRANSCRIPTION_TIMEOUT_SECONDS"] = "99999"
            self.assertEqual(_get_transcription_timeout_seconds(), 3600)

            os.environ["AZURE_TRANSCRIPTION_TIMEOUT_SECONDS"] = "invalid"
            self.assertEqual(_get_transcription_timeout_seconds(), 600)
        finally:
            if previous is None:
                os.environ.pop("AZURE_TRANSCRIPTION_TIMEOUT_SECONDS", None)
            else:
                os.environ["AZURE_TRANSCRIPTION_TIMEOUT_SECONDS"] = previous

    def test_whisper_temperature_env_bounds(self):
        previous = os.environ.get("AZURE_WHISPER_TEMPERATURE")
        try:
            os.environ["AZURE_WHISPER_TEMPERATURE"] = "0"
            self.assertEqual(_get_whisper_temperature(), 0.0)

            os.environ["AZURE_WHISPER_TEMPERATURE"] = "0.35"
            self.assertAlmostEqual(_get_whisper_temperature(), 0.35)

            os.environ["AZURE_WHISPER_TEMPERATURE"] = "-2"
            self.assertEqual(_get_whisper_temperature(), 0.0)

            os.environ["AZURE_WHISPER_TEMPERATURE"] = "9"
            self.assertEqual(_get_whisper_temperature(), 1.0)

            os.environ["AZURE_WHISPER_TEMPERATURE"] = "invalid"
            self.assertEqual(_get_whisper_temperature(), 0.0)
        finally:
            if previous is None:
                os.environ.pop("AZURE_WHISPER_TEMPERATURE", None)
            else:
                os.environ["AZURE_WHISPER_TEMPERATURE"] = previous

    def test_resolve_azure_whisper_config(self):
        keys = [
            "AZURE_WHISPER_ENDPOINT",
            "AZURE_WHISPER_KEY",
            "AZURE_WHISPER_DEPLOYMENT",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_KEY",
            "AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT",
        ]
        previous = {key: os.environ.get(key) for key in keys}
        try:
            os.environ["AZURE_WHISPER_ENDPOINT"] = "https://example.openai.azure.com"
            os.environ["AZURE_WHISPER_KEY"] = "test-key"
            os.environ["AZURE_WHISPER_DEPLOYMENT"] = "whisper-1"
            os.environ.pop("AZURE_OPENAI_ENDPOINT", None)
            os.environ.pop("AZURE_OPENAI_KEY", None)
            os.environ.pop("AZURE_OPENAI_TRANSCRIBE_DEPLOYMENT", None)

            endpoint, key = _resolve_azure_whisper_config()
            self.assertEqual(key, "test-key")
            self.assertIn("/openai/deployments/whisper-1/audio/transcriptions", endpoint or "")

            os.environ["AZURE_WHISPER_DEPLOYMENT"] = ""
            endpoint, key = _resolve_azure_whisper_config()
            self.assertIsNone(endpoint)
            self.assertIsNone(key)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_load_criteria_for_sector(self):
        # 1. Base cases (null/empty)
        self.assertIsNone(core.config.load_criteria_for_sector(None))
        self.assertIsNone(core.config.load_criteria_for_sector(""))
        self.assertIsNone(core.config.load_criteria_for_sector("setor_inexistente"))
        
        # 2. Direct mapping (should hit cache too)
        cadastro_criteria = core.config.load_criteria_for_sector("cadastro")
        self.assertIsNotNone(cadastro_criteria)
        self.assertTrue(len(cadastro_criteria) > 0)
        self.assertTrue(hasattr(cadastro_criteria[0], "label"))
        
        # 3. Alias mapping tests
        uti_criteria = core.config.load_criteria_for_sector("uti")
        self.assertIsNotNone(uti_criteria)
        
        grs_criteria = core.config.load_criteria_for_sector("grs")
        self.assertIsNotNone(grs_criteria)
        
        bas_criteria = core.config.load_criteria_for_sector("bas")
        self.assertIsNotNone(bas_criteria)
        
        rast_criteria = core.config.load_criteria_for_sector("rast")
        self.assertIsNotNone(rast_criteria)
        
        dist_criteria = core.config.load_criteria_for_sector("dist")
        self.assertIsNotNone(dist_criteria)
        
        # GRS and UTI should match
        self.assertEqual(len(uti_criteria), len(grs_criteria))
        self.assertEqual(uti_criteria[0].id, grs_criteria[0].id)

    def test_resolve_azure_gpt4o_diarize_config(self):
        keys = [
            "AZURE_GPT4O_DIARIZE_ENDPOINT",
            "AZURE_GPT4O_DIARIZE_KEY",
            "AZURE_GPT4O_DIARIZE_DEPLOYMENT",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_KEY",
            "AZURE_OPENAI_TRANSCRIBE_DIARIZE_DEPLOYMENT",
        ]
        previous = {key: os.environ.get(key) for key in keys}
        try:
            os.environ["AZURE_GPT4O_DIARIZE_ENDPOINT"] = "https://example.openai.azure.com"
            os.environ["AZURE_GPT4O_DIARIZE_KEY"] = "test-key"
            os.environ["AZURE_GPT4O_DIARIZE_DEPLOYMENT"] = "gpt-4o-transcribe-diarize"
            os.environ.pop("AZURE_OPENAI_ENDPOINT", None)
            os.environ.pop("AZURE_OPENAI_KEY", None)
            os.environ.pop("AZURE_OPENAI_TRANSCRIBE_DIARIZE_DEPLOYMENT", None)

            endpoint, key = _resolve_azure_gpt4o_diarize_config()
            self.assertEqual(key, "test-key")
            self.assertIn("/openai/deployments/gpt-4o-transcribe-diarize/audio/transcriptions", endpoint or "")

            os.environ["AZURE_GPT4O_DIARIZE_DEPLOYMENT"] = ""
            endpoint, key = _resolve_azure_gpt4o_diarize_config()
            self.assertIsNone(endpoint)
            self.assertIsNone(key)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_get_azure_gpt4o_diarize_auth_mode_defaults_by_endpoint_shape(self):
        previous = os.environ.get("AZURE_GPT4O_DIARIZE_AUTH_MODE")
        try:
            os.environ.pop("AZURE_GPT4O_DIARIZE_AUTH_MODE", None)
            self.assertEqual(
                _get_azure_gpt4o_diarize_auth_mode(
                    "https://auditoria-ia-e2.cognitiveservices.azure.com/openai/deployments/gpt/audio/transcriptions"
                ),
                "bearer",
            )
            self.assertEqual(
                _get_azure_gpt4o_diarize_auth_mode(
                    "https://auditoria-ia-e2.openai.azure.com/openai/deployments/gpt/audio/transcriptions"
                ),
                "api_key",
            )
        finally:
            if previous is None:
                os.environ.pop("AZURE_GPT4O_DIARIZE_AUTH_MODE", None)
            else:
                os.environ["AZURE_GPT4O_DIARIZE_AUTH_MODE"] = previous

    def test_get_azure_gpt4o_diarize_model_name_defaults(self):
        keys = ["AZURE_GPT4O_DIARIZE_MODEL", "AZURE_OPENAI_TRANSCRIBE_DIARIZE_MODEL"]
        previous = {key: os.environ.get(key) for key in keys}
        try:
            os.environ.pop("AZURE_GPT4O_DIARIZE_MODEL", None)
            os.environ.pop("AZURE_OPENAI_TRANSCRIBE_DIARIZE_MODEL", None)
            self.assertEqual(_get_azure_gpt4o_diarize_model_name(), "gpt-4o-transcribe-diarize")

            os.environ["AZURE_GPT4O_DIARIZE_MODEL"] = "custom-diarize"
            self.assertEqual(_get_azure_gpt4o_diarize_model_name(), "custom-diarize")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


    def test_transcribe_audio_uses_gpt4o_diarize_fallback_after_fast_weak_result(self):
        env_keys = ["AZURE_SPEECH_ENDPOINT", "AZURE_GPT4O_DIARIZE_FALLBACK"]
        previous = {key: os.environ.get(key) for key in env_keys}
        weak_segments = [{"start": "00:00", "end": "00:01", "text": "sim"}]
        gpt_segments = [
            {"start": "00:00", "end": "00:08", "text": "Operador: Bom dia, aqui e a central Opentech confirmando uma ocorrencia de entrega.", "speaker_source_ids": [1], "speaker_risk": "low"},
            {"start": "00:09", "end": "00:17", "text": "Motorista: Estou parado no cliente aguardando descarga e consigo atualizar a previsao.", "speaker_source_ids": [0], "speaker_risk": "low"},
            {"start": "00:18", "end": "00:26", "text": "Operador: Perfeito, vou registrar o caso e peco retorno em duas horas caso continue parado.", "speaker_source_ids": [1], "speaker_risk": "low"},
        ]
        try:
            os.environ["AZURE_SPEECH_ENDPOINT"] = "https://speech.test"
            os.environ["AZURE_TRANSCRIPTION_ENGINE"] = "fast"
            os.environ["AZURE_GPT4O_DIARIZE_FALLBACK"] = "true"
            os.environ["AZURE_GPT4O_DIARIZE_SMART_ROUTING"] = "false"

            with (
                patch.object(core.transcription, "AI_PROVIDER_PRIORITY", "azure"),
                patch.object(core.transcription, "AZURE_SPEECH_KEY", "speech-key"),
                patch(
                    "core.transcription.prepare_audio_for_azure",
                    return_value=PreparedAudio(audio_file=b"audio", mime_type="audio/wav"),
                ),
                patch("core.transcription._resolve_azure_whisper_config", return_value=(None, None)),
                patch(
                    "core.transcription._resolve_azure_gpt4o_diarize_config",
                    return_value=("https://example.test/openai/deployments/gpt/audio/transcriptions?api-version=2024-06-01", "gpt-key"),
                ),
                patch("core.transcription.transcribe_audio_azure", return_value=weak_segments) as mocked_fast,
                patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=gpt_segments) as mocked_gpt,
            ):
                result = asyncio.run(
                    services.transcribe_audio(
                        audio_file=b"audio",
                        mime_type="audio/wav",
                        operator_name="Ana",
                        driver_name="Motorista",
                    )
                )

            self.assertEqual(result, gpt_segments)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_transcribe_audio_keeps_fast_only_without_premium_fallback(self):
        env_keys = [
            "AZURE_SPEECH_ENDPOINT",
            "AZURE_TRANSCRIPTION_ENGINE",
            "AZURE_GPT4O_DIARIZE_FALLBACK",
            "AZURE_PREMIUM_TRANSCRIPTION_FALLBACK",
            "AZURE_WHISPER_FALLBACK",
            "AZURE_SDK_FALLBACK",
            "TRANSCRIPTION_CANDIDATE_SELECTOR_ENABLED",
        ]
        previous = {key: os.environ.get(key) for key in env_keys}
        weak_segments = [{"start": "00:00", "end": "00:01", "text": "sim"}]
        try:
            os.environ["AZURE_SPEECH_ENDPOINT"] = "https://speech.test"
            os.environ["AZURE_TRANSCRIPTION_ENGINE"] = "fast"
            os.environ["TRANSCRIPTION_CANDIDATE_SELECTOR_ENABLED"] = "false"
            for key in (
                "AZURE_GPT4O_DIARIZE_FALLBACK",
                "AZURE_PREMIUM_TRANSCRIPTION_FALLBACK",
                "AZURE_WHISPER_FALLBACK",
                "AZURE_SDK_FALLBACK",
            ):
                os.environ.pop(key, None)

            with (
                patch.object(core.transcription, "AI_PROVIDER_PRIORITY", "azure"),
                patch.object(core.transcription, "AZURE_SPEECH_KEY", "speech-key"),
                patch(
                    "core.transcription.prepare_audio_for_azure",
                    return_value=PreparedAudio(audio_file=b"audio", mime_type="audio/wav"),
                ),
                patch("core.transcription._resolve_azure_whisper_config", return_value=("https://whisper.test", "whisper-key")),
                patch(
                    "core.transcription._resolve_azure_gpt4o_diarize_config",
                    return_value=("https://example.test/openai/deployments/gpt/audio/transcriptions?api-version=2024-06-01", "gpt-key"),
                ),
                patch("core.transcription.transcribe_audio_azure", return_value=weak_segments) as mocked_fast,
                patch("core.transcription.transcribe_audio_gpt4o_diarize") as mocked_gpt,
            ):
                result, metadata = asyncio.run(
                    services.transcribe_audio(
                        audio_file=b"audio",
                        mime_type="audio/wav",
                        operator_name="Ana",
                        driver_name="Motorista",
                        return_metadata=True,
                    )
                )

            self.assertEqual(result, weak_segments)
            self.assertEqual(metadata["selected_strategy"], "fast")
            self.assertEqual([attempt["strategy"] for attempt in metadata["attempts"]], ["fast"])
            self.assertEqual(mocked_fast.call_count, 1)
            self.assertEqual(mocked_gpt.call_count, 0)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_transcribe_audio_uses_gpt4o_diarize_when_fast_diarization_is_weak(self):
        env_keys = ["AZURE_SPEECH_ENDPOINT", "AZURE_GPT4O_DIARIZE_FALLBACK"]
        previous = {key: os.environ.get(key) for key in env_keys}
        fast_segments = [
            {"start": "00:00", "end": "00:08", "text": "Operador: Bom dia, aqui e a central Opentech.", "speaker_source_ids": [0], "speaker_risk": "medium"},
            {"start": "00:09", "end": "00:17", "text": "Cliente: Estou parado no cliente aguardando descarga.", "speaker_source_ids": [0], "speaker_risk": "medium"},
            {"start": "00:18", "end": "00:26", "text": "Operador: Pode me confirmar sua placa, por favor?", "speaker_source_ids": [0], "speaker_risk": "medium"},
        ]
        gpt_segments = [
            {"start": "00:00", "end": "00:08", "text": "Operador: Bom dia, aqui e a central Opentech.", "speaker_source_ids": [1], "speaker_risk": "low"},
            {"start": "00:09", "end": "00:17", "text": "Cliente: Estou parado no cliente aguardando descarga.", "speaker_source_ids": [0], "speaker_risk": "low"},
            {"start": "00:18", "end": "00:26", "text": "Operador: Pode me confirmar sua placa, por favor?", "speaker_source_ids": [1], "speaker_risk": "low"},
        ]
        try:
            os.environ["AZURE_SPEECH_ENDPOINT"] = "https://speech.test"
            os.environ["AZURE_TRANSCRIPTION_ENGINE"] = "fast"
            os.environ["AZURE_GPT4O_DIARIZE_FALLBACK"] = "true"
            os.environ["AZURE_GPT4O_DIARIZE_SMART_ROUTING"] = "false"

            with (
                patch.object(core.transcription, "AI_PROVIDER_PRIORITY", "azure"),
                patch.object(core.transcription, "AZURE_SPEECH_KEY", "speech-key"),
                patch(
                    "core.transcription.prepare_audio_for_azure",
                    return_value=PreparedAudio(audio_file=b"audio", mime_type="audio/wav"),
                ),
                patch("core.transcription._resolve_azure_whisper_config", return_value=(None, None)),
                patch(
                    "core.transcription._resolve_azure_gpt4o_diarize_config",
                    return_value=("https://example.test/openai/deployments/gpt/audio/transcriptions?api-version=2024-06-01", "gpt-key"),
                ),
                patch("core.transcription.transcribe_audio_azure", return_value=fast_segments) as mocked_fast,
                patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=gpt_segments) as mocked_gpt,
            ):
                result = asyncio.run(
                    services.transcribe_audio(
                        audio_file=b"audio",
                        mime_type="audio/wav",
                        operator_name="Ana",
                        driver_name="Cliente",
                    )
                )

            self.assertEqual(result, gpt_segments)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_transcribe_audio_return_metadata_includes_selected_provider(self):
        env_keys = ["AZURE_SPEECH_ENDPOINT", "AZURE_GPT4O_DIARIZE_FALLBACK"]
        previous = {key: os.environ.get(key) for key in env_keys}
        fast_segments = [{"start": "00:00", "end": "00:01", "text": "sim"}]
        gpt_segments = [
            {"start": "00:00", "end": "00:08", "text": "Operador: Bom dia, aqui e a central Opentech.", "speaker_source_ids": [1], "speaker_risk": "low"},
            {"start": "00:09", "end": "00:17", "text": "Cliente: Estou parado no cliente aguardando descarga.", "speaker_source_ids": [0], "speaker_risk": "low"},
            {"start": "00:18", "end": "00:26", "text": "Operador: Pode me confirmar sua placa, por favor?", "speaker_source_ids": [1], "speaker_risk": "low"},
        ]
        try:
            os.environ["AZURE_SPEECH_ENDPOINT"] = "https://speech.test"
            os.environ["AZURE_TRANSCRIPTION_ENGINE"] = "fast"
            os.environ["AZURE_GPT4O_DIARIZE_FALLBACK"] = "true"
            os.environ["AZURE_GPT4O_DIARIZE_SMART_ROUTING"] = "false"

            with (
                patch.object(core.transcription, "AI_PROVIDER_PRIORITY", "azure"),
                patch.object(core.transcription, "AZURE_SPEECH_KEY", "speech-key"),
                patch(
                    "core.transcription.prepare_audio_for_azure",
                    return_value=PreparedAudio(audio_file=b"audio", mime_type="audio/wav"),
                ),
                patch("core.transcription._resolve_azure_whisper_config", return_value=(None, None)),
                patch(
                    "core.transcription._resolve_azure_gpt4o_diarize_config",
                    return_value=("https://example.test/openai/deployments/gpt/audio/transcriptions?api-version=2024-06-01", "gpt-key"),
                ),
                patch("core.transcription.transcribe_audio_azure", return_value=fast_segments),
                patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=gpt_segments),
            ):
                result, metadata = asyncio.run(
                    services.transcribe_audio(
                        audio_file=b"audio",
                        mime_type="audio/wav",
                        operator_name="Ana",
                        driver_name="Cliente",
                        return_metadata=True,
                    )
                )

            self.assertEqual(result, gpt_segments)
            self.assertEqual(metadata["selected_strategy"], "gpt4o_diarize")
            self.assertEqual(metadata["selected_provider"], "GPT-4o-transcribe-diarize")
            self.assertEqual(metadata["selected_reason"], "accepted")
            self.assertEqual(metadata["attempts"][0]["status"], "insufficient")
            self.assertEqual(metadata["attempts"][1]["status"], "accepted")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_transcribe_audio_keeps_fast_first_when_fast_is_valid(self):
        env_keys = ["AZURE_SPEECH_ENDPOINT", "AZURE_GPT4O_DIARIZE_FALLBACK"]
        previous = {key: os.environ.get(key) for key in env_keys}
        fast_segments = [
            {"start": "00:00", "end": "00:08", "text": "Operador: Bom dia, aqui e a central Opentech confirmando uma ocorrencia de entrega.", "speaker_source_ids": [1], "speaker_risk": "low"},
            {"start": "00:09", "end": "00:17", "text": "Cliente: Estou parado no cliente aguardando descarga e consigo atualizar a previsao.", "speaker_source_ids": [0], "speaker_risk": "low"},
            {"start": "00:18", "end": "00:26", "text": "Operador: Perfeito, vou registrar o caso e peco retorno em duas horas caso continue parado.", "speaker_source_ids": [1], "speaker_risk": "low"},
        ]
        try:
            os.environ["AZURE_SPEECH_ENDPOINT"] = "https://speech.test"
            os.environ["AZURE_TRANSCRIPTION_ENGINE"] = "fast"
            os.environ["AZURE_GPT4O_DIARIZE_FALLBACK"] = "true"
            os.environ["AZURE_GPT4O_DIARIZE_SMART_ROUTING"] = "false"

            with (
                patch.object(core.transcription, "AI_PROVIDER_PRIORITY", "azure"),
                patch.object(core.transcription, "AZURE_SPEECH_KEY", "speech-key"),
                patch(
                    "core.transcription.prepare_audio_for_azure",
                    return_value=PreparedAudio(audio_file=b"audio", mime_type="audio/wav"),
                ),
                patch("core.transcription._resolve_azure_whisper_config", return_value=(None, None)),
                patch(
                    "core.transcription._resolve_azure_gpt4o_diarize_config",
                    return_value=("https://example.test/openai/deployments/gpt/audio/transcriptions?api-version=2024-06-01", "gpt-key"),
                ),
                patch("core.transcription.transcribe_audio_azure", return_value=fast_segments) as mocked_fast,
                patch("core.transcription.transcribe_audio_gpt4o_diarize", side_effect=Exception("Failed")) as mocked_gpt,
            ):
                result = asyncio.run(
                    services.transcribe_audio(
                        audio_file=b"audio",
                        mime_type="audio/wav",
                        operator_name="Ana",
                        driver_name="Cliente",
                    )
                )

            self.assertEqual(result, fast_segments)
            self.assertEqual(mocked_gpt.call_count, 0)
            self.assertEqual(mocked_fast.call_count, 1)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_transcribe_audio_waits_for_gpt4o_when_selector_needs_review(self):
        env_keys = ["AZURE_SPEECH_ENDPOINT", "AZURE_GPT4O_DIARIZE_FALLBACK"]
        previous = {key: os.environ.get(key) for key in env_keys}

        def tagged_segments(source: str) -> list[dict]:
            return [
                {"start": "00:00", "end": "00:08", "text": "Operador: Bom dia, aqui e a central Opentech.", "source": source, "speaker_source_ids": [1], "speaker_risk": "low"},
                {"start": "00:09", "end": "00:17", "text": "Cliente: Estou parado no cliente aguardando descarga.", "source": source, "speaker_source_ids": [0], "speaker_risk": "low"},
                {"start": "00:18", "end": "00:26", "text": "Operador: Vou registrar a tratativa e acompanhar o caso.", "source": source, "speaker_source_ids": [1], "speaker_risk": "low"},
            ]

        fast_segments = tagged_segments("fast")
        whisper_segments = tagged_segments("whisper")
        gpt_segments = tagged_segments("gpt4o")

        def transcribe_azure_side_effect(*_args, **kwargs):
            if kwargs.get("endpoint_override"):
                return whisper_segments
            return fast_segments

        def score_by_source(segments, _diarization_reference):
            source = segments[0].get("source") if segments else ""
            return {"fast": 1000, "whisper": 960, "gpt4o": 1400}.get(source, 0)

        try:
            os.environ["AZURE_SPEECH_ENDPOINT"] = "https://speech.test"
            os.environ["AZURE_TRANSCRIPTION_ENGINE"] = "fast"
            os.environ["AZURE_GPT4O_DIARIZE_FALLBACK"] = "true"
            os.environ["AZURE_GPT4O_DIARIZE_SMART_ROUTING"] = "false"

            with (
                patch.object(core.transcription, "AI_PROVIDER_PRIORITY", "azure"),
                patch.object(core.transcription, "AZURE_SPEECH_KEY", "speech-key"),
                patch(
                    "core.transcription.prepare_audio_for_azure",
                    return_value=PreparedAudio(audio_file=b"audio", mime_type="audio/wav"),
                ),
                patch("core.transcription._resolve_azure_whisper_config", return_value=("https://whisper.test", "whisper-key")),
                patch(
                    "core.transcription._resolve_azure_gpt4o_diarize_config",
                    return_value=("https://example.test/openai/deployments/gpt/audio/transcriptions?api-version=2024-06-01", "gpt-key"),
                ),
                patch("core.transcription.transcribe_audio_azure", side_effect=transcribe_azure_side_effect) as mocked_azure,
                patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=gpt_segments) as mocked_gpt,
                patch("core.transcription._transcription_candidate_is_acceptable", return_value=True),
                patch("core.transcription._score_transcription_candidate", side_effect=score_by_source),
            ):
                result, metadata = asyncio.run(
                    services.transcribe_audio(
                        audio_file=b"audio",
                        mime_type="audio/wav",
                        operator_name="Ana",
                        driver_name="Cliente",
                        return_metadata=True,
                    )
                )

            self.assertEqual(result, gpt_segments)
            self.assertEqual(metadata["selected_strategy"], "gpt4o_diarize")
            self.assertEqual([attempt["strategy"] for attempt in metadata["attempts"]], ["fast", "whisper", "gpt4o_diarize"])
            self.assertEqual(mocked_azure.call_count, 2)
            self.assertEqual(mocked_gpt.call_count, 1)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_process_audit_with_ai_includes_transcription_provider_metadata(self):
        transcription = [
            {"start": "00:00", "end": "00:08", "text": "Operador: Bom dia, aqui e a central Opentech.", "speaker_source_ids": [1], "speaker_risk": "low"},
            {"start": "00:09", "end": "00:17", "text": "Cliente: Estou parado no cliente aguardando descarga.", "speaker_source_ids": [0], "speaker_risk": "low"},
        ]
        provider_metadata = {
            "selected_strategy": "fast",
            "selected_provider": "Azure Fast Transcription",
            "selected_reason": "accepted",
            "attempts": [
                {
                    "strategy": "fast",
                    "provider": "Azure Fast Transcription",
                    "status": "accepted",
                    "score": 999,
                }
            ],
        }
        alert = AuditAlert(id="A4", label="Cliente", context="Contato com cliente", criteria=[])
        evaluation = {"summary": "ok", "details": []}

        with (
            patch.dict(os.environ, {"AUDIT_ALLOW_OFFICIAL_CRITERIA_TEST_FALLBACK": "true"}, clear=False),
            patch("core.audit.transcribe_audio", new=AsyncMock(return_value=(transcription, provider_metadata))),
            patch("core.audit.evaluate_with_ai_priority", new=AsyncMock(return_value=evaluation)),
        ):
            result, _, _ = asyncio.run(
                services.process_audit_with_ai(
                    audio_file=b"audio",
                    mime_type="audio/wav",
                    alert=alert,
                    operator_name="Ana",
                    operator_id="OP-1",
                    sector_id="logistica",
                )
            )

        self.assertIsNotNone(result.audio_quality)
        self.assertEqual(result.audio_quality["transcription_provider"]["selected_strategy"], "fast")
        self.assertEqual(result.audio_quality["transcription_provider"]["selected_reason"], "accepted")
        self.assertEqual(result.audio_quality["transcription_provider"]["attempts"][0]["status"], "accepted")

    def test_process_audit_with_ai_uses_official_db_criteria_over_payload(self):
        transcription = [
            {"start": "00:00", "end": "00:08", "text": "Operador: Bom dia, aqui e a central Opentech."},
        ]
        stale_alert = AuditAlert(
            id="ALERTA-DB",
            label="Payload antigo",
            context="Payload antigo",
            criteria=[AuditCriterion(id="OLD", label="Antigo", weight=1.0)],
        )
        official_rows = [
            {
                "id": 99,
                "alert_id": "ALERTA-DB",
                "chave": "NEW",
                "label": "Novo criterio oficial",
                "weight": 10,
                "description": "Oficial",
                "deflator": 0,
                "evaluation_type": "auto",
            }
        ]
        evaluation = {
            "summary": "ok",
            "details": [
                {
                    "criterionId": "NEW",
                    "status": "pass",
                    "comment": "ok",
                    "evidence_text": "Operador: Bom dia, aqui e a central Opentech.",
                }
            ],
        }

        with (
            patch("core.audit.DETERMINISTIC_MODE", False),
            patch("repositories.admin_criteria.get_criteria", return_value=official_rows),
            patch("repositories.admin_criteria.get_alerts", return_value=[
                {"id": "ALERTA-DB", "label": "Catalogo oficial", "context": "Contexto oficial"}
            ]),
            patch("core.audit.transcribe_audio", new=AsyncMock(return_value=(transcription, {}))),
            patch("core.audit.evaluate_with_ai_priority", new=AsyncMock(return_value=evaluation)) as mocked_evaluate,
        ):
            result, _, _ = asyncio.run(
                services.process_audit_with_ai(
                    audio_file=b"audio",
                    mime_type="audio/wav",
                    alert=stale_alert,
                    operator_name="Ana",
                    operator_id="OP-1",
                    sector_id="logistica",
                )
            )

        used_alert = mocked_evaluate.call_args.args[1]
        used_criteria = mocked_evaluate.call_args.args[2]
        self.assertEqual(used_alert.label, "Catalogo oficial")
        self.assertEqual([criterion.id for criterion in used_criteria], ["NEW"])
        self.assertEqual(result.maxPossibleScore, 10)
        self.assertEqual(result.details[0].label, "Novo criterio oficial")

    def test_should_use_gpt4o_diarize_as_primary_for_mondelez(self):
        env_keys = ["AZURE_GPT4O_DIARIZE_PRIMARY_SECTORS"]
        previous = {key: os.environ.get(key) for key in env_keys}
        try:
            os.environ["AZURE_GPT4O_DIARIZE_PRIMARY_SECTORS"] = "mondelez"
            self.assertTrue(
                _should_use_gpt4o_diarize_as_primary(
                    AuditAlert(id="A1", label="Monitoramento Mondelez", context="Torre Mondelez", criteria=[]),
                    "mondelez",
                )
            )
            self.assertFalse(
                _should_use_gpt4o_diarize_as_primary(
                    AuditAlert(id="A2", label="Parada Indevida - Cliente", context="Contato com cliente", criteria=[]),
                    "logistica",
                )
            )
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_should_promote_prescan_to_gpt4o_when_excerpt_collapses_speakers(self):
        excerpt_segments = [
            {"start": "00:00", "end": "00:06", "text": "Telefonia: Ola, bem-vindo a Torre Mondelez. Digite 1 para devolucao parcial."},
            {"start": "00:07", "end": "00:12", "text": "Operador: Torre Mondelez, boa tarde, em que posso ajudar?", "speaker_source_ids": [0], "speaker_risk": "medium"},
            {"start": "00:13", "end": "00:18", "text": "Cliente: Estou com devolucao parcial aqui no cliente.", "speaker_source_ids": [0], "speaker_risk": "medium"},
        ]
        self.assertTrue(_should_promote_prescan_to_gpt4o(excerpt_segments, "Cliente"))

    def test_should_not_promote_mondelez_prescan_to_gpt4o_when_excerpt_is_stable(self):
        excerpt_segments = [
            {"start": "00:00", "end": "00:06", "text": "Telefonia: Ola, bem-vindo a Torre Mondelez. Digite 1 para devolucao parcial."},
            {"start": "00:07", "end": "00:12", "text": "Operador: Torre Mondelez, boa tarde, em que posso ajudar?", "speaker_source_ids": [1], "speaker_risk": "low"},
            {"start": "00:13", "end": "00:18", "text": "Cliente: Estou com devolucao parcial aqui no cliente.", "speaker_source_ids": [0], "speaker_risk": "low"},
        ]
        self.assertFalse(_should_promote_prescan_to_gpt4o(excerpt_segments, "Cliente"))

    def test_should_use_gpt4o_diarize_as_primary_for_audio_respects_smart_routing(self):
        env_keys = ["AZURE_GPT4O_DIARIZE_PRIMARY_SECTORS", "AZURE_GPT4O_DIARIZE_SMART_ROUTING"]
        previous = {key: os.environ.get(key) for key in env_keys}
        try:
            os.environ["AZURE_GPT4O_DIARIZE_PRIMARY_SECTORS"] = "mondelez"
            os.environ["AZURE_GPT4O_DIARIZE_SMART_ROUTING"] = "true"
            with (
                patch("core.transcription.extract_audio_excerpt", return_value=b"excerpt"),
                patch(
                    "services.transcribe_audio_azure",
                    return_value=[
                        {"start": "00:00", "end": "00:06", "text": "Telefonia: Ola, bem-vindo a Torre Mondelez. Digite 1 para devolucao parcial."},
                        {"start": "00:07", "end": "00:12", "text": "Operador: Torre Mondelez, boa tarde, em que posso ajudar?", "speaker_source_ids": [0], "speaker_risk": "medium"},
                        {"start": "00:13", "end": "00:18", "text": "Cliente: Estou com devolucao parcial aqui no cliente.", "speaker_source_ids": [0], "speaker_risk": "medium"},
                    ],
                ),
            ):
                self.assertTrue(
                    _should_use_gpt4o_diarize_as_primary_for_audio(
                        b"audio",
                        "audio/wav",
                        AuditAlert(id="A3", label="Monitoramento Mondelez", context="Torre Mondelez", criteria=[]),
                        "mondelez",
                        "Operador",
                        "Cliente",
                        gpt4o_diarize_available=True,
                    )
                )
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_transcribe_audio_keeps_fast_first_for_mondelez_when_engine_fast(self):
        env_keys = ["AZURE_SPEECH_ENDPOINT", "AZURE_GPT4O_DIARIZE_FALLBACK", "AZURE_GPT4O_DIARIZE_PRIMARY_SECTORS"]
        previous = {key: os.environ.get(key) for key in env_keys}
        fast_segments = [
            {"start": "00:00", "end": "00:08", "text": "Telefonia: Ola, bem-vindo a Torre Mondelez.", "speaker_source_ids": [2], "speaker_risk": "low"},
            {"start": "00:09", "end": "00:17", "text": "Operador: Torre Mondelez, boa tarde, em que posso ajudar?", "speaker_source_ids": [1], "speaker_risk": "low"},
            {"start": "00:18", "end": "00:26", "text": "Cliente: Estou com devolucao parcial aqui no cliente.", "speaker_source_ids": [0], "speaker_risk": "low"},
        ]
        gpt_segments = [
            {"start": "00:00", "end": "00:08", "text": "Telefonia: Ola, bem-vindo a Torre Mondelez.", "speaker_source_ids": [2], "speaker_risk": "low"},
            {"start": "00:09", "end": "00:17", "text": "Operador: Torre Mondelez, boa tarde, em que posso ajudar?", "speaker_source_ids": [1], "speaker_risk": "low"},
            {"start": "00:18", "end": "00:26", "text": "Cliente: Estou com devolucao parcial aqui no cliente.", "speaker_source_ids": [0], "speaker_risk": "low"},
        ]
        try:
            os.environ["AZURE_SPEECH_ENDPOINT"] = "https://speech.test"
            os.environ["AZURE_TRANSCRIPTION_ENGINE"] = "fast"
            os.environ["AZURE_GPT4O_DIARIZE_FALLBACK"] = "true"
            os.environ["AZURE_GPT4O_DIARIZE_SMART_ROUTING"] = "false"
            os.environ["AZURE_GPT4O_DIARIZE_PRIMARY_SECTORS"] = "mondelez"

            with (
                patch.object(core.transcription, "AI_PROVIDER_PRIORITY", "azure"),
                patch.object(core.transcription, "AZURE_SPEECH_KEY", "speech-key"),
                patch(
                    "core.transcription.prepare_audio_for_azure",
                    return_value=PreparedAudio(audio_file=b"audio", mime_type="audio/wav"),
                ),
                patch("core.transcription._resolve_azure_whisper_config", return_value=(None, None)),
                patch(
                    "core.transcription._resolve_azure_gpt4o_diarize_config",
                    return_value=("https://example.test/openai/deployments/gpt/audio/transcriptions?api-version=2024-06-01", "gpt-key"),
                ),
                patch("core.transcription._should_use_gpt4o_diarize_as_primary_for_audio", return_value=True),
                patch("core.transcription.transcribe_audio_azure", return_value=fast_segments) as mocked_fast,
                patch("core.transcription.transcribe_audio_gpt4o_diarize", return_value=gpt_segments) as mocked_gpt,
            ):
                result = asyncio.run(
                    services.transcribe_audio(
                        audio_file=b"audio",
                        mime_type="audio/wav",
                        operator_name="Ana",
                        driver_name="Cliente",
                        alert=AuditAlert(id="A3", label="Monitoramento Mondelez", context="Torre Mondelez", criteria=[]),
                        sector_id="mondelez",
                    )
                )

            self.assertEqual(result, fast_segments)
            self.assertEqual(mocked_gpt.call_count, 0)
            self.assertEqual(mocked_fast.call_count, 1)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_should_discard_whisper_segment(self):
        self.assertTrue(
            _should_discard_whisper_segment(
                "",
                no_speech_prob=0.0,
                avg_logprob=0.0,
                compression_ratio=0.0,
                duracao_seconds=1.0,
                start_seconds=0.0,
            )
        )

        self.assertTrue(
            _should_discard_whisper_segment(
                "ruido",
                no_speech_prob=0.96,
                avg_logprob=-1.1,
                compression_ratio=1.0,
                duracao_seconds=0.8,
                start_seconds=10.0,
            )
        )

        self.assertFalse(
            _should_discard_whisper_segment(
                "operador boa tarde",
                no_speech_prob=0.02,
                avg_logprob=-0.1,
                compression_ratio=1.2,
                duracao_seconds=1.4,
                start_seconds=3.0,
            )
        )

    def test_should_replace_whisper_segment_with_inaudivel(self):
        self.assertTrue(
            _should_replace_whisper_segment_with_inaudivel(
                "eu falo com voce",
                no_speech_prob=0.20,
                avg_logprob=-0.10,
                compression_ratio=1.0,
                duracao_seconds=1.0,
            )
        )
        self.assertTrue(
            _should_replace_whisper_segment_with_inaudivel(
                "alou",
                no_speech_prob=0.70,
                avg_logprob=-0.20,
                compression_ratio=1.9,
                duracao_seconds=1.0,
            )
        )
        self.assertFalse(
            _should_replace_whisper_segment_with_inaudivel(
                "operador confirma temperatura em menos cinco",
                no_speech_prob=0.05,
                avg_logprob=-0.05,
                compression_ratio=1.1,
                duracao_seconds=2.0,
            )
        )

    def test_filter_hallucinations_blacklist_term(self):
        text = "Operador: estou vendo um antropologo aqui no visor"
        cleaned = filter_hallucinations(text)
        self.assertNotIn("antropologo", cleaned.lower())

    def test_filter_hallucinations_phrase_replacement_to_inaudivel(self):
        text = "Operador: eu falo com você"
        cleaned = filter_hallucinations(text)
        self.assertIn("[inaudível]", cleaned.lower())

    def test_deduplicate_preserves_speaker_when_same_window(self):
        segments = [
            {"start": "00:35", "end": "00:36", "text": "Operador: Pode confirmar a temperatura?"},
            {"start": "00:35", "end": "00:36", "text": "Motorista: Menos cinco, continuo."},
        ]
        deduped = deduplicate_transcription_segments(segments)
        self.assertEqual(len(deduped), 2)
        self.assertTrue(deduped[0]["text"].startswith("Operador:"))
        self.assertTrue(deduped[1]["text"].startswith("Motorista:"))

    def test_build_diarization_quality_flags_fragmentation(self):
        segments = [
            {
                "start": "00:01",
                "end": "00:04",
                "text": "Operador: Bom dia, aqui e da central Opentech.",
                "speaker_source_ids": [1],
                "speaker_persona_ids": [1, 3],
                "speaker_confidence": 0.91,
                "speaker_risk": "medium",
                "speaker_ambiguous": False,
            },
            {
                "start": "00:05",
                "end": "00:07",
                "text": "Motorista: To descarregando aqui no cliente.",
                "speaker_source_ids": [0],
                "speaker_persona_ids": [0],
                "speaker_confidence": 0.84,
                "speaker_risk": "low",
                "speaker_ambiguous": False,
            },
            {
                "start": "00:08",
                "end": "00:10",
                "text": "Operador: Preciso confirmar a previsao de saida.",
                "speaker_source_ids": [3],
                "speaker_persona_ids": [1, 3],
                "speaker_confidence": 0.78,
                "speaker_risk": "medium",
                "speaker_ambiguous": False,
            },
        ]

        quality = build_diarization_quality(segments)

        self.assertIsInstance(quality, dict)
        self.assertIn("diarization", quality)
        self.assertTrue(quality["diarization"]["fragmented"])
        self.assertEqual(quality["diarization"]["swap_risk"], "medium")
        self.assertEqual(quality["diarization"]["operator_speaker_ids"], [1, 3])
        self.assertEqual(quality["diarization"]["interlocutor_speaker_ids"], [0])

    def test_build_diarization_quality_allows_support_point_handoff_without_forcing_three_by_default(self):
        segments = [
            {
                "start": "00:01",
                "end": "00:03",
                "text": "Operador: Aqui e a central Opentech.",
                "speaker_source_ids": [1],
                "speaker_risk": "low",
            },
            {
                "start": "00:04",
                "end": "00:06",
                "text": "Ponto de Apoio: O motorista esta aqui.",
                "speaker_source_ids": [0],
                "speaker_risk": "low",
            },
            {
                "start": "00:07",
                "end": "00:09",
                "text": "Ponto de Apoio: Vou chamar ele.",
                "speaker_source_ids": [2],
                "speaker_risk": "low",
            },
        ]

        quality = build_diarization_quality(
            segments,
            {"diarization_reference": build_diarization_reference("Ponto de Apoio")},
        )

        self.assertFalse(quality["diarization"]["fragmented"])
        self.assertEqual(quality["diarization"]["expected_max_speakers"], 2)
        self.assertEqual(quality["diarization"]["effective_max_speakers"], 3)
        self.assertTrue(quality["diarization"]["conference_possible"])
        self.assertTrue(quality["diarization"]["handoff_detected"])
        self.assertEqual(quality["diarization"]["swap_risk"], "low")

    def test_build_diarization_quality_ignores_telephony_segments(self):
        segments = [
            {
                "start": "00:00",
                "end": "00:07",
                "text": "Telefonia: Ola, bem vindo a Torre Mondelez. Digite 1 para devolucao parcial.",
                "speaker_source_ids": [9],
                "speaker_risk": "high",
                "speaker_ambiguous": True,
            },
            {
                "start": "00:08",
                "end": "00:10",
                "text": "Operador: Boa tarde, em que posso ajudar?",
                "speaker_source_ids": [1],
                "speaker_risk": "medium",
                "speaker_ambiguous": False,
            },
            {
                "start": "00:11",
                "end": "00:15",
                "text": "Cliente: Estou ligando sobre uma ocorrencia.",
                "speaker_source_ids": [0],
                "speaker_risk": "low",
                "speaker_ambiguous": False,
            },
        ]

        quality = build_diarization_quality(segments)

        self.assertEqual(quality["diarization"]["raw_speaker_count"], 2)
        self.assertEqual(quality["diarization"]["telephony_segment_count"], 1)
        self.assertEqual(quality["diarization"]["swap_risk"], "low")
        self.assertIn("segmentos_de_telefonia_ignorados_na_diarizacao", quality["diarization"]["notes"])

    def test_build_diarization_quality_keeps_single_human_speaker_as_non_low_risk(self):
        segments = [
            {
                "start": "00:00",
                "end": "00:07",
                "text": "Telefonia: Ola, bem-vindo a Torre Mondelez. Digite 1 para devolucao parcial.",
                "speaker_source_ids": [9],
                "speaker_risk": "high",
                "speaker_ambiguous": True,
            },
            {
                "start": "00:08",
                "end": "00:12",
                "text": "Operador: Torre Mondelez, boa tarde, em que posso ajudar?",
                "speaker_source_ids": [1],
                "speaker_risk": "low",
                "speaker_ambiguous": False,
            },
        ]

        quality = build_diarization_quality(segments)

        self.assertEqual(quality["diarization"]["raw_speaker_count"], 1)
        self.assertEqual(quality["diarization"]["swap_risk"], "medium")
        self.assertEqual(quality["diarization"]["quality"], "baixa")
        self.assertTrue(quality["review_recommended"])
        self.assertEqual(quality["review_priority"], "medium")
        self.assertIn("apenas_um_speaker_humano_detectado", quality["review_reasons"])

    def test_build_diarization_quality_recommends_review_when_only_best_candidate_survives(self):
        segments = [
            {
                "start": "00:01",
                "end": "00:04",
                "text": "Operador: Bom dia, aqui e a central Opentech.",
                "speaker_source_ids": [1],
                "speaker_risk": "low",
            },
            {
                "start": "00:05",
                "end": "00:08",
                "text": "Cliente: Estou no cliente aguardando descarga.",
                "speaker_source_ids": [0],
                "speaker_risk": "low",
            },
        ]

        quality = build_diarization_quality(
            segments,
            {
                "transcription_provider": {
                    "selected_strategy": "fast",
                    "selected_provider": "Azure Fast Transcription",
                    "selected_reason": "best_candidate",
                    "attempts": [
                        {
                            "strategy": "fast",
                            "provider": "Azure Fast Transcription",
                            "status": "error",
                            "error": "server_error",
                        },
                        {
                            "strategy": "gpt4o_diarize",
                            "provider": "GPT-4o-transcribe-diarize",
                            "status": "insufficient",
                            "score": 420,
                        },
                    ],
                }
            },
        )

        self.assertTrue(quality["review_recommended"])
        self.assertEqual(quality["review_priority"], "medium")
        self.assertIn("nenhum_provedor_passou_na_validacao_forte", quality["review_reasons"])
        self.assertIn("falhas_em_provedores_de_transcricao", quality["review_reasons"])

    def test_pergunta_operacional_vs_social(self):
        self.assertTrue(
            SpeakerDetectionService.eh_pergunta_ou_direcionamento_operador(
                "pode confirmar sua placa?"
            )
        )
        self.assertTrue(
            SpeakerDetectionService.eh_pergunta_ou_direcionamento_operador(
                "qual a placa do cavalo?"
            )
        )
        self.assertFalse(
            SpeakerDetectionService.eh_pergunta_ou_direcionamento_operador(
                "tudo bem, e voce?"
            )
        )

    def test_classificar_speakers_sem_diarizacao_turnos_basicos(self):
        frases = [
            RawPhrase(
                timestamp=timedelta(seconds=0),
                duration_seconds=2.5,
                speaker_id=-1,
                texto="Boa tarde aqui e da central opentech pode confirmar sua placa",
                texto_normalizado=SpeakerDetectionService.normalizar_texto(
                    "Boa tarde aqui e da central opentech pode confirmar sua placa"
                ),
            ),
            RawPhrase(
                timestamp=timedelta(seconds=3),
                duration_seconds=2.0,
                speaker_id=-1,
                texto="sim abc1d23",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("sim abc1d23"),
            ),
            RawPhrase(
                timestamp=timedelta(seconds=6),
                duration_seconds=2.5,
                speaker_id=-1,
                texto="qual o local da ocorrencia",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("qual o local da ocorrencia"),
            ),
            RawPhrase(
                timestamp=timedelta(seconds=9),
                duration_seconds=2.0,
                speaker_id=-1,
                texto="to no km cento e vinte e tres",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("to no km cento e vinte e tres"),
            ),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(frases, "Operador", "Motorista")
        self.assertEqual([s.speaker for s in segmentos], ["Operador", "Motorista", "Operador", "Motorista"])

    def test_classificar_speakers_sem_diarizacao_pergunta_social(self):
        frases = [
            RawPhrase(
                timestamp=timedelta(seconds=0),
                duration_seconds=2.0,
                speaker_id=-1,
                texto="Boa tarde aqui e da central opentech",
                texto_normalizado=SpeakerDetectionService.normalizar_texto(
                    "Boa tarde aqui e da central opentech"
                ),
            ),
            RawPhrase(
                timestamp=timedelta(seconds=2),
                duration_seconds=1.8,
                speaker_id=-1,
                texto="tudo bem e voce",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("tudo bem e voce"),
            ),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(frases, "Operador", "Motorista")
        self.assertEqual([s.speaker for s in segmentos], ["Operador", "Motorista"])

    def test_classificar_speakers_sem_diarizacao_resposta_social_do_operador(self):
        frases = [
            RawPhrase(
                timestamp=timedelta(seconds=0),
                duration_seconds=2.0,
                speaker_id=-1,
                texto="Aqui e da central tudo bem?",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("Aqui e da central tudo bem?"),
            ),
            RawPhrase(
                timestamp=timedelta(seconds=2),
                duration_seconds=1.5,
                speaker_id=-1,
                texto="tudo bem e voce?",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("tudo bem e voce?"),
            ),
            RawPhrase(
                timestamp=timedelta(seconds=4),
                duration_seconds=1.5,
                speaker_id=-1,
                texto="eu to bem tambem",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("eu to bem tambem"),
            ),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(frases, "Operador", "Motorista")
        self.assertEqual([s.speaker for s in segmentos], ["Operador", "Motorista", "Operador"])

    def test_classificar_speakers_sem_diarizacao_contexto_institucional(self):
        frases = [
            RawPhrase(
                timestamp=timedelta(seconds=0),
                duration_seconds=3.0,
                speaker_id=-1,
                texto="Eu tenho um relato com o senhor",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("Eu tenho um relato com o senhor"),
            ),
            RawPhrase(
                timestamp=timedelta(seconds=3),
                duration_seconds=4.0,
                speaker_id=-1,
                texto="o codigo desse cliente e 1002 6266 com devolucao parcial por divergencia de preco e erro interno",
                texto_normalizado=SpeakerDetectionService.normalizar_texto(
                    "o codigo desse cliente e 1002 6266 com devolucao parcial por divergencia de preco e erro interno"
                ),
            ),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(frases, "Operador", "Motorista")
        self.assertEqual([s.speaker for s in segmentos], ["Operador", "Operador"])

    def test_classificar_speakers_sem_diarizacao_gostaria_de_saber(self):
        frases = [
            RawPhrase(
                timestamp=timedelta(seconds=0),
                duration_seconds=2.0,
                speaker_id=-1,
                texto="Alo boa tarde",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("Alo boa tarde"),
            ),
            RawPhrase(
                timestamp=timedelta(seconds=2),
                duration_seconds=4.0,
                speaker_id=-1,
                texto="Aqui e Thais da JBS eu gostaria de saber referente a carga a temperatura",
                texto_normalizado=SpeakerDetectionService.normalizar_texto(
                    "Aqui e Thais da JBS eu gostaria de saber referente a carga a temperatura"
                ),
            ),
        ]

        segmentos = SpeakerDetectionService.classificar_speakers(frases, "Operador", "Motorista")
        self.assertEqual([s.speaker for s in segmentos], ["Operador", "Operador"])

    def test_resposta_curta_interlocutor_social(self):
        self.assertTrue(
            SpeakerDetectionService.eh_resposta_curta_interlocutor_contextual("tudo bem, e voce?")
        )

    def test_promover_turno_operacional_endereco_continuacao(self):
        segmentos = [
            SegmentoFormatado(
                timestamp=timedelta(seconds=31),
                speaker="Operador",
                texto="... o cliente de Ciabras, que fica na rua",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("... o cliente de Ciabras, que fica na rua"),
                duracao_seconds=3.0,
            ),
            SegmentoFormatado(
                timestamp=timedelta(seconds=35),
                speaker="Motorista",
                texto="Cardoso de Almeida 472, em Sao Paulo",
                texto_normalizado=SpeakerDetectionService.normalizar_texto("Cardoso de Almeida 472, em Sao Paulo"),
                duracao_seconds=2.0,
            ),
        ]

        promovidos = SpeakerDetectionService.promover_turnos_operacionais(segmentos, "Operador", "Motorista")
        self.assertEqual([s.speaker for s in promovidos], ["Operador", "Operador"])

    def test_normalize_speaker_prefix(self):
        """Test speaker normalization and company name correction"""
        # Prefix normalization
        self.assertEqual(normalize_speaker_prefix("operador: ola", "Op", "Mot"), "Op: ola")
        self.assertEqual(normalize_speaker_prefix("cliente: sim", "Op", "Mot"), "Mot: sim")
        
        # Case insensitivity
        self.assertEqual(normalize_speaker_prefix("OPERADOR: ola", "Op", "Mot"), "Op: ola")
        
        # No change if unknown
        self.assertEqual(normalize_speaker_prefix("random: ola", "Op", "Mot"), "random: ola")

    def test_normalize_speaker_prefix_accepts_accented_terms(self):
        self.assertEqual(normalize_speaker_prefix("Vítima: sim", "Op", "Mot"), "Mot: sim")
        self.assertEqual(normalize_speaker_prefix("Robô: digite a opção 1", "Op", "Mot"), "Telefonia: digite a opção 1")

    def test_normalize_speaker_prefix_detects_ura_without_depending_on_accents(self):
        accented = "Sua ligação é muito importante, aguarde na linha."
        plain = "Sua ligacao e muito importante, aguarde na linha."
        self.assertEqual(normalize_speaker_prefix(accented, "Op", "Mot"), f"Telefonia: {accented}")
        self.assertEqual(normalize_speaker_prefix(plain, "Op", "Mot"), f"Telefonia: {plain}")

    def test_infer_interlocutor_label(self):
        self.assertEqual(infer_interlocutor_label(self.alert), "Motorista")
        self.assertEqual(
            infer_interlocutor_label(
                AuditAlert(id="A1", label="Parada Indevida - Cliente", context="Contato com cliente", criteria=[])
            ),
            "Cliente"
        )
        self.assertEqual(
            infer_interlocutor_label(
                AuditAlert(id="A2", label="Posição em Atraso - Ponto de Apoio", context="Contato com Ponto de Apoio", criteria=[])
            ),
            "Ponto de Apoio"
        )

    def test_validate_transcription(self):
        """Test transcription JSON validation"""
        valid_data = [{"start": "00:00", "end": "00:01", "text": "hello"}]
        self.assertTrue(validate_transcription(valid_data))
        
        invalid_data_1 = {"wrong": "structure"}
        self.assertFalse(validate_transcription(invalid_data_1))
        
        # Missing keys
        invalid_data_2 = [{"start": "00:00", "text": "hello"}] # Missing 'end'
        self.assertFalse(validate_transcription(invalid_data_2))

    def test_result_from_raw_score_calculation(self):
        """Test score calculation logic"""
        raw_evaluation = {
            "summary": "Test Summary",
            "details": [
                {"criterionId": "CR01", "status": "pass", "comment": "ok"},    # 10.0 (100%) -> 10.0
                {"criterionId": "CR02", "status": "partial", "comment": "meh"}, # legado: partial -> fail
                {"criterionId": "CR03", "status": "fail", "comment": "bad"}     # 5.0 (0%) -> 0.0
            ]
        }
        
        # Note: result_from_raw iterates over raw['details'] and matches with criteria_list
        # If item in details matches criterion, it adds to score.
        
        result = result_from_raw(
            raw=raw_evaluation,
            criteria_list=self.criteria,
            transcription_data=[],
            operator_name="TestOp"
        )
        
        expected_score = 10.0 + 0.0 + 0.0 # 10.0
        expected_max = 10.0 + 20.0 + 5.0   # 35.0

        self.assertEqual(result.score, expected_score)
        self.assertEqual(result.maxPossibleScore, expected_max)

    def test_result_from_raw_na_handling(self):
        """Legacy 'na' is normalized to pass; missing criteria are backfilled as fail."""
        raw_evaluation = {
            "summary": "Test NA",
            "details": [
                {"criterionId": "CR01", "status": "pass", "comment": "ok"}, # 10.0
                {"criterionId": "CR02", "status": "na", "comment": "legacy benevolence"}
            ]
        }
        
        result = result_from_raw(
            raw=raw_evaluation,
            criteria_list=self.criteria
        )
        
        expected_max = 35.0 # All criteria count
        expected_score = 30.0 # CR01 pass(10), CR02 na->pass(20), CR03 missing->fail(0)
        
        self.assertEqual(result.maxPossibleScore, expected_max)
        self.assertEqual(result.score, expected_score)
        self.assertEqual(len(result.details), 3)
        self.assertEqual(result.details[1].status, "pass")
        self.assertEqual(result.details[2].criterionId, "CR03")
        self.assertEqual(result.details[2].status, "fail")
        self.assertIn("Critério ausente", result.details[2].comment)

    def test_result_from_raw_consolidates_duplicates_using_stricter_status(self):
        raw_evaluation = {
            "summary": "Test duplicate criteria",
            "details": [
                {"criterionId": "CR01", "status": "pass", "comment": "primeira leitura"},
                {"criterionId": "CR01", "status": "fail", "comment": "falha identificada depois"},
                {"criterionId": "CR02", "status": "partial", "comment": "parcial"},
                {"criterionId": "CR03", "status": "pass", "comment": "ok"},
            ]
        }

        result = result_from_raw(
            raw=raw_evaluation,
            criteria_list=self.criteria
        )

        self.assertEqual(len(result.details), 3)
        self.assertEqual(result.details[0].criterionId, "CR01")
        self.assertEqual(result.details[0].status, "fail")
        self.assertEqual(result.details[0].comment, "falha identificada depois")
        self.assertEqual(result.score, 5.0)
        self.assertEqual(result.maxPossibleScore, 35.0)

    def test_result_from_raw_preserves_timestamp_and_evidence_metadata(self):
        raw_evaluation = {
            "summary": "Test evidence",
            "details": [
                {
                    "criterionId": "CR01",
                    "status": "pass",
                    "comment": "ok",
                    "timestamp": "00:00:01 - 00:00:04",
                    "evidence_text": "Operador: bom dia.",
                    "evidence_validation": {"status": "matched", "matched": True, "method": "literal"},
                }
            ],
        }

        result = result_from_raw(
            raw=raw_evaluation,
            criteria_list=self.criteria
        )

        detail = result.details[0]
        self.assertEqual(detail.timestamp, "00:00:01 - 00:00:04")
        self.assertEqual(detail.evidence_text, "Operador: bom dia.")
        self.assertEqual(detail.evidence_validation["method"], "literal")

    def test_result_from_raw_ignores_unknown_criteria_and_preserves_original_checklist(self):
        raw_evaluation = {
            "summary": "Test unknown criteria",
            "details": [
                {"criterionId": "FAKE", "status": "pass", "comment": "inventado"},
                {"criterionId": "CR01", "status": "pass", "comment": "ok"},
            ]
        }

        result = result_from_raw(
            raw=raw_evaluation,
            criteria_list=self.criteria
        )

        self.assertEqual([detail.criterionId for detail in result.details], ["CR01", "CR02", "CR03"])
        self.assertEqual([detail.status for detail in result.details], ["pass", "fail", "fail"])
        self.assertEqual(result.score, 10.0)
        self.assertEqual(result.maxPossibleScore, 35.0)

    def test_result_from_raw_zero_summary_uses_specific_reason(self):
        """When a call is zeroed, the summary should cite the concrete reason."""
        criteria = [
            AuditCriterion(id="senha", label="Senha", weight=10.0, description=""),
        ]
        raw_evaluation = {
            "summary": "Operador conduziu a chamada.",
            "details": [
                {"criterionId": "senha", "status": "fail", "comment": "Aceitou senha incorreta."}
            ]
        }

        result = result_from_raw(
            raw=raw_evaluation,
            criteria_list=criteria,
            sector_id="rastreamento"
        )

        self.assertEqual(result.score, 0.0)
        self.assertIn("Nota zerada porque", result.summary)
        self.assertIn("critério de senha", result.summary.lower())
        self.assertNotIn("violação não negociável", result.summary.lower())

    def test_result_from_raw_zeroing_uses_criterion_chave(self):
        criteria = [
            AuditCriterion(
                id="crit_123",
                chave="confirmou_senha",
                label="Confirmou validacao de seguranca?",
                weight=10.0,
                description="",
            ),
        ]
        raw_evaluation = {
            "summary": "Operador nao validou a senha.",
            "details": [
                {"criterionId": "crit_123", "status": "fail", "comment": "Nao houve validacao."}
            ],
        }

        result = result_from_raw(
            raw=raw_evaluation,
            criteria_list=criteria,
            sector_id="bas"
        )

        self.assertEqual(result.score, 0.0)
        self.assertIn("senha", result.summary.lower())

if __name__ == '__main__':
    unittest.main()
