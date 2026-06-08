from __future__ import annotations
"""
Text Processing Module

Normalization, hallucination filtering, deduplication, and speaker prefix
handling for transcription segments.
"""


import json
import logging
import re
from pathlib import Path
from typing import Any

from audio.diarization_quality import (
    clone_transcription_segment,
    extract_segment_speaker,
    normalize_lookup_text,
)

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _load_text_corrections() -> dict:
    path = _CONFIG_DIR / "text_corrections.json"
    if path.exists():
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {}


TEXT_CORRECTIONS_CONFIG = _load_text_corrections()

# ── Pre-compiled regex (executa 1x no boot, evita N+1 compilations) ──────────

_COMPILED_BLACKLIST = [
    re.compile(rf"\b{re.escape(str(term).strip())}\b", flags=re.IGNORECASE)
    for term in TEXT_CORRECTIONS_CONFIG.get("hallucination_blacklist_terms", [])
    if str(term).strip()
]

_COMPILED_REPLACEMENTS = [
    (re.compile(rf"\b{re.escape(str(k).strip())}\b", flags=re.IGNORECASE), str(v).strip())
    for k, v in TEXT_CORRECTIONS_CONFIG.get("hallucination_phrase_replacements", {}).items()
    if str(k).strip()
]

# ── Emoji removal ────────────────────────────────────────────────────────────

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]+",
    flags=re.UNICODE,
)


