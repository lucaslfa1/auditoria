"""Helpers internos de parsing de metadata da fila de triagem.

Pequenas funções de normalização compartilhadas entre a leitura
(`classification_review_queries`) e as transições de status
(`classification_review`) da fila `fila_revisao_classificacao`.

Extraído de `repositories/classification_review.py` (v1.3.144) sem mudança de
comportamento. Mantido num módulo próprio (em vez de em `classification_review`)
para que tanto as consultas quanto as transições possam importá-lo sem criar
import circular com o módulo de fachada.
"""

from datetime import datetime, timezone
from typing import Optional, Any

from repositories.common import json_loads


def _normalize_metadata_value(value: Optional[object]) -> dict:
    """Converte `metadata_json` (dict ou string JSON) em dict mutável; inválido vira {}."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json_loads(value, {})
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_metadata_datetime(value: Any) -> Optional[datetime]:
    """Interpreta timestamp ISO vindo do metadata; retorna datetime UTC-aware ou None.

    Aceita sufixo "Z" e assume UTC quando o valor é naive (sem timezone),
    para permitir comparação segura com `datetime.now(timezone.utc)`.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
