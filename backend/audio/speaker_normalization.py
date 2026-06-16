"""Utilidades de texto/tempo para a normalização de falas (diarização).

Funções puras de apoio à montagem da transcrição por locutor: formatação de
timestamp, concatenação inteligente de trechos de fala e quebra de texto em
cláusulas. Sem custo de API e sem efeitos colaterais (só CPU/strings).
"""

import re
from datetime import timedelta
from typing import List

_RE_PUNCT_PREFIX = re.compile(r"^[.,;:\!\?]")
_RE_CLAUSE_SPLIT = re.compile(r"(?<=[.!?])\s+")

def formatar_timestamp(td: timedelta) -> str:
    """Formata uma duração como ``MM:SS.mmm`` (minutos:segundos com milissegundos).

    Recebe um ``timedelta`` e retorna a string usada como marca de tempo na
    transcrição (ex.: ``"02:13.480"``). Minutos não são reiniciados a cada hora:
    uma duração de 1h vira ``"60:00.000"``. Função pura.
    """
    total_ms = td.total_seconds()
    minutes = int(total_ms // 60)
    seconds = total_ms % 60
    return f"{minutes:02d}:{seconds:06.3f}"

def unir_textos(primeiro: str, segundo: str) -> str:
    """Concatena dois trechos de fala do mesmo locutor preservando a pontuação.

    Regras: trechos vazios são ignorados (retorna o outro já com ``strip``);
    se o primeiro termina em hífen (palavra cortada) ou o segundo começa com
    pontuação (``. , ; : ! ?``), junta SEM espaço; caso contrário insere um
    espaço entre os dois. Função pura.
    """
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
    """Divide um texto em cláusulas, cortando após ``.``, ``!`` ou ``?`` seguidos de espaço.

    Retorna a lista de cláusulas (cada uma com ``strip``, sem itens vazios).
    Texto vazio retorna ``[]``; texto sem pontuação de fim de frase retorna ele
    mesmo como único elemento. Função pura.
    """
    if not texto:
        return []
    partes = [p.strip() for p in _RE_CLAUSE_SPLIT.split(texto.strip()) if p.strip()]
    return partes or [texto.strip()]
