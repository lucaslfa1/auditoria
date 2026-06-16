"""Modelo de candidato de transcrição usado pelo seletor (sandbox).

Papel no sistema: define a estrutura `TranscriptionCandidate` — um artefato de
transcrição produzido por um provider real (Fast/Whisper/SDK etc.) — junto com
helpers para construir candidatos e extrair texto a partir dos segmentos. Vários
candidatos são comparados pelo seletor de transcrição (e, eventualmente, por um
juiz LLM) para escolher a melhor transcrição.

Regra importante: o texto vem sempre de um provider real; juízes LLM podem
ranquear candidatos, mas NÃO substituem os segmentos por texto gerado.

Sem custo de API: este módulo só estrutura/normaliza dados (CPU). As chamadas
pagas de transcrição ocorrem nos providers; aqui nada chama Azure/rede/banco.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Um segmento de transcrição é um dict livre (text/speaker/start/end e extras).
Segment = dict[str, Any]


@dataclass(frozen=True)
class TranscriptionCandidate:
    """Immutable-ish transcription artifact used by the sandbox selector.

    The candidate represents text produced by a real transcription provider.
    LLM judges may rank candidates later, but must not replace these segments
    with generated text.
    """

    candidate_id: str
    provider: str
    segments: list[Segment]
    deterministic_score: float = 0.0
    status: str = "candidate"
    raw_response: Optional[Any] = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    quality_flags: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    elapsed_seconds: Optional[float] = None

    @property
    def segment_count(self) -> int:
        """Quantidade de segmentos válidos (apenas itens que são dict)."""
        return sum(1 for segment in self.segments if isinstance(segment, dict))

    @property
    def has_error(self) -> bool:
        """True se o candidato falhou (tem `error` ou `status == "errored"`)."""
        return bool(self.error) or self.status == "errored"

    @property
    def text(self) -> str:
        """Texto completo do candidato (concatenação dos textos dos segmentos)."""
        return segments_to_text(self.segments)


def clone_segments(segments: list[Segment] | None) -> list[Segment]:
    """Copia raso a lista de segmentos (descarta itens que não são dict).

    Cada segmento vira um novo dict, isolando o candidato de mutações no
    chamador. Retorna lista vazia para entrada None/vazia.
    """
    return [dict(segment) for segment in (segments or []) if isinstance(segment, dict)]


def segments_to_text(segments: list[Segment] | None) -> str:
    """Junta os textos dos segmentos em uma única string separada por espaço.

    Ignora itens não-dict e textos vazios/em branco. Retorna "" para entrada
    None/vazia.
    """
    return " ".join(
        str(segment.get("text") or "").strip()
        for segment in (segments or [])
        if isinstance(segment, dict) and str(segment.get("text") or "").strip()
    ).strip()


def build_candidate(
    provider: str,
    segments: list[Segment] | None,
    *,
    candidate_id: Optional[str] = None,
    deterministic_score: Optional[float] = None,
    status: str = "candidate",
    raw_response: Optional[Any] = None,
    provider_metadata: Optional[dict[str, Any]] = None,
    quality_flags: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
    elapsed_seconds: Optional[float] = None,
) -> TranscriptionCandidate:
    """Constrói um `TranscriptionCandidate` normalizado a partir de segmentos.

    Normaliza o nome do provider (minúsculas; "unknown" se vazio), clona os
    segmentos (`clone_segments`) e, quando `deterministic_score` não é informado,
    deriva um score padrão = soma dos tamanhos dos textos dos segmentos (favorece
    transcrições mais densas). `candidate_id` cai para o provider normalizado se
    omitido.

    Retorna um candidato imutável (dataclass frozen). Sem efeitos colaterais.
    """
    normalized_provider = str(provider or "unknown").strip().lower() or "unknown"
    cloned_segments = clone_segments(segments)
    if deterministic_score is None:
        deterministic_score = float(sum(len(str(segment.get("text") or "")) for segment in cloned_segments))
    return TranscriptionCandidate(
        candidate_id=candidate_id or normalized_provider,
        provider=normalized_provider,
        segments=cloned_segments,
        deterministic_score=float(deterministic_score or 0.0),
        status=status,
        raw_response=raw_response,
        provider_metadata=dict(provider_metadata or {}),
        quality_flags=dict(quality_flags or {}),
        error=error,
        elapsed_seconds=elapsed_seconds,
    )


__all__ = [
    "Segment",
    "TranscriptionCandidate",
    "build_candidate",
    "clone_segments",
    "segments_to_text",
]
