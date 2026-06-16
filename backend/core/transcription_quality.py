"""Avaliacao deterministica da QUALIDADE de uma transcricao para fins de auditoria.

Papel no fluxo: depois de transcrever um audio, este modulo calcula um sinal de
"prontidao para auditar" (audit_readiness) a partir dos segmentos e dos metadados
do provedor/diarizacao. Esse sinal alimenta a camada de disposicao da automacao,
que decide entre auditar automaticamente, mandar para revisao humana ou descartar.

Distincao central usada pela automacao:
- 'blocked'   -> IMPOSSIVEL de auditar (vazia, conteudo insuficiente, selector
                 rejeitado). Pode justificar descarte permanente SO se vazia.
- 'review_required' -> existe mas imperfeita; deve seguir e ser auditada.
- 'ready'     -> forte o bastante para auditoria automatica.

NAO julga se o operador passou na auditoria; so mede a transcricao em si.

CUSTO DE API: nenhum. So processa estruturas em memoria (CPU); nao chama
Azure/rede nem banco.
"""
from __future__ import annotations

from collections import Counter
import re
from typing import Any, Optional

from audio.diarization_quality import (
    extract_segment_body,
    extract_segment_speaker,
    normalize_lookup_text,
    parse_float_value,
    parse_timestamp_seconds,
)


_PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2}
DEGRADED_FALLBACK_REASON = "fallback_de_transcricao_sem_consenso"


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or "", flags=re.UNICODE))


def _max_priority(first: str, second: str) -> str:
    return first if _PRIORITY_RANK.get(first, 0) >= _PRIORITY_RANK.get(second, 0) else second


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value and value not in target:
            target.append(value)


def _provider_has_degraded_consensus_gap(provider_meta: dict[str, Any]) -> bool:
    """True quando o pipeline pretendia usar hybrid_dual mas caiu em fallback.

    Detecta o "gap de consenso degradado": a estrategia hybrid_dual (que combina
    dois provedores) foi tentada mas teve de ser substituida por outra
    (effective_strategy != hybrid_dual) ou registrou status insuficiente/erro nas
    tentativas. Esse caso e penalizado/sinalizado porque a transcricao foi feita
    sem o consenso esperado. Inspeciona `provider_meta["attempts"]`.
    """
    selected_strategy = str(provider_meta.get("selected_strategy") or "").strip().lower()
    if not selected_strategy or selected_strategy == "hybrid_dual":
        return False

    attempts = provider_meta.get("attempts") if isinstance(provider_meta.get("attempts"), list) else []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        strategy = str(attempt.get("strategy") or "").strip().lower()
        effective_strategy = str(attempt.get("effective_strategy") or strategy).strip().lower()
        status = str(attempt.get("status") or "").strip().lower()
        if strategy == "hybrid_dual" and effective_strategy and effective_strategy != "hybrid_dual":
            return True
        if (
            (strategy == "hybrid_dual" or effective_strategy == "hybrid_dual")
            and status in {"insufficient", "error"}
        ):
            return True
    return False


def get_transcription_review_reasons(audio_quality: Optional[dict[str, Any]]) -> list[str]:
    """Lista os motivos pelos quais a transcricao exige revisao humana.

    Le o bloco `transcription_quality` de `audio_quality`: quando o readiness e
    'blocked' ou 'review_required', devolve os `reasons` ja apurados (ou um motivo
    sintetico `transcricao_<readiness>`). Como fallback, sinaliza o gap de
    consenso degradado do provedor. Retorna [] quando nao ha motivo. Funcao pura.
    """
    if not isinstance(audio_quality, dict):
        return []

    transcription_quality = audio_quality.get("transcription_quality")
    if isinstance(transcription_quality, dict):
        readiness = str(transcription_quality.get("audit_readiness") or "").strip().lower()
        if readiness in {"blocked", "review_required"}:
            reasons = [
                str(reason).strip()
                for reason in (transcription_quality.get("reasons") or [])
                if str(reason).strip()
            ]
            return reasons or [f"transcricao_{readiness}"]

    provider_meta = (
        audio_quality.get("transcription_provider")
        if isinstance(audio_quality.get("transcription_provider"), dict)
        else {}
    )
    if _provider_has_degraded_consensus_gap(provider_meta):
        return [DEGRADED_FALLBACK_REASON]
    return []


def get_transcription_audit_readiness(audio_quality: Optional[dict[str, Any]]) -> Optional[str]:
    """Readiness deterministico da transcricao para a camada de disposicao da automacao:
    'blocked' (IMPOSSIVEL de auditar — vazia, conteudo insuficiente, selector rejeitado),
    'review_required' (existe mas imperfeita — deve seguir e ser auditada) ou 'ready'.
    Retorna None quando nao ha sinal. Separa transcricao IMPOSSIVEL (descartar) de
    IMPERFEITA (auditar)."""
    if not isinstance(audio_quality, dict):
        return None
    transcription_quality = audio_quality.get("transcription_quality")
    if isinstance(transcription_quality, dict):
        readiness = str(transcription_quality.get("audit_readiness") or "").strip().lower()
        if readiness:
            return readiness
    return None


