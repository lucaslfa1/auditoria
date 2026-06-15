"""Pré-parser determinístico de nome de arquivo (sem custo de API).

Extrai operador, setor, alerta e data de nomes padronizados como:
`POSIÇÃO-MOTORISTA-20251230112504541_Camila_Florindo_Reinert_Logistica_Voz.wav`.
Essas pistas alimentam o prompt da IA e os fallbacks do alinhamento de catálogo.

Extraído de `core/classification.py` (v1.3.148) sem mudança de comportamento;
`parse_filename` e `FilenameParsed` seguem reexportados de `core.classification`
(compat com callers internos e externos como `huawei/sync_classification`).
Totalmente desacoplado de DB/IA — só stdlib + os helpers de token de alerta.
"""

import os
import re as _re
import unicodedata
from dataclasses import dataclass

from core.classification_alert_equivalence import (
    _normalize_alert_token,
    _infer_alert_actor_suffix,
)


# Alert keywords that appear at the start of filenames -> sector + alert hints.
_FILENAME_ALERT_MAP: dict[str, dict[str, str]] = {
    # Operational sectors now use sector-specific alert IDs in the catalog.
    "POSIÇÃO": {"logistica": "LOGISTICA-POSICAO", "bas": "UTI-POSICAO-MOT", "uti": "UTI-POSICAO-MOT", "transferencia": "TRANSFERENCIA-POSICAO-MOT", "distribuicao": "DISTRIBUICAO-POSICAO-MOT", "fenix": "FENIX-POSICAO-MOT"},
    "POSICAO": {"logistica": "LOGISTICA-POSICAO", "bas": "UTI-POSICAO-MOT", "uti": "UTI-POSICAO-MOT", "transferencia": "TRANSFERENCIA-POSICAO-MOT", "distribuicao": "DISTRIBUICAO-POSICAO-MOT", "fenix": "FENIX-POSICAO-MOT"},
    "PARADA": {"logistica": "LOGISTICA-PARADA", "bas": "UTI-PARADA-MOT", "uti": "UTI-PARADA-MOT", "transferencia": "TRANSFERENCIA-PARADA-MOT", "distribuicao": "DISTRIBUICAO-PARADA-MOT", "fenix": "FENIX-PARADA-MOT"},
    "DESVIO": {"logistica": "LOGISTICA-DESVIO", "bas": "UTI-DESVIO-MOT", "uti": "UTI-DESVIO-MOT", "transferencia": "TRANSFERENCIA-DESVIO-MOT", "distribuicao": "DISTRIBUICAO-DESVIO-MOT", "fenix": "FENIX-DESVIO-MOT"},
    "VIAGEM": {"logistica": "LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI"},
    "ESPELHAMENTO": {"logistica": "LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI"},
    "PERDA": {"logistica": "LOGISTICA-PERDA-POSICAO-CLI"},
    "ATRASO": {"logistica": "LOGISTICA-ATRASO"},
    "ESTADIA": {"logistica": "LOGISTICA-ESTADIA"},
    "TEMPERATURA": {"logistica": "LOGISTICA-TEMPERATURA-MOT"},
    "DESLIGAMENTO": {"logistica": "LOGISTICA-DESLIG-TEMP-MOT"},
    "POLICIA": {"bas": "BAS-PRIORITARIO-POLICIA", "transferencia": "TRANSFERENCIA-PRIORITARIO-POLICIA", "uti": "UTI-PRIORITARIO-POLICIA", "distribuicao": "DISTRIBUICAO-PRIORITARIO-POLICIA", "fenix": "FENIX-PRIORITARIO-POLICIA"},
    "POLICIAL": {"bas": "BAS-PRIORITARIO-POLICIA", "transferencia": "TRANSFERENCIA-PRIORITARIO-POLICIA", "uti": "UTI-PRIORITARIO-POLICIA", "distribuicao": "DISTRIBUICAO-PRIORITARIO-POLICIA", "fenix": "FENIX-PRIORITARIO-POLICIA"},
    "DEVOLUÇÃO": {"logistica_unilever": "UNILEVER-DEVOLUCAO"},
    "DEVOLUCAO": {"logistica_unilever": "UNILEVER-DEVOLUCAO"},
    "CABINETS": {"logistica_unilever": "UNILEVER-CABINETS"},
    "LOSS": {"logistica_unilever": "UNILEVER-LOSSTREE"},
    "ANTECEDENTES": {"cadastro": "CADASTRO-ANTECEDENTES"},
    "PRIORITARIO": {"bas": "UTI-PRIORITARIO-MOT", "transferencia": "TRANSFERENCIA-PRIORITARIO-MOT", "uti": "UTI-PRIORITARIO-MOT", "distribuicao": "DISTRIBUICAO-PRIORITARIO-MOT", "fenix": "FENIX-PRIORITARIO-MOT"},
    "PRIORITÁRIO": {"bas": "UTI-PRIORITARIO-MOT", "transferencia": "TRANSFERENCIA-PRIORITARIO-MOT", "uti": "UTI-PRIORITARIO-MOT", "distribuicao": "DISTRIBUICAO-PRIORITARIO-MOT", "fenix": "FENIX-PRIORITARIO-MOT"},
}

