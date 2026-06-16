from __future__ import annotations
"""Regras de selecao automatica de interacoes por setor.

Traduz o processo manual descrito em `instrucoes/` (PROCESSO PARA LOCALIZAR
LIGACOES E BAIXAR) para um dicionario consumido pelo orquestrador Huawei.

Campos:
    media_type       VOICE | MULTIMEDIA (WhatsApp)
    call_direction   INBOUND | OUTBOUND | None (qualquer)
    motivos_alvo     lista de substrings (case-insensitive) que DEVEM aparecer
                     na tabulacao/motivo da chamada
    motivos_excluir  lista de substrings que, se presentes, descartam a chamada
    duracao_min_segundos, duracao_max_segundos
    action           'process_voice'         - audita WAV/MP3
                     'process_voice_random'  - areas de risco (sem filtro de motivo)
                     'generate_pdf_and_process' - gera PDF do chat e audita

Setores fora do escopo Huawei ficam ausentes do dicionario:
    - mondelez  -> plataforma Tarifando (fase futura)
"""


from datetime import datetime, timezone
from typing import Any, Dict
from zoneinfo import ZoneInfo

AUTOMATION_RULES: Dict[str, Dict[str, Any]] = {
    "cadastro": {
        "media_type": "VOICE",
        "call_direction": None,
        "duracao_min_segundos": 60,
        "use_llm_triage": True,
        "motivos_alvo": ["Antecedentes"],
        "action": "process_voice",
    },
    "logistica": {
        "media_type": "VOICE",
        "call_direction": None,
        "duracao_min_segundos": 60,
        "use_llm_triage": True,
        "motivos_alvo": [
            "CONTROLE DE TEMPERATURA",
            "PARADA",
            "DESVIO",
            "FIM DE VIAGEM",
        ],
        "motivos_excluir": ["NAO FALEI COM CLIENTE", "CAIXA POSTAL"],
        "action": "process_voice",
    },
    "logistica_unilever": {
        "media_type": "VOICE",
        "call_direction": None,
        "duracao_min_segundos": 60,
        "use_llm_triage": True,
        "motivos_alvo": [
            "Atuacao tratativa",
            "Devolucao",
            "Distribuicao",
            "Cabinets",
            "Loss Tree",
            "Atuação tratativa",
            "Devolução",
            "Distribuição"
        ],
        "motivos_excluir": ["NAO FALEI COM CLIENTE", "CAIXA POSTAL"],
        "action": "process_voice",
    },
    "receptivo": {
        "media_type": "MULTIMEDIA",
        "call_direction": None,
        "motivos_alvo": [
            "ENVIO DE COMANDOS",
            "EMBARQUE DE MACROS",
            "FIM DE VIAGEM",
            "DESLIGAR SIRENE",
            "DESBLOQUEIO",
        ],
        "action": "generate_pdf_and_process",
    },
    # Areas de Risco: sem acesso automatico ao relatorio de relatos,
    # pegamos 2 chamadas com duracao > 2 min do operador no periodo.
    # Revisar assim que a chave API Huawei chegar e soubermos quais
    # campos de tabulacao estao disponiveis.
    "transferencia": {
        "media_type": "VOICE",
        "call_direction": "OUTBOUND",
        "duracao_min_segundos": 60,
        "action": "process_voice_random",
    },
    "uti": {
        "media_type": "VOICE",
        "call_direction": "OUTBOUND",
        "duracao_min_segundos": 60,
        "action": "process_voice_random",
    },
    "bas": {
        "media_type": "VOICE",
        "call_direction": "OUTBOUND",
        "duracao_min_segundos": 60,
        "action": "process_voice_random",
    },
    "distribuicao": {
        "media_type": "VOICE",
        "call_direction": "OUTBOUND",
        "duracao_min_segundos": 60,
        "action": "process_voice_random",
    },
    "fenix": {
        "media_type": "VOICE",
        "call_direction": "OUTBOUND",
        "duracao_min_segundos": 60,
        "action": "process_voice_random",
    },
}