def transcription_is_empty(audio_quality: Optional[dict[str, Any]]) -> bool:
    """True SOMENTE quando a transcricao e genuinamente impossivel de auditar: vazia
    (nenhum segmento / sem texto). Qualidade ruim mas COM conteudo (selector rejeitado,
    poucas falas humanas, conteudo curto) NAO conta como vazia — deve seguir para o
    auditor, nunca virar tombstone permanente. So este caso justifica descarte permanente."""
    if not isinstance(audio_quality, dict):
        return False
    transcription_quality = audio_quality.get("transcription_quality")
    if not isinstance(transcription_quality, dict):
        return False
    blocking = transcription_quality.get("blocking_reasons") or []
    if isinstance(blocking, list) and "transcricao_vazia" in blocking:
        return True
    metrics = transcription_quality.get("metrics")
    if isinstance(metrics, dict):
        if metrics.get("segment_count") == 0:
            return True
        total_chars = metrics.get("total_chars")
        total_words = metrics.get("total_words")
        if total_chars is not None and total_words is not None:
            try:
                if int(total_chars) == 0 and int(total_words) == 0:
                    return True
            except (TypeError, ValueError):
                pass
    return False


def assess_transcription_quality(
    transcription_segments: list[dict],
    audio_quality: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a deterministic readiness signal for audit use.

    This does not try to judge whether the operator passed the audit. It only
    answers whether the transcript is strong enough to support an automatic
    audit without hidden manual review.
    """

    segments = [segment for segment in (transcription_segments or []) if isinstance(segment, dict)]
    audio_quality = audio_quality if isinstance(audio_quality, dict) else {}
    diarization = audio_quality.get("diarization") if isinstance(audio_quality.get("diarization"), dict) else {}
    provider_meta = (
        audio_quality.get("transcription_provider")
        if isinstance(audio_quality.get("transcription_provider"), dict)
        else {}
    )

    speaker_counts: Counter[str] = Counter()
    normalized_bodies: list[str] = []
    starts: list[float] = []
    total_chars = 0
    total_words = 0
    timestamped_count = 0
    monotonic_errors = 0
    inaudible_segments = 0
    short_segments = 0
    human_segment_count = 0
    telephony_segment_count = 0

    previous_start: Optional[float] = None
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue

        speaker = extract_segment_speaker(text)
        normalized_speaker = normalize_lookup_text(speaker)
        body = extract_segment_body(text)
        normalized_body = normalize_lookup_text(body)
        words = _word_count(body)

        if normalized_body:
            normalized_bodies.append(normalized_body)
        total_chars += len(body)
        total_words += words

        if normalized_speaker == "telefonia":
            telephony_segment_count += 1
        else:
            human_segment_count += 1
            speaker_counts[normalized_speaker or "sem_rotulo"] += 1

        if "inaudivel" in normalized_body or "*inaudivel*" in normalized_body:
            inaudible_segments += 1
        if words <= 2:
            short_segments += 1

        raw_start = str(segment.get("start") or "").strip()
        if raw_start:
            timestamped_count += 1
            start_seconds = parse_timestamp_seconds(raw_start)
            starts.append(start_seconds)
            if previous_start is not None and start_seconds + 0.001 < previous_start:
                monotonic_errors += 1
            previous_start = start_seconds

    segment_count = len(segments)
    unique_bodies = len(set(normalized_bodies))
    repeated_ratio = 0.0
    if normalized_bodies:
        repeated_ratio = 1.0 - (unique_bodies / len(normalized_bodies))

    timestamp_coverage = (timestamped_count / segment_count) if segment_count else 0.0
    inaudible_ratio = (inaudible_segments / segment_count) if segment_count else 0.0
    short_segment_ratio = (short_segments / segment_count) if segment_count else 0.0
    human_speaker_count = len([speaker for speaker in speaker_counts if speaker != "telefonia"])

    reasons: list[str] = []
    blocking_reasons: list[str] = []
    score = 1.0

    if segment_count == 0:
        blocking_reasons.append("transcricao_vazia")
        score = 0.0
    elif total_words < 15 or total_chars < 80:
        blocking_reasons.append("conteudo_transcrito_insuficiente")
        score -= 0.45

    if segment_count and human_segment_count < 2:
        blocking_reasons.append("falas_humanas_insuficientes")
        score -= 0.25
    elif human_segment_count < 4:
        reasons.append("poucos_turnos_humanos")
        score -= 0.12

    if human_speaker_count < 2 and human_segment_count >= 2:
        reasons.append("apenas_um_falante_humano_rotulado")
        score -= 0.20

    if timestamp_coverage < 0.75:
        reasons.append("baixa_cobertura_de_timestamps")
        score -= 0.16
    if monotonic_errors > 0:
        reasons.append("timestamps_fora_de_ordem")
        score -= min(0.18, monotonic_errors * 0.06)
    if repeated_ratio >= 0.35:
        reasons.append("repeticao_excessiva_de_trechos")
        score -= 0.18
    if inaudible_ratio >= 0.30:
        reasons.append("muitos_trechos_inaudiveis")
        score -= 0.16
    if short_segment_ratio >= 0.65 and segment_count >= 8:
        reasons.append("segmentacao_fragmentada_em_excesso")
        score -= 0.10

    diarization_score = parse_float_value(diarization.get("score")) if diarization else None
    swap_risk = str(diarization.get("swap_risk") or "").strip().lower()
    if diarization_score is not None:
        if diarization_score < 0.42:
            reasons.append("score_de_diarizacao_muito_baixo")
            score -= 0.26
        elif diarization_score < 0.50:
            reasons.append("score_de_diarizacao_baixo")
            score -= 0.14
    if swap_risk == "high":
        reasons.append("risco_alto_de_troca_de_falante")
        score -= 0.22
    elif swap_risk == "medium":
        reasons.append("risco_medio_de_troca_de_falante")
        score -= 0.10

    selected_reason = str(provider_meta.get("selected_reason") or "").strip().lower()
    if selected_reason == "best_candidate":
        reasons.append("nenhum_provedor_passou_na_validacao_forte")
        score -= 0.12

    selector_status = str(provider_meta.get("selection_status") or "").strip().lower()
    selector_review_reasons = [
        str(reason).strip()
        for reason in (provider_meta.get("review_reasons") or [])
        if str(reason).strip()
    ]
    if selector_status in {"manual_review", "rejected"}:
        blocking_reasons.append(f"selector_{selector_status}")
        _append_unique(blocking_reasons, selector_review_reasons)
        score -= 0.45
    elif selector_status == "needs_review":
        reasons.append("selector_exigiu_revisao")
        _append_unique(reasons, selector_review_reasons)
        score -= 0.24

    attempts = provider_meta.get("attempts") if isinstance(provider_meta.get("attempts"), list) else []
    if any(isinstance(item, dict) and str(item.get("status") or "").lower() == "error" for item in attempts):
        reasons.append("falha_em_um_ou_mais_provedores")
        score -= 0.04
    if _provider_has_degraded_consensus_gap(provider_meta):
        reasons.append(DEGRADED_FALLBACK_REASON)
        score -= 0.28

    score = round(_clamp(score), 3)
    if blocking_reasons:
        readiness = "blocked"
    elif score >= 0.74 and not any(reason.startswith("risco_alto") for reason in reasons):
        readiness = "ready"
    else:
        readiness = "review_required"

    return {
        "score": score,
        "audit_readiness": readiness,
        "review_recommended": readiness != "ready",
        "reasons": blocking_reasons + reasons,
        "blocking_reasons": blocking_reasons,
        "metrics": {
            "segment_count": segment_count,
            "human_segment_count": human_segment_count,
            "telephony_segment_count": telephony_segment_count,
            "human_speaker_count": human_speaker_count,
            "speaker_counts": dict(speaker_counts),
            "total_chars": total_chars,
            "total_words": total_words,
            "timestamp_coverage": round(timestamp_coverage, 3),
            "monotonic_errors": monotonic_errors,
            "repeated_ratio": round(repeated_ratio, 3),
            "inaudible_ratio": round(inaudible_ratio, 3),
            "short_segment_ratio": round(short_segment_ratio, 3),
        },
    }


def attach_transcription_quality_gate(
    audio_quality: Optional[dict[str, Any]],
    transcription_segments: list[dict],
) -> dict[str, Any]:
    """Anexa o gate de qualidade de transcricao ao dict de qualidade de audio.

    Roda `assess_transcription_quality` sobre os segmentos e guarda o resultado em
    `transcription_quality`. Quando a transcricao recomenda revisao, eleva os
    sinais agregados de revisao do dict (`review_recommended=True`,
    `review_priority` -> no minimo "high") e acrescenta os motivos prefixados com
    "transcricao:". NAO muta o dict de entrada: trabalha sobre uma copia rasa e a
    retorna. Funcao pura (so processa dicts em memoria).
    """
    base = dict(audio_quality or {})
    assessment = assess_transcription_quality(transcription_segments, base)
    base["transcription_quality"] = assessment

    if assessment.get("review_recommended"):
        base["review_recommended"] = True
        base["review_priority"] = _max_priority(str(base.get("review_priority") or "low"), "high")
        reasons = list(base.get("review_reasons") or [])
        prefixed = [f"transcricao:{reason}" for reason in assessment.get("reasons", [])]
        _append_unique(reasons, prefixed)
        base["review_reasons"] = reasons

    return base