# Known sector keywords in filenames
_FILENAME_SECTOR_MAP: dict[str, str] = {
    "logistica": "logistica",
    "logística": "logistica",
    "transferencia": "transferencia",
    "transferência": "transferencia",
    "uti": "uti",
    "bas": "bas",
    "distribuicao": "distribuicao",
    "distribuição": "distribuicao",
    "fenix": "fenix",
    "fênix": "fenix",
    "cadastro": "cadastro",
    "unilever": "logistica_unilever",
    "mondelez": "mondelez",
    "checklist": "checklist",
    "taborda": "logistica",
    "bbm": "distribuicao",
    "receptivo": "receptivo",
    "whatsapp": "receptivo",
}

# Known non-name tokens that appear in filenames (alert types, sectors, suffixes)
_NON_NAME_TOKENS = {
    "motorista", "cliente", "policia", "polícia", "ponto", "apoio",
    "logistica", "logística", "transferencia", "transferência",
    "uti", "bas", "distribuicao", "distribuição", "fenix", "fênix", "bbm",
    "cadastro", "unilever", "mondelez", "checklist", "taborda", "receptivo",
    "voz", "audio", "áudio", "ligacao", "ligação", "agent", "whatsapp", "rastreamento", "multimidia", "multimídia",
    "viagem", "espelhamento", "perda", "excessiva",
    "node01", "node02", "wav", "mp3", "ogg", "m4a", "webm", "pdf", "jpg", "jpeg", "png",
}


@dataclass
class FilenameParsed:
    """Dados estruturados extraídos deterministicamente do nome do arquivo."""
    alert_hint: str = ""          # e.g. "POSIÇÃO-MOTORISTA"
    operator_name: str | None = None
    sector_hint: str | None = None
    alert_id_hint: str | None = None
    id_huawei: str | None = None   # e.g. from agent-XXXXX pattern
    audit_date: str | None = None  # ISO date extracted from filename (YYYY-MM-DD)