def remove_emojis(text: str) -> str:
    if not text:
        return ""
    cleaned = EMOJI_PATTERN.sub("", text)
    cleaned = cleaned.replace("\uFE0F", "").replace("\u200D", "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


# ── Hallucination filtering ──────────────────────────────────────────────────


def filter_hallucinations(text: str) -> str:
    """Remove padroes comuns de alucinacao da transcricao (inspirado no Sentinel)."""
    if not text:
        return text
    # Remove loops de palavras repetidas 3+ vezes (ex: "alo alo alo" -> "alo")
    # Separadores explícitos evitam Catastrophic Backtracking (ReDoS)
    try:
        text = re.sub(r"\b(\w+)(?:[\s.,!?;\-]+\1\b){2,}", r"\1", text, flags=re.IGNORECASE)
    except Exception:
        logger.exception("Falha ao aplicar filtro de repeticao em filter_hallucinations")
    # Remove system prompt leaks
    text = re.sub(r"\[The following.*?\]", "", text)
    # Remove marcadores de fim/silencio
    text = text.replace("FIM_DO_AUDIO", "").replace("[SILENCIO]", "")
    # Remove chamadas automaticas de URA/telefonia que nao fazem parte da conversa auditavel
    text = re.sub(r"^\s*aten[cç][aã]o!?[\s\-]*liga[cç][aã]o receptiva\.?\s*$", "", text, flags=re.IGNORECASE)
    # Remove termos sabidamente alucinados pelo ASR (pre-compilados no boot)
    for pattern in _COMPILED_BLACKLIST:
        text = pattern.sub("", text)
    # Aplica substituições de frases (pre-compiladas no boot)
    for pattern, replacement in _COMPILED_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


# ── Text normalization ────────────────────────────────────────────────────────


def normalize_text_for_dedupe(text: str) -> str:
    cleaned = remove_emojis(text).lower()
    cleaned = re.sub(r"[^\w\s:]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_company_name(text: str) -> str:
    """Corrige erros foneticos de transcricao usando config/text_corrections.json."""
    corrections = TEXT_CORRECTIONS_CONFIG.get("corrections", [])
    for correction in corrections:
        target = correction.get("target", "")
        for pattern in correction.get("patterns", []):
            text = re.sub(pattern, target, text, flags=re.IGNORECASE)
    return text


# ── Deduplication ─────────────────────────────────────────────────────────────


def deduplicate_transcription_segments(segments: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    previous_normalized = ""
    previous_start = ""
    previous_end = ""
    previous_speaker = ""

    for segment in segments:
        if not isinstance(segment, dict):
            continue

        start = str(segment.get("start", "00:00")).strip() or "00:00"
        end = str(segment.get("end", "00:00")).strip() or "00:00"
        text = remove_emojis(str(segment.get("text", "")).strip())
        if not text:
            continue

        normalized = normalize_text_for_dedupe(text)
        if not normalized:
            continue
        current_speaker = extract_segment_speaker(text)

        if deduped:
            repeated_phrase = normalized == previous_normalized and len(normalized.split()) >= 4
            same_window = start == previous_start and end == previous_end

            if same_window:
                if current_speaker and previous_speaker and current_speaker != previous_speaker:
                    deduped.append(clone_transcription_segment(segment, start=start, end=end, text=text))
                    previous_normalized = normalized
                    previous_start = start
                    previous_end = end
                    previous_speaker = current_speaker
                    continue
                if len(normalized) > len(previous_normalized):
                    deduped[-1] = clone_transcription_segment(segment, start=start, end=end, text=text)
                    previous_normalized = normalized
                    previous_speaker = current_speaker
                continue

            if repeated_phrase and (not current_speaker or not previous_speaker or current_speaker == previous_speaker):
                continue

            if (
                start == previous_start
                and normalized.startswith(previous_normalized)
                and len(previous_normalized) >= 12
                and (not current_speaker or not previous_speaker or current_speaker == previous_speaker)
            ):
                deduped[-1] = clone_transcription_segment(segment, start=start, end=end, text=text)
                previous_normalized = normalized
                previous_end = end
                previous_speaker = current_speaker
                continue

            if (
                start == previous_start
                and previous_normalized.startswith(normalized)
                and len(normalized) >= 12
                and (not current_speaker or not previous_speaker or current_speaker == previous_speaker)
            ):
                continue

        deduped.append(clone_transcription_segment(segment, start=start, end=end, text=text))
        previous_normalized = normalized
        previous_start = start
        previous_end = end
        previous_speaker = current_speaker

    return deduped


# ── Speaker prefix normalization ──────────────────────────────────────────────


def normalize_speaker_prefix(text: str, operator_label: str, driver_label: str) -> str:
    """Normaliza prefixos de falantes usando config/text_corrections.json."""
    speaker_config = TEXT_CORRECTIONS_CONFIG.get("speaker_prefixes", {})
    prefixes: dict[str, str] = {}
    for p in speaker_config.get("operator", ["operador", "atendente", "central", "bas"]):
        prefixes[normalize_lookup_text(str(p))] = operator_label
    for p in speaker_config.get("driver", ["cliente", "motorista", "vitima", "declarante", "condutor"]):
        prefixes[normalize_lookup_text(str(p))] = driver_label
    for p in speaker_config.get("telephony", ["telefonia", "ura", "ivr", "robo", "automatico"]):
        prefixes[normalize_lookup_text(str(p))] = "Telefonia"

    speaker_candidate, separator, remainder = text.partition(":")
    normalized_candidate = normalize_lookup_text(speaker_candidate)

    # Ordenar por tamanho desc para match mais especifico primeiro ("operador bas" antes de "operador")
    if separator:
        for prefix in sorted(prefixes, key=len, reverse=True):
            if normalized_candidate == prefix:
                return f"{prefixes[prefix]}:{remainder}"

    # Deteccao automatica de URA por conteudo se nao houver prefixo
    ura_keywords = TEXT_CORRECTIONS_CONFIG.get("ura_keywords", ["digite", "opcao", "bem-vindo", "aguarde na linha"])
    normalized_text = normalize_lookup_text(text)
    normalized_keywords = [normalize_lookup_text(str(keyword)) for keyword in ura_keywords]
    if any(keyword and keyword in normalized_text for keyword in normalized_keywords) and ":" not in text:
        return f"Telefonia: {text}"

    return text


def format_pt_br_name(name: str) -> str:
    """Formata nomes para Title Case, mantendo preposicoes do pt-br em minusculo."""
    if not name:
        return name
    
    prepositions = {"da", "de", "do", "das", "dos", "e"}
    words = str(name).lower().split()
    formatted_words = []
    
    for i, word in enumerate(words):
        if word in prepositions and i > 0 and i < len(words) - 1:
            formatted_words.append(word)
        else:
            formatted_words.append(word.capitalize())
            
    return " ".join(formatted_words)
