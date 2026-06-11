from __future__ import annotations
from datetime import timedelta
import time
import re
from threading import Semaphore

import logging
from dataclasses import dataclass
import json
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

from utils.http_session import create_requests_session
from audio.speaker_detection import RawPhrase, SpeakerDetectionService

from transcription_providers.common import (
    build_azure_domain_phrases,
    build_combined_segments,
    finalize_speaker_segments,
    normalize_transcribed_text,
)


def _read_int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(str(os.getenv(name, str(default))).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _get_max_sync_upload_bytes() -> int:
    return _read_int_env("AZURE_SPEECH_MAX_SYNC_UPLOAD_BYTES", 25 * 1024 * 1024, 1)


def _get_whisper_max_concurrency() -> int:
    return _read_int_env("WHISPER_MAX_CONCURRENCY", 4, 1)


@dataclass(frozen=True)
class AzureTranscriptionDependencies:
    text_corrections_config: dict
    guess_audio_filename: Callable[[str], str]
    get_transcription_timeout_seconds: Callable[[], int]
    get_whisper_temperature: Callable[[], float]
    get_whisper_prompt: Callable[[Optional[str]], str]
    normalize_company_name: Callable[[str], str]
    filter_hallucinations: Callable[[str], str]
    remove_emojis: Callable[[str], str]
    parse_iso_duration: Callable[[Any], float]
    parse_float: Callable[[Any], Optional[float]]
    should_discard_whisper_segment: Callable[[str, float, float, float, float, float], bool]
    should_replace_whisper_segment_with_inaudivel: Callable[[str, float, float, float, float], bool]
    extract_phrase_text: Callable[[dict], str]
    extract_phrase_timing_ms: Callable[[dict], tuple[float, float]]
    normalize_speaker_id: Callable[[Any], int]
    deduplicate_transcription_segments: Callable[[list[dict]], list[dict]]


def transcribe_audio_azure(
    audio_file: bytes,
    operator_label: str,
    driver_label: str,
    operator_name: Optional[str] = None,
    driver_name: Optional[str] = None,
    mime_type: str = "audio/wav",
    endpoint_override: Optional[str] = None,
    api_key_override: Optional[str] = None,
    *,
    sector_id: Optional[str] = None,
    dependencies: AzureTranscriptionDependencies,
) -> list[dict]:
    api_key = (api_key_override or os.getenv("AZURE_SPEECH_KEY") or "").strip()
    endpoint = (endpoint_override or os.getenv("AZURE_SPEECH_ENDPOINT") or "").strip()
    if not api_key or not endpoint:
        raise RuntimeError("Azure Speech not configured")

    if not audio_file or len(audio_file) < 100:
        raise ValueError("Audio invalido ou muito pequeno")

    incoming_mime = (mime_type or "audio/wav").strip().lower() or "audio/wav"
    if incoming_mime not in {"audio/wav", "audio/x-wav", "audio/wave"}:
        try:
            from audio.audio_utils import convert_audio_to_wav
            audio_file = convert_audio_to_wav(audio_file)
            mime_type = "audio/wav"
            logger.info("Audio normalizado para WAV (origem=%s).", incoming_mime)
        except Exception as e:
            logger.warning("Falha na normalizacao para WAV, seguindo com original (%s): %s", incoming_mime, e)


    safe_mime = (mime_type or "audio/wav").strip().lower() or "audio/wav"
    upload_name = dependencies.guess_audio_filename(safe_mime)
    request_timeout_seconds = dependencies.get_transcription_timeout_seconds()

    if "openai/deployments" in endpoint:
        url = endpoint.replace("/translations?", "/transcriptions?")
        if "?api-version=" not in url:
            url += "?api-version=2024-06-01"

        headers = {"api-key": api_key, "Accept": "application/json"}
        files = {"file": (upload_name, audio_file, safe_mime)}
        fallback_prompt = dependencies.text_corrections_config.get(
            "whisper_prompt",
            "Opentech, nstech, BAS, motorista, placa, Mondelez, Unilever, Buonny, Sascar, Tracker, Onix, Autotrac, Omnilink, Ravex, isca, [Inaudível].",
        )
        data = {
            "response_format": "verbose_json",
            "language": "pt",
            "prompt": dependencies.get_whisper_prompt(sector_id) or fallback_prompt,
            "temperature": f"{dependencies.get_whisper_temperature():.2f}",
        }
        try:
            result = None
            with _whisper_semaphore:
                for attempt in range(4): # Ate 4 tentativas
                    from core import cost_guard
                    cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "transcricao_whisper")
                    with create_requests_session() as session:
                        response = session.post(
                            url,
                            headers=headers,
                            files=files,
                            data=data,
                            timeout=request_timeout_seconds,
                        )
                    
                    if response.status_code == 429:
                        retry_after = 10
                        try:
                            msg = response.json().get("error", {}).get("message", "")
                            match = re.search(r"retry after (\d+) seconds", msg, re.I)
                            if match:
                                retry_after = int(match.group(1)) + 1
                        except: pass
                        logger.warning("Whisper 429 (Rate Limit): Aguardando %ds para tentativa %d...", retry_after, attempt+1)
                        time.sleep(retry_after)
                        continue
                    
                    if not response.ok:
                        response.raise_for_status()
                    
                    result = response.json()
                    break
            
            if result is None:
                raise RuntimeError("Falha apos multiplas tentativas (Rate Limit)")

            logger.debug("Raw Azure OpenAI JSON parsed successfully (%d bytes).", len(response.content))


            raw_phrases: list[RawPhrase] = []
            for segment in result.get("segments", []):
                if not isinstance(segment, dict):
                    continue

                text = normalize_transcribed_text(
                    str(segment.get("text", "")).strip(),
                    normalize_company_name=dependencies.normalize_company_name,
                    filter_hallucinations=dependencies.filter_hallucinations,
                    remove_emojis=dependencies.remove_emojis,
                )
                if not text:
                    continue

                start_sec = max(0.0, dependencies.parse_iso_duration(segment.get("start", 0)))
                end_sec = max(start_sec, dependencies.parse_iso_duration(segment.get("end", start_sec)))
                duration_sec = max(0.0, end_sec - start_sec)

                no_speech_prob = dependencies.parse_float(segment.get("no_speech_prob")) or 0.0
                avg_logprob = dependencies.parse_float(segment.get("avg_logprob")) or 0.0
                compression_ratio = dependencies.parse_float(segment.get("compression_ratio")) or 0.0
                normalized_text = SpeakerDetectionService.normalizar_texto(text)

                if dependencies.should_discard_whisper_segment(
                    normalized_text,
                    no_speech_prob,
                    avg_logprob,
                    compression_ratio,
                    duration_sec,
                    start_sec,
                ):
                    continue

                if dependencies.should_replace_whisper_segment_with_inaudivel(
                    normalized_text,
                    no_speech_prob,
                    avg_logprob,
                    compression_ratio,
                    duration_sec,
                ):
                    text = "*inaudivel*"
                    normalized_text = SpeakerDetectionService.normalizar_texto(text)

                raw_phrases.append(
                    RawPhrase(
                        timestamp=timedelta(seconds=start_sec),
                        duration_seconds=duration_sec,
                        speaker_id=-1,
                        texto=text,
                        texto_normalizado=normalized_text,
                    )
                )

            if not raw_phrases:
                text_fallback = normalize_transcribed_text(
                    str(result.get("text", "")).strip(),
                    normalize_company_name=dependencies.normalize_company_name,
                    filter_hallucinations=dependencies.filter_hallucinations,
                    remove_emojis=dependencies.remove_emojis,
                )
                if not text_fallback:
                    raise RuntimeError("Azure OpenAI Whisper returned empty transcription")
                raw_phrases.append(
                    RawPhrase(
                        timestamp=timedelta(seconds=0),
                        duration_seconds=0.0,
                        speaker_id=-1,
                        texto=text_fallback,
                        texto_normalizado=SpeakerDetectionService.normalizar_texto(text_fallback),
                    )
                )

            final_segments = finalize_speaker_segments(
                raw_phrases,
                operator_label=operator_label,
                driver_label=driver_label,
                deduplicate_transcription_segments=dependencies.deduplicate_transcription_segments,
            )
            if not final_segments:
                raise RuntimeError("Azure OpenAI Whisper returned no valid segments after filtering")

            return final_segments
        except Exception as exc:
            err_msg = response.text if "response" in locals() and hasattr(response, "text") else ""
            logger.warning(
                "Azure OpenAI Whisper falhou (%s); orchestrator tentara proxima estrategia. Body: %s",
                exc, err_msg,
            )
            raise RuntimeError(f"Azure OpenAI Whisper Transcription failed: {exc}. Body: {err_msg}")

    # Etapa 4: Fallback Azure Speech Fast com validacao robusta
    base_url = endpoint.rstrip("/")
    if not base_url.endswith("transcriptions:transcribe"):
        base_url = base_url + "/speechtotext/transcriptions:transcribe"
    api_version = os.getenv("AZURE_SPEECH_API_VERSION", "2025-10-15").strip() or "2025-10-15"
    url = base_url + f"?api-version={api_version}"
    headers = {"Ocp-Apim-Subscription-Key": api_key, "Accept": "application/json"}
    try:
        max_speakers = int(os.getenv("AZURE_SPEECH_MAX_SPEAKERS", "2"))
    except Exception:
        max_speakers = 2
    max_speakers = max(1, min(max_speakers, 10))

    definition = {
        "locales": ["pt-BR"],
        "profanityFilterMode": "None",
        "diarization": {"enabled": True, "maxSpeakers": max_speakers},
        "wordLevelTimestampsEnabled": True,
    }
    domain_phrases = build_azure_domain_phrases(
        dependencies.text_corrections_config,
        operator_name,
        driver_name,
    )
    if domain_phrases:
        definition["phraseList"] = {"phrases": domain_phrases}

    max_sync_upload_bytes = _get_max_sync_upload_bytes()
    if len(audio_file) > max_sync_upload_bytes:
        raise RuntimeError(
            "Azure Speech Fast synchronous upload exceeds configured limit "
            f"({len(audio_file)} bytes > {max_sync_upload_bytes} bytes). "
            "Use an async batch transcription path or lower the input size."
        )

    multipart_files = {
        "audio": (upload_name, audio_file, safe_mime),
        "definition": (None, json.dumps(definition), "application/json"),
    }
    try:
        from core import cost_guard
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_SPEECH, "transcricao_fast")
        with create_requests_session() as session:
            response = session.post(
                url,
                headers=headers,
                files=multipart_files,
                timeout=request_timeout_seconds,
            )
        if not response.ok:
            error_msg = response.text
            response.raise_for_status()
        result = response.json()

        logger.debug("Raw Azure Fast Transcription JSON parsed successfully (%d bytes).", len(response.content))

        phrases_source = result.get("phrases", [])
        if not phrases_source and "combinedPhrases" in result:
            combined_segments = build_combined_segments(
                result["combinedPhrases"],
                extract_phrase_text=dependencies.extract_phrase_text,
                extract_phrase_timing_ms=dependencies.extract_phrase_timing_ms,
                normalize_company_name=dependencies.normalize_company_name,
                filter_hallucinations=dependencies.filter_hallucinations,
                remove_emojis=dependencies.remove_emojis,
                deduplicate_transcription_segments=dependencies.deduplicate_transcription_segments,
            )
            if combined_segments:
                return combined_segments
            raise RuntimeError("Azure Speech returned no diarized phrases or combined phrases")

        raw_phrases: list[RawPhrase] = []
        for phrase in phrases_source:
            text = dependencies.extract_phrase_text(phrase)
            if not text:
                continue

            text = normalize_transcribed_text(
                text,
                normalize_company_name=dependencies.normalize_company_name,
                filter_hallucinations=dependencies.filter_hallucinations,
                remove_emojis=dependencies.remove_emojis,
            )
            if not text:
                continue

            offset_ms, duration_ms = dependencies.extract_phrase_timing_ms(phrase)
            speaker_id = dependencies.normalize_speaker_id(phrase.get("speaker", phrase.get("speakerId", -1)))
            raw_phrases.append(
                RawPhrase(
                    timestamp=timedelta(milliseconds=offset_ms),
                    duration_seconds=max(0.0, duration_ms / 1000.0),
                    speaker_id=speaker_id,
                    texto=text,
                    texto_normalizado=SpeakerDetectionService.normalizar_texto(text),
                )
            )

        if not raw_phrases:
            raise RuntimeError("Azure Speech returned empty phrases")

        return finalize_speaker_segments(
            raw_phrases,
            operator_label=operator_label,
            driver_label=driver_label,
            deduplicate_transcription_segments=dependencies.deduplicate_transcription_segments,
        )
    except Exception as exc:
        logger.warning(
            "Azure Fast Transcription falhou (%s); orchestrator tentara proxima estrategia.",
            exc,
        )
        raise RuntimeError(f"Azure Transcription failed: {exc}")


# Semaforo para respeitar o limite de cota do Azure Whisper (S0 tier)
_whisper_semaphore = Semaphore(_get_whisper_max_concurrency())