def parse_filename(filename: str) -> FilenameParsed:
    """Extrai deterministicamente operador/setor/alerta/data do nome do arquivo.

    Suporta padrões como:
      POSIÇÃO-MOTORISTA-20251230112504541_Camila_Florindo_Reinert_Logistica_Voz.wav
      ATRASO-MOTORISTA-20251230173926115_Danilo_Alves_Logistica_Voz.wav
      DESVIO-MOTORISTA-agent-11218-19_11_2025_19_57_50-node01-1763593067-198710.wav

    No padrão `agent-XXXXX` extrai o id Huawei (não há nome de operador no
    arquivo). Campos não reconhecidos ficam None — pista ausente nunca é erro.
    """
    result = FilenameParsed()

    # Remove extension
    base = os.path.splitext(filename)[0]

    # Try to extract the alert type from the beginning (before the first date/agent marker)
    # Pattern: ALERT-CONTEXT-<rest>
    alert_match = _re.match(r'^([A-ZÀ-ÚÇ]+(?:-[A-ZÀ-ÚÇ]+)*)', base)
    if alert_match:
        result.alert_hint = alert_match.group(1)

    # Check for sector keyword anywhere in the filename
    base_lower = base.lower()
    for keyword, sector_id in _FILENAME_SECTOR_MAP.items():
        if keyword in base_lower:
            result.sector_hint = sector_id
            break

    # Resolve alert_id from alert_hint + sector_hint
    if result.alert_hint:
        first_token = result.alert_hint.split("-")[0].upper()
        # Normalize accented characters for matching
        first_normalized = unicodedata.normalize("NFKD", first_token)
        first_normalized = "".join(ch for ch in first_normalized if not unicodedata.combining(ch))

        alert_sectors = _FILENAME_ALERT_MAP.get(first_token) or _FILENAME_ALERT_MAP.get(first_normalized)
        if alert_sectors and result.sector_hint:
            result.alert_id_hint = alert_sectors.get(result.sector_hint)
        elif alert_sectors and len(alert_sectors) == 1:
            # Only auto-assign sector when the alert is unambiguous (one possible sector)
            only_sector = next(iter(alert_sectors.keys()))
            result.alert_id_hint = alert_sectors[only_sector]
            if not result.sector_hint:
                result.sector_hint = only_sector

    normalized_base = _normalize_alert_token(base)
    actor = _infer_alert_actor_suffix(result.alert_hint, base)
    if result.sector_hint == "logistica":
        if "ESPELHAMENTO" in normalized_base:
            result.alert_id_hint = "LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI"
        elif "PERDA" in normalized_base and ("POSICAO" in normalized_base or "SINAL" in normalized_base):
            result.alert_id_hint = "LOGISTICA-PERDA-POSICAO-CLI"
        elif "PARADA" in normalized_base and "EXCESSIVA" in normalized_base:
            result.alert_id_hint = (
                "LOGISTICA-PARADA-EXCESSIVA-CLI"
                if actor == "CLI"
                else "LOGISTICA-PARADA-EXCESSIVA-MOT"
            )

    # Taborda WhatsApp/Multimidia tem POP dedicado (4.4.12 -> LOGISTICA-TABORDA).
    # Taborda Voz cai nos POPs genericos da Logistica (resolvidos pelo prefixo).
    if "taborda" in base_lower and (
        "whatsapp" in base_lower or "multimidia" in base_lower or "multimídia" in base_lower
    ):
        result.sector_hint = "logistica"
        result.alert_id_hint = "LOGISTICA-TABORDA"

    # Extract date from filename (e.g. 20251230112504541 → 2025-12-30)
    date_match = _re.search(r'(\d{4})(\d{2})(\d{2})\d{6,}', base)
    if date_match:
        y, m, d = date_match.group(1), date_match.group(2), date_match.group(3)
        if 2020 <= int(y) <= 2099 and 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            result.audit_date = f"{y}-{m}-{d}"
    if not result.audit_date:
        # Try agent-based pattern: agent-XXXXX-DD_MM_YYYY_HH_MM_SS
        agent_date = _re.search(r'(\d{1,2})_(\d{1,2})_(\d{4})_\d{1,2}_\d{1,2}_\d{1,2}', base)
        if agent_date:
            d2, m2, y2 = agent_date.group(1), agent_date.group(2), agent_date.group(3)
            result.audit_date = f"{y2}-{m2.zfill(2)}-{d2.zfill(2)}"

    # Extract operator name from the underscore-separated part after the date/ID
    # Pattern 1: ..._FirstName_LastName_Sector_Voz.wav (date-based)
    # Extract ID Huawei from agent-XXXXX pattern
    agent_match = _re.search(r'agent-(\d{4,6})', base)
    if agent_match:
        result.id_huawei = agent_match.group(1)

    name_match = _re.search(r'\d{10,}_(.+?)(?:_[Vv]oz|_[Rr]astreamento_[Ww]hatsapp|_[Ww]hatsapp)?$', base)
    if not name_match:
        # Pattern 2: agent-XXXX-DATE-... (agent-based) → no operator name in filename
        name_match = _re.search(r'agent-\d+', base)
        if name_match:
            return result

    if name_match and not _re.search(r'agent-\d+', base):
        name_part = name_match.group(1)
        tokens = name_part.split("_")

        # Filter out non-name tokens (sector names, "Voz", dates, numbers)
        name_tokens = []
        for token in tokens:
            token_lower = token.lower()
            # Skip if it's a known non-name token
            if token_lower in _NON_NAME_TOKENS:
                continue
            # Skip if it's purely numeric
            if _re.match(r'^\d+$', token):
                continue
            # Skip if it's a date pattern
            if _re.match(r'^\d{1,2}$', token):
                continue
            # Must start with an uppercase letter (proper name)
            if token and token[0].isupper():
                name_tokens.append(token)

        if name_tokens:
            result.operator_name = " ".join(name_tokens)

    return result
