from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, Tuple

@dataclass
class RawPhrase:
    timestamp: timedelta
    duration_seconds: float
    speaker_id: int
    texto: str
    texto_normalizado: str

@dataclass
class SegmentoFormatado:
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
    speaker_map: Dict[int, str] = field(default_factory=dict)
    confidence_by_id: Dict[int, float] = field(default_factory=dict)
    role_speaker_ids: Dict[str, Tuple[int, ...]] = field(default_factory=dict)
    ambiguous_ids: Tuple[int, ...] = ()
    risk_by_id: Dict[int, str] = field(default_factory=dict)
    fragmented: bool = False
    swap_risk: str = "unknown"
    raw_speaker_count: int = 0
    notes: Tuple[str, ...] = ()