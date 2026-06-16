"""Selector deterministico de candidatos de transcricao (modelo "sandbox").

Papel no fluxo: dados varios candidatos de transcricao (cada um produzido por um
provedor real — fast / gpt4o_diarize / whisper / sdk), decide se a automacao pode
seguir com UM deles ou se o item precisa de revisao humana. NUNCA cria texto novo:
so escolhe entre os artefatos existentes ou roteia para revisao.

Estados de decisao retornados (`SelectorDecision.status`):
- DECISION_ACCEPTED     -> automacao pode prosseguir com o candidato selecionado.
- DECISION_NEEDS_REVIEW -> segue com um candidato, mas marca revisao (ex.: empate
                           que pede juiz LLM, divergencia de qualidade).
- DECISION_MANUAL_REVIEW-> exige triagem humana (candidatos curtos demais).
- DECISION_REJECTED     -> nao da para usar nenhum candidato (audio inviavel,
                           todos vazios).

CUSTO DE API: nenhum. Logica puramente deterministica em memoria (CPU); nao chama
Azure nem banco. O desempate por LLM, quando sinalizado (gate
`needs_judge_tiebreaker`), e disparado por outra camada via
`core/transcription_judge.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.transcription_candidates import TranscriptionCandidate
from core.transcription_cross_signals import pair_key


DECISION_ACCEPTED = "accepted"
DECISION_NEEDS_REVIEW = "needs_review"
DECISION_MANUAL_REVIEW = "manual_review"
DECISION_REJECTED = "rejected"


@dataclass(frozen=True)
class SelectorThresholds:
    """Limiares de decisao do selector (todos com defaults conservadores).

    - min_audio_quality_score: abaixo disto, rejeita por audio inviavel.
    - manual_audio_quality_score: reservado para politica de revisao manual.
    - min_segments_for_automation: minimo de segmentos para automacao prosseguir.
    - numeric_manual_threshold: recall numerico abaixo do qual ha divergencia
      numerica relevante (hoje resolvida pelo ranking global, v1.3.87).
    - numeric_review_threshold: recall numerico abaixo do qual marca revisao.
    - token_conflict_threshold: Jaccard de tokens abaixo do qual ha conflito de
      texto entre candidatos.
    - token_confirm_threshold: limiar de confirmacao por sobreposicao de tokens.
    - tie_ratio_threshold: diferenca relativa de score abaixo da qual dois
      candidatos sao considerados empatados (aciona desempate por juiz).
    """

    min_audio_quality_score: float = 0.30
    manual_audio_quality_score: float = 0.50
    min_segments_for_automation: int = 3
    numeric_manual_threshold: float = 0.50
    numeric_review_threshold: float = 0.80
    token_conflict_threshold: float = 0.40
    token_confirm_threshold: float = 0.85
    tie_ratio_threshold: float = 0.10


@dataclass(frozen=True)
class SelectorDecision:
    """Resultado da decisao do selector.

    Campos:
    - status: um dos DECISION_* (accepted / needs_review / manual_review / rejected).
    - reason: motivo curto (string de contrato, em snake_case PT) da decisao.
    - selected_candidate: candidato escolhido (pode existir mesmo em needs_review;
      None em rejected/manual_review).
    - review_reasons: motivos legiveis para revisao/rejeicao.
    - gates: trilha de rastreabilidade interna (quais portoes/limiares dispararam),
      util para debug; nao exibida como badge na UI.
    """

    status: str
    reason: str
    selected_candidate: Optional[TranscriptionCandidate] = None
    review_reasons: list[str] = field(default_factory=list)
    gates: dict[str, Any] = field(default_factory=dict)

    @property
    def selected_candidate_id(self) -> Optional[str]:
        """candidate_id do candidato escolhido, ou None se nao houver."""
        return self.selected_candidate.candidate_id if self.selected_candidate else None

    @property
    def selected_provider(self) -> Optional[str]:
        """Nome do provedor do candidato escolhido, ou None se nao houver."""
        return self.selected_candidate.provider if self.selected_candidate else None


def _usable_candidates(candidates: list[TranscriptionCandidate]) -> list[TranscriptionCandidate]:
    return [
        candidate
        for candidate in candidates
        if isinstance(candidate, TranscriptionCandidate)
        and not candidate.has_error
        and candidate.segment_count > 0
    ]


def _rank_candidates(candidates: list[TranscriptionCandidate]) -> list[TranscriptionCandidate]:
    """Ordena candidatos do melhor para o pior (o primeiro vira o "top").

    Criterio, em ordem de prioridade: maior deterministic_score, depois mais
    segmentos, e por fim desempate a favor do provedor "fast".
    """
    return sorted(
        candidates,
        key=lambda candidate: (
            float(candidate.deterministic_score or 0.0),
            candidate.segment_count,
            1 if candidate.provider == "fast" else 0,
        ),
        reverse=True,
    )


def _signals_for_top(
    top: TranscriptionCandidate,
    candidates: list[TranscriptionCandidate],
    cross_signals: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Coleta os sinais cruzados (pareados) entre o `top` e os demais candidatos.

    Para cada outro candidato utilizavel, busca em `cross_signals` o registro do
    par (chave via `pair_key`) — sobreposicao numerica, similaridade de tokens,
    etc. Ignora o proprio top e candidatos com status insuficiente/erro.
    """
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.candidate_id == top.candidate_id:
            continue
        if str(candidate.status or "").strip().lower() in {"insufficient", "errored", "error"}:
            continue
        signals = cross_signals.get(pair_key(top, candidate))
        if signals:
            result.append(signals)
    return result


