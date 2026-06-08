import re
from datetime import timedelta
from typing import List

_RE_PUNCT_PREFIX = re.compile(r"^[.,;:\!\?]")
_RE_CLAUSE_SPLIT = re.compile(r"(?<=[.!?])\s+")

def formatar_timestamp(td: timedelta) -> str:
    total_ms = td.total_seconds()
    minutes = int(total_ms // 60)
    seconds = total_ms % 60
    return f"{minutes:02d}:{seconds:06.3f}"

def unir_textos(primeiro: str, segundo: str) -> str:
    if not primeiro: return segundo.strip()
    if not segundo: return primeiro.strip()
    
    a = primeiro.strip()
    b = segundo.strip()
    
    if a.endswith("-") or _RE_PUNCT_PREFIX.match(b):
        return a + b
    return f"{a} {b}"

def _clamp_confidence(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))

def _parse_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def quebrar_texto_em_clausulas(texto: str) -> List[str]:
    if not texto:
        return []
    partes = [p.strip() for p in _RE_CLAUSE_SPLIT.split(texto.strip()) if p.strip()]
    return partes or [texto.strip()]