def _coerce_numeric(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _coerce_time_millis(value: Any) -> int | None:
    numeric = _coerce_numeric(value)
    if numeric is not None:
        if numeric <= 0:
            return None
        if abs(numeric) < 10_000_000_000:
            numeric *= 1000
        return numeric

    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
            return int(dt.astimezone(timezone.utc).timestamp() * 1000)
        except ValueError:
            continue
    return None


_DURATION_KEYS = (
    "duration",
    "duracao",
    "callDuration",
    "calllDuration",
    "talkDuration",
    "talkTime",
    "durationSeconds",
    "durationSec",
    "recordDuration",
    "recordTime",
)


def get_call_reason_text(chamada: dict) -> str:
    """Extrai o texto de motivo/tabulação da chamada, testando os nomes de campo
    conhecidos da Huawei em ordem. Retorna '' se nenhum estiver preenchido. Só CPU."""
    for key in (
        "callReason",
        "talkReason",
        "talkRemark",
        "huawei_call_reason",
        "motivo",
    ):
        value = str(chamada.get(key) or "").strip()
        if value:
            return value
    return ""


def get_call_duration_seconds(chamada: dict) -> int:
    """Calcula a duração da chamada em segundos.

    Primeiro tenta os campos de duração explícitos (`_DURATION_KEYS`); se nenhum
    existir, deriva da diferença entre os timestamps de início (callBegin/
    beginTime/ackBegin/waitBegin) e fim (callEnd/endTime/logDate), coagidos a
    epoch ms. Retorna 0 quando não dá para determinar (faltam timestamps ou fim
    anterior ao início). Só CPU.
    """
    for key in _DURATION_KEYS:
        explicit_duration = _coerce_numeric(chamada.get(key))
        if explicit_duration is not None and explicit_duration >= 0:
            return explicit_duration

    start = (
        _coerce_time_millis(chamada.get("callBegin"))
        or _coerce_time_millis(chamada.get("beginTime"))
        or _coerce_time_millis(chamada.get("ackBegin"))
        or _coerce_time_millis(chamada.get("waitBegin"))
    )
    end = (
        _coerce_time_millis(chamada.get("callEnd"))
        or _coerce_time_millis(chamada.get("endTime"))
        or _coerce_time_millis(chamada.get("logDate"))
    )
    if start is None or end is None or end < start:
        return 0
    return max(0, int((end - start) / 1000))


def filtrar_chamadas(chamadas: list[dict], regra: dict) -> list[dict]:
    """Aplica `motivos_alvo`, `motivos_excluir` e filtros de duracao.

    Para cada chamada: o motivo (texto livre) é comparado, em maiúsculas, contra
    `motivos_alvo` (precisa casar uma substring) e `motivos_excluir` (descarta se
    casar). Quando a regra usa `use_llm_triage`, chamadas sem motivo legível são
    mantidas (a triagem por IA decide depois). Em seguida filtra por
    `duracao_min_segundos`/`duracao_max_segundos`. As chamadas aprovadas são
    COPIADAS (sem mutar a original) e anotadas com `duration`/`duracao`,
    `callReason` e, quando havia `motivos_alvo`, `native_reason_match` e
    `native_reason_targets`. Só CPU; não toca em banco/rede.
    """
    motivos_alvo = [m.upper() for m in regra.get("motivos_alvo", [])]
    motivos_excluir = [m.upper() for m in regra.get("motivos_excluir", [])]
    dur_min = regra.get("duracao_min_segundos")
    dur_max = regra.get("duracao_max_segundos")
    allow_missing_reason = bool(regra.get("use_llm_triage"))

    resultado: list[dict] = []
    for chamada in chamadas:
        motivo_raw = get_call_reason_text(chamada)
        motivo = motivo_raw.upper()
        reason_matches: bool | None = None
        if motivos_alvo:
            if motivo:
                reason_matches = any(alvo in motivo for alvo in motivos_alvo)
                if not reason_matches and not allow_missing_reason:
                    continue
            elif not allow_missing_reason:
                continue
        if motivos_excluir and motivo and any(excl in motivo for excl in motivos_excluir):
            continue
        duracao = get_call_duration_seconds(chamada)
        if dur_min is not None and duracao < dur_min:
            continue
        if dur_max is not None and duracao > dur_max:
            continue
        chamada_filtrada = dict(chamada)
        chamada_filtrada.setdefault("duration", duracao)
        chamada_filtrada.setdefault("duracao", duracao)
        if motivo_raw:
            chamada_filtrada.setdefault("callReason", motivo_raw)
        if motivos_alvo:
            chamada_filtrada.setdefault("native_reason_match", reason_matches)
            chamada_filtrada.setdefault("native_reason_targets", list(regra.get("motivos_alvo", [])))
        resultado.append(chamada_filtrada)
    return resultado