def _numeric_min_recall(signals: dict[str, Any]) -> float:
    numeric = signals.get("numeric_overlap") if isinstance(signals, dict) else {}
    if not isinstance(numeric, dict):
        return 1.0
    return float(numeric.get("min_recall") if numeric.get("min_recall") is not None else 1.0)


def _has_numeric_evidence(signals: dict[str, Any]) -> bool:
    numeric = signals.get("numeric_overlap") if isinstance(signals, dict) else {}
    return bool(isinstance(numeric, dict) and numeric.get("has_numeric_evidence"))


def _close_score(first: TranscriptionCandidate, second: TranscriptionCandidate, threshold: float) -> bool:
    """True quando os scores dos dois candidatos sao proximos o bastante (empate).

    Compara a diferenca relativa dos `deterministic_score` (normalizada por um
    baseline >= 1.0) contra `threshold`. Empate aciona o desempate por juiz LLM.
    """
    first_score = float(first.deterministic_score or 0.0)
    second_score = float(second.deterministic_score or 0.0)
    baseline = max(abs(first_score), abs(second_score), 1.0)
    return abs(first_score - second_score) / baseline <= threshold


def select_transcription_candidate(
    candidates: list[TranscriptionCandidate],
    *,
    cross_signals: Optional[dict[str, dict[str, Any]]] = None,
    audio_quality_score: Optional[float] = None,
    critical_alert: bool = False,
    thresholds: SelectorThresholds = SelectorThresholds(),
) -> SelectorDecision:
    """Select one immutable provider artifact or route to review.

    This sandbox selector deliberately never creates new transcript text.
    It only returns an existing candidate when automation can proceed.
    """

    cross_signals = cross_signals or {}
    gates: dict[str, Any] = {
        "candidate_count": len(candidates or []),
        "usable_candidate_count": 0,
        "audio_quality_score": audio_quality_score,
        "critical_alert": critical_alert,
    }

    if audio_quality_score is not None and audio_quality_score < thresholds.min_audio_quality_score:
        gates["reject_audio_quality"] = True
        return SelectorDecision(
            status=DECISION_REJECTED,
            reason="audio_inviavel",
            review_reasons=["audio_quality_below_minimum"],
            gates=gates,
        )

    usable = _usable_candidates(candidates or [])
    gates["usable_candidate_count"] = len(usable)
    if not usable:
        gates["reject_no_candidates"] = True
        return SelectorDecision(
            status=DECISION_REJECTED,
            reason="todos_candidatos_vazios",
            review_reasons=["no_usable_transcription_candidate"],
            gates=gates,
        )

    accepted_candidates = [
        candidate
        for candidate in usable
        if str(candidate.status or "").strip().lower() in {"accepted", "selected", "candidate"}
    ]
    ranked = _rank_candidates(accepted_candidates or usable)
    top = ranked[0]
    gates["top_candidate_id"] = top.candidate_id
    gates["top_provider"] = top.provider
    gates["top_score"] = top.deterministic_score

    if all(candidate.segment_count < thresholds.min_segments_for_automation for candidate in usable):
        gates["manual_all_candidates_short"] = True
        return SelectorDecision(
            status=DECISION_MANUAL_REVIEW,
            reason="todos_candidatos_curto_demais",
            review_reasons=["all_candidates_too_short"],
            gates=gates,
        )

    top_pair_signals = _signals_for_top(top, usable, cross_signals)
    numeric_conflicts = [
        signals
        for signals in top_pair_signals
        if _has_numeric_evidence(signals)
        and _numeric_min_recall(signals) < thresholds.numeric_manual_threshold
    ]
    if numeric_conflicts:
        # v1.3.87: em vez de mandar pra manual review, aceitar o top.
        # O `deterministic_score` ja combina varios sinais globais (densidade,
        # cobertura, qualidade lexical), entao o top eh quem "transcreveu o resto
        # melhor" mesmo quando ha divergencia numerica pontual. O gate humano em
        # `audits.status=awaiting_pair` continua valendo: o auditor sempre revisa
        # antes de promover ao supervisor, e a UI da auditoria expoe a transcricao
        # selecionada pra ajuste se necessario. Persistimos os motivos no objeto
        # de decisao pra rastreabilidade interna sem badge na UI.
        gates["numeric_conflict_present"] = True
        gates["numeric_conflict_count"] = len(numeric_conflicts)
        gates["numeric_conflict_resolved_via_global_ranking"] = True
        return SelectorDecision(
            status=DECISION_ACCEPTED,
            selected_candidate=top,
            reason="divergencia_numerica_resolvida_pelo_ranking_global",
            review_reasons=["numeric_conflict_resolved_via_top_quality"],
            gates=gates,
        )

    low_numeric = [
        signals
        for signals in top_pair_signals
        if _has_numeric_evidence(signals)
        and _numeric_min_recall(signals) < thresholds.numeric_review_threshold
    ]
    low_similarity = [
        signals
        for signals in top_pair_signals
        if float(signals.get("token_jaccard") or 0.0) < thresholds.token_conflict_threshold
    ]
    top_flags = dict(top.quality_flags or {})
    high_swap_risk = str(top_flags.get("swap_risk") or "").strip().lower() == "high"

    if len(ranked) >= 2 and _close_score(top, ranked[1], thresholds.tie_ratio_threshold):
        gates["needs_judge_tiebreaker"] = True
        return SelectorDecision(
            status=DECISION_NEEDS_REVIEW,
            reason="empate_requer_judge",
            selected_candidate=top,
            review_reasons=["selector_tie_requires_judge"],
            gates=gates,
        )

    if high_swap_risk or low_numeric or low_similarity:
        gates["needs_review_quality_gap"] = True
        gates["low_numeric_count"] = len(low_numeric)
        gates["low_similarity_count"] = len(low_similarity)
        gates["high_swap_risk"] = high_swap_risk
        reasons: list[str] = []
        if high_swap_risk:
            reasons.append("speaker_swap_risk_high")
        if low_numeric:
            reasons.append("numeric_overlap_partial")
        if low_similarity:
            reasons.append("candidate_text_conflict")
        return SelectorDecision(
            status=DECISION_NEEDS_REVIEW,
            reason="candidato_exige_revisao",
            selected_candidate=top,
            review_reasons=reasons,
            gates=gates,
        )

    if critical_alert and len(usable) == 1:
        gates["critical_single_candidate_review"] = True
        return SelectorDecision(
            status=DECISION_NEEDS_REVIEW,
            reason="alerta_critico_sem_confirmacao",
            selected_candidate=top,
            review_reasons=["critical_alert_requires_secondary_candidate"],
            gates=gates,
        )

    if top.provider == "fast":
        gates["accept_fast"] = True
        return SelectorDecision(
            status=DECISION_ACCEPTED,
            reason="accept_fast",
            selected_candidate=top,
            gates=gates,
        )

    if top.provider == "gpt4o_diarize":
        gates["accept_diarize"] = True
        return SelectorDecision(
            status=DECISION_ACCEPTED,
            reason="accept_diarize",
            selected_candidate=top,
            gates=gates,
        )

    gates["accept_top_candidate"] = True
    return SelectorDecision(
        status=DECISION_ACCEPTED,
        reason="accept_top_candidate",
        selected_candidate=top,
        gates=gates,
    )


__all__ = [
    "DECISION_ACCEPTED",
    "DECISION_MANUAL_REVIEW",
    "DECISION_NEEDS_REVIEW",
    "DECISION_REJECTED",
    "SelectorDecision",
    "SelectorThresholds",
    "select_transcription_candidate",
]
