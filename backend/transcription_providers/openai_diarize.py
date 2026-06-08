from __future__ import annotations
import logging

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

from utils.http_session import create_requests_session
from audio.speaker_detection import RawPhrase, SpeakerDetectionService

from transcription_providers.common import finalize_speaker_segments, normalize_transcribed_text


@dataclass(frozen=True)
class GPT4oDiarizeTranscriptionDependencies:
    guess_audio_filename: Callable[[str], str]
    get_transcription_timeout_seconds: Callable[[], int]
    get_retry_count: Callable[[], int]
    get_retry_delay_seconds: Callable[[], float]
    build_domain_prompt: Callable[[Optional[str], Optional[str]], str]
    normalize_company_name: Callable[[str], str]
    filter_hallucinations: Callable[[str], str]
    remove_emojis: Callable[[str], str]
    deduplicate_transcription_segments: Callable[[list[dict]], list[dict]]
    sleep: Callable[[float], None]


def _parse_seconds(value: object) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _is_retryable_exception(exc: Exception) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", 0) or 0
        return status_code >= 500
    return False


def _response_rejected_prompt_parameter(response: requests.Response) -> bool:
    status_code = getattr(response, "status_code", 0) or 0
    if status_code != 400:
        return False
    body = str(getattr(response, "text", "") or "").lower()
    if "prompt" not in body:
        return False
    return any(marker in body for marker in ("unknown", "unrecognized", "unsupported", "invalid", "not allowed"))


def transcribe_audio_gpt4o_diarize(
    audio_file: bytes,
    mime_type: str,
    operator_label: str,
    driver_label: str,
    *,
    endpoint: str,
    api_key: str,
    auth_mode: str = "api_key",
    model_name: Optional[str] = None,
    operator_name: Optional[str] = None,
    driver_name: Optional[str] = None,
    dependencies: GPT4oDiarizeTranscriptionDependencies,
) -> list[dict]:
    safe_endpoint = str(endpoint or "").strip()
    safe_api_key = str(api_key or "").strip()
    if not safe_endpoint or not safe_api_key:
        raise RuntimeError("GPT-4o-transcribe-diarize not configured")

    incoming_mime = (mime_type or "audio/wav").strip().lower() or "audio/wav"
    if incoming_mime not in {"audio/wav", "audio/x-wav", "audio/wave"}:
        try:
            from audio.audio_utils import convert_audio_to_wav
            audio_file = convert_audio_to_wav(audio_file)
            mime_type = "audio/wav"
            logger.info("Audio normalizado para WAV (origem=%s) p/ GPT-4o Diarize.", incoming_mime)
        except Exception as e:
            logger.warning("Normalizacao de audio falhou, tentando arquivo original (%s): %s", incoming_mime, e)


    safe_mime = (mime_type or "audio/wav").strip().lower() or "audio/wav"
    upload_name = dependencies.guess_audio_filename(safe_mime)
    timeout_seconds = dependencies.get_transcription_timeout_seconds()
    retry_count = max(0, int(dependencies.get_retry_count() or 0))
    retry_delay_seconds = max(0.0, float(dependencies.get_retry_delay_seconds() or 0.0))

    normalized_auth_mode = (auth_mode or "api_key").strip().lower()
    if normalized_auth_mode == "bearer":
        headers = {"Authorization": f"Bearer {safe_api_key}", "Accept": "application/json"}
    else:
        headers = {"api-key": safe_api_key, "Accept": "application/json"}
    files = {"file": (upload_name, audio_file, safe_mime)}
    domain_prompt = (dependencies.build_domain_prompt(operator_name, driver_name) or "").strip()
    base_data = {
        "response_format": "diarized_json",
        "language": "pt",
        "chunking_strategy": "auto",
    }
    if model_name:
        base_data["model"] = str(model_name).strip()
    if domain_prompt:
        base_data["prompt"] = domain_prompt

    last_exc: Optional[Exception] = None
    last_response_text = ""
    for attempt in range(retry_count + 1):
        response = None
        try:
            with create_requests_session() as session:
                response = session.post(
                    safe_endpoint,
                    headers=headers,
                    files=files,
                    data=base_data,
                    timeout=timeout_seconds,
                )
                if not response.ok and "prompt" in base_data and _response_rejected_prompt_parameter(response):
                    logger.warning("GPT-4o diarize rejeitou parametro prompt; repetindo chamada sem prompt.")
                    data_without_prompt = dict(base_data)
                    data_without_prompt.pop("prompt", None)
                    response = session.post(
                        safe_endpoint,
                        headers=headers,
                        files=files,
                        data=data_without_prompt,
                        timeout=timeout_seconds,
                    )
            if not response.ok:
                response.raise_for_status()
            payload = response.json()

            raw_phrases: list[RawPhrase] = []
            speaker_map: dict[str, int] = {}
            for segment in payload.get("segments", []):
                if not isinstance(segment, dict):
                    continue

                text = normalize_transcribed_text(
                    str(segment.get("text") or "").strip(),
                    normalize_company_name=dependencies.normalize_company_name,
                    filter_hallucinations=dependencies.filter_hallucinations,
                    remove_emojis=dependencies.remove_emojis,
                )
                if not text:
                    continue

                speaker_token = str(
                    segment.get("speaker")
                    or segment.get("speaker_name")
                    or segment.get("speaker_label")
                    or ""
                ).strip()
                if speaker_token and speaker_token not in speaker_map:
                    speaker_map[speaker_token] = len(speaker_map)

                start_seconds = _parse_seconds(segment.get("start"))
                end_seconds = max(start_seconds, _parse_seconds(segment.get("end")))
                raw_phrases.append(
                    RawPhrase(
                        timestamp=timedelta(seconds=start_seconds),
                        duration_seconds=max(0.0, end_seconds - start_seconds),
                        speaker_id=speaker_map.get(speaker_token, -1),
                        texto=text,
                        texto_normalizado=SpeakerDetectionService.normalizar_texto(text),
                    )
                )

            if not raw_phrases:
                fallback_text = normalize_transcribed_text(
                    str(payload.get("text") or "").strip(),
                    normalize_company_name=dependencies.normalize_company_name,
                    filter_hallucinations=dependencies.filter_hallucinations,
                    remove_emojis=dependencies.remove_emojis,
                )
                if not fallback_text:
                    raise RuntimeError("GPT-4o-transcribe-diarize returned empty transcription")
                raw_phrases.append(
                    RawPhrase(
                        timestamp=timedelta(seconds=0),
                        duration_seconds=0.0,
                        speaker_id=-1,
                        texto=fallback_text,
                        texto_normalizado=SpeakerDetectionService.normalizar_texto(fallback_text),
                    )
                )

            final_segments = finalize_speaker_segments(
                raw_phrases,
                operator_label=operator_label,
                driver_label=driver_label,
                deduplicate_transcription_segments=dependencies.deduplicate_transcription_segments,
            )
            if not final_segments:
                raise RuntimeError("GPT-4o-transcribe-diarize returned no valid segments")

            return final_segments
        except Exception as exc:
            last_response_text = response.text if response is not None and hasattr(response, "text") else ""
            last_exc = exc
            if attempt < retry_count and _is_retryable_exception(exc):
                wait_seconds = retry_delay_seconds * (attempt + 1)
                if wait_seconds > 0:
                    dependencies.sleep(wait_seconds)
                continue
            break

    raise RuntimeError(f"GPT-4o-transcribe-diarize failed: {last_exc}. Body: {last_response_text}")
