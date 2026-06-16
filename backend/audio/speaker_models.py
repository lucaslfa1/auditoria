"""Estruturas de dados (dataclasses) da diarização de speakers.

Define os DTOs usados em todo o pipeline de detecção de falantes (módulos
`speaker_heuristics`, `speaker_identification` e `speaker_detection`):
a frase bruta vinda do STT, o segmento já rotulado (operador/motorista), as
estatísticas acumuladas por speaker_id e o resultado consolidado da análise.

Sem custo de API (só estruturas em memória/CPU).
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, Tuple

@dataclass
class RawPhrase:
    """Frase bruta como saiu do transcritor, antes da atribuição de persona.

    Campos:
        timestamp: instante de início da fala (offset desde o começo do áudio).
        duration_seconds: duração da fala em segundos.
        speaker_id: id de speaker atribuído pela diarização nativa do STT
            (>= 0). Use -1 quando não há diarização nativa disponível.
        texto: texto transcrito original (com acentuação/pontuação).
        texto_normalizado: mesmo texto após normalização (minúsculas, sem
            acentos), usado pelas heurísticas de pontuação.
    """
    timestamp: timedelta
    duration_seconds: float
    speaker_id: int
    texto: str
    texto_normalizado: str

@dataclass
class SegmentoFormatado:
    """Segmento de fala já atribuído a uma persona (operador ou interlocutor).

    É a unidade de saída do pipeline de diarização. Os campos de risco/confiança
    descrevem quão confiável foi a atribuição de falante e são consumidos
    downstream pela qualidade de diarização e pela revisão da auditoria.

    Campos:
        speaker: rótulo da persona (ex.: operator_label ou driver_label).
        source_speaker_ids: ids de speaker nativos do STT que originaram este
            segmento.
        persona_speaker_ids: todos os ids de speaker mapeados para a mesma
            persona deste segmento.
        speaker_confidence: confiança [0..1] na atribuição do falante.
        diarization_risk: risco de troca de falante ("low"/"medium"/"high"/
            "unknown").
        diarization_ambiguous: True quando o falante ficou ambíguo na análise.
    """
    timestamp: timedelta
    speaker: str
    texto: str
    texto_normalizado: str
    duracao_seconds: float
    source_speaker_ids: Tuple[int, ...] = ()
    persona_speaker_ids: Tuple[int, ...] = ()
    speaker_confidence: float = 0.0
    diarization_risk: str = "unknown"
    diarization_ambiguous: bool = False

@dataclass
class SpeakerStats:
    """Estatísticas acumuladas por speaker_id usadas para inferir a persona.

    Cada instância agrega evidências (scores de operador/interlocutor, número de
    perguntas, intros, turnos "fortes", etc.) das frases de um único speaker_id,
    servindo de base para `_avaliar_speaker_por_heuristica`.
    """
    primeira_fala_segundos: float = float('inf')
    score_operador: int = 0
    score_interlocutor: int = 0
    perguntas: int = 0
    intro_operador: int = 0
    total_frases: int = 0
    total_duracao_seconds: float = 0.0
    respostas_curtas_interlocutor: int = 0
    turnos_operador_fortes: int = 0
    turnos_interlocutor_fortes: int = 0

@dataclass
class DiarizationAnalysis:
    """Resultado consolidado da análise de diarização por speaker_id.

    Reúne o mapa final de id -> persona, confiança por id, agrupamento de ids
    por papel, ids ambíguos, risco por id e métricas globais (fragmentação,
    risco de troca, contagem de speakers e notas de diagnóstico).
    """
    speaker_map: Dict[int, str] = field(default_factory=dict)
    confidence_by_id: Dict[int, float] = field(default_factory=dict)
    role_speaker_ids: Dict[str, Tuple[int, ...]] = field(default_factory=dict)
    ambiguous_ids: Tuple[int, ...] = ()
    risk_by_id: Dict[int, str] = field(default_factory=dict)
    fragmented: bool = False
    swap_risk: str = "unknown"
    raw_speaker_count: int = 0
    notes: Tuple[str, ...] = ()