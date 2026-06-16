"""Helpers compartilhados pela camada de repositórios (`repositories/*`).

Concentra utilidades sem estado usadas por vários repositórios:

- Serialização JSON segura para colunas json/jsonb do Postgres, com defesa contra
  o escape de NUL (U+0000) que o `jsonb` rejeita (`strip_json_nul`, `json_dumps`,
  `harden_jsonb_nul_cast`) — ver o bloco de comentário abaixo para o contexto do
  incidente de produção.
- Leitura tolerante de linhas vindas do banco (`get_row_value`, `extract_returning_id`),
  que funcionam tanto com dict quanto com row factories do psycopg2.
- Normalização de campos de domínio (role de usuário, source_type, audit_scope,
  audit_status, prioridade da fila de revisão, setor, qualidade) contra os
  conjuntos canônicos de `db.domain_constants`.
- Conversão de uma linha de `audits` para o schema Pydantic `AuditResult`.

Sem custo de API (apenas CPU + parsing; quem chama é que faz I/O de banco).
"""

import json
import re
import unicodedata
from typing import Optional

from db.domain_constants import (
    AUDIT_SCOPES,
    AUDIT_SCOPE_CALL_QUALITY,
    AUDIT_STATUSES,
    DEFAULT_AUDIT_SCOPE,
    DEFAULT_AUDIT_STATUS,
    DEFAULT_SOURCE_TYPE,
    DEFAULT_USER_ROLE,
    REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
    REVIEW_QUEUE_PRIORITIES,
    REVIEW_QUEUE_QUERY_STATUSES,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_PENDING,
    REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
    SOURCE_TYPES,
    USER_ROLES,
)
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment


INVALID_AUDIO_QUALITY_THRESHOLD = 0.4
CALL_QUALITY_SCOPE = AUDIT_SCOPE_CALL_QUALITY


# O `jsonb` do Postgres REJEITA o escape de NUL (U+0000) mesmo sendo JSON válido
# em texto. STT/GPT/Huawei ocasionalmente emitem U+0000; `json.dumps` o grava como
# o escape literal de 6 chars (barra-invertida + u0000), que persiste em colunas
# TEXT (metadata_json, details_json, ...) e faz QUALQUER cast `::jsonb` estourar.
# Como o cast roda linha-a-linha, UMA linha corrompida derruba a query inteira
# (incidente prod 2026-06-15: GET /api/salvos retornava 500). Atacamos a raiz
# sanitizando na escrita (`strip_json_nul`) e mantemos defesa na leitura
# (`harden_jsonb_nul_cast`) para sobreviver a dados já gravados.
_JSON_NUL_ESCAPE = chr(92) + "u0000"  # a sequência de 6 chars
_JSON_NUL_CHAR = chr(0)  # o byte NUL real (defesa extra)


def strip_json_nul(text: Optional[str]) -> Optional[str]:
    """Remove o escape de NUL (U+0000) de um JSON já serializado.

    No-op para JSON sem NUL (preserva os bytes). Use ao serializar para colunas
    json/jsonb a partir de conteúdo de IA/transcrição/Huawei.
    """
    if text is None:
        return None
    return text.replace(_JSON_NUL_ESCAPE, "").replace(_JSON_NUL_CHAR, "")


_METADATA_JSONB_CAST_RE = re.compile(
    r"(?<![\w])(?P<alias>[A-Za-z_]\w*\.)?metadata_json::jsonb"
)


def harden_jsonb_nul_cast(sql: str) -> str:
    """Protege casts `metadata_json::jsonb` contra o escape de NUL (U+0000).

    Troca `<alias>.metadata_json::jsonb` por
    `replace(<alias>.metadata_json, '\\u0000', '')::jsonb` em todo o SQL,
    cobrindo qualquer alias de tabela. Defesa de leitura para linhas já gravadas
    com NUL antes da sanitização na escrita (ver `strip_json_nul`).
    """

    def _repl(match: "re.Match[str]") -> str:
        alias = match.group("alias") or ""
        return f"replace({alias}metadata_json, '{_JSON_NUL_ESCAPE}', '')::jsonb"

    return _METADATA_JSONB_CAST_RE.sub(_repl, sql)


def json_dumps(value):
    """Serializa `value` em JSON já saneado de NUL (U+0000) para colunas json/jsonb.

    Retorna None se `value` for None (deixa a coluna nula em vez de gravar "null").
    Ver `strip_json_nul` para o porquê do saneamento.
    """
    return strip_json_nul(json.dumps(value)) if value is not None else None


def json_loads(value, default=None):
    """Desserializa JSON de forma tolerante a falhas, retornando `default` em erro.

    Aceita None/"" (retorna `default`), dict/list já desserializados (retorna cópia
    rasa) e strings JSON. Em `TypeError`/`JSONDecodeError` loga um warning truncado
    e retorna `default` em vez de propagar — usado em listagens que não podem cair
    por causa de uma linha malformada.
    """
    if value in (None, ""):
        return default
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to decode JSON: %s (value: %s)", exc, repr(value)[:100])
        return default


def get_row_value(row, key: str, default=None):
    """Lê `key` de uma linha do banco independente do tipo de row.

    Funciona com dict e com objetos tipo-row do psycopg2 (que expõem `.keys()` e
    indexação por chave). Retorna `default` se a chave não existir ou se o tipo não
    for suportado. Não acessa o banco.
    """
    if isinstance(row, dict):
        return row.get(key, default)
    if hasattr(row, 'keys'):
        return row[key] if key in row.keys() else default
    return default


def extract_returning_id(row) -> int:
    """Extrai o id retornado por um `INSERT ... RETURNING id`, robusto ao tipo de row.

    Tenta `row["id"]`, depois `row[0]`, e por fim o próprio `row` como valor.
    Levanta `ValueError` se `row` for None (o INSERT não retornou nada). Não acessa
    o banco — só interpreta o resultado de `cursor.fetchone()`.
    """
    if row is None:
        raise ValueError("insert did not return an id")
    value = get_row_value(row, "id")
    if value is None:
        try:
            value = row[0]
        except (KeyError, IndexError, TypeError):
            value = row
    return int(value)


def normalize_lookup_text(value: str) -> str:
    """Normaliza texto para comparação: trim + lowercase + remove acentos (NFD).

    Usada para matching de nomes/identificadores sem sensibilidade a caixa ou
    acentuação. Não acessa o banco.
    """
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_huawei_agent_id(value) -> str:
    """Normaliza um id de agente Huawei para string canônica, tratando floats.

    Aceita int/float/str. Converte floats inteiros (ex.: 1234.0) para "1234" e
    remove parte decimal só-zeros de strings ("1234.0" -> "1234"). Trata
    "none"/"null"/"nan" (case-insensitive) e vazio como "". Não acessa o banco.
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan"}:
        return ""
    if "." in text:
        integer_part, decimal_part = text.split(".", 1)
        if integer_part.isdigit() and decimal_part and set(decimal_part) == {"0"}:
            return integer_part
    return text


def extract_audio_quality(row) -> Optional[dict]:
    """Lê e desserializa o campo `audio_quality` (JSON) da linha; None se ausente/inválido.

    Retorna o dict de qualidade de áudio ou None quando não for um objeto JSON.
    Não acessa o banco.
    """
    parsed = json_loads(get_row_value(row, "audio_quality"), None)
    return parsed if isinstance(parsed, dict) else None


def is_invalid_audio_quality(audio_quality: Optional[dict]) -> bool:
    """Indica se a qualidade de áudio está abaixo do limiar mínimo aceitável.

    Retorna True quando `audio_quality["score"]` (default 1.0) for menor que
    `INVALID_AUDIO_QUALITY_THRESHOLD` (0.4). Tolerante a dict ausente ou score
    não-numérico (retorna False nesses casos). Não acessa o banco.
    """
    if not isinstance(audio_quality, dict):
        return False
    try:
        return float(audio_quality.get("score", 1.0)) < INVALID_AUDIO_QUALITY_THRESHOLD
    except (TypeError, ValueError):
        return False


def derive_audit_scope(source_type: Optional[str], audio_quality: Optional[dict]) -> str:
    """Retorna o escopo de auditoria a usar — atualmente sempre `CALL_QUALITY_SCOPE`.

    Os parâmetros são ignorados hoje (o sistema tem um único escopo ativo, qualidade
    de ligação); a assinatura é mantida para compatibilidade. Não acessa o banco.
    """
    return CALL_QUALITY_SCOPE


def get_audit_scope(row) -> str:
    """Retorna o escopo de auditoria de uma linha — efetivamente sempre `CALL_QUALITY_SCOPE`.

    Lê e normaliza o campo `audit_scope` da linha, mas converge para
    `CALL_QUALITY_SCOPE` independente do valor armazenado (único escopo ativo).
    Não acessa o banco.
    """
    stored_scope = normalize_audit_scope(get_row_value(row, "audit_scope"), default=None)
    if stored_scope == CALL_QUALITY_SCOPE:
        return stored_scope
    return CALL_QUALITY_SCOPE


def normalize_user_role(role: Optional[str], default: Optional[str] = DEFAULT_USER_ROLE) -> Optional[str]:
    """Normaliza `role` (trim+lowercase) e valida contra `USER_ROLES`.

    Retorna o role normalizado se válido; senão retorna `default` (que pode ser
    None para sinalizar role inválido ao caller). Não acessa o banco.
    """
    normalized = str(role or "").strip().lower()
    if normalized in USER_ROLES:
        return normalized
    return default


def normalize_source_type(source_type: Optional[str], default: Optional[str] = DEFAULT_SOURCE_TYPE) -> Optional[str]:
    """Normaliza `source_type` (trim+lowercase) e valida contra `SOURCE_TYPES`.

    Retorna o valor normalizado se válido; senão `default`. Não acessa o banco.
    """
    normalized = str(source_type or "").strip().lower()
    if normalized in SOURCE_TYPES:
        return normalized
    return default


def normalize_audit_scope(scope: Optional[str], default: Optional[str] = DEFAULT_AUDIT_SCOPE) -> Optional[str]:
    """Normaliza `scope` (trim+lowercase) e valida contra `AUDIT_SCOPES`.

    Retorna o valor normalizado se válido; senão `default`. Não acessa o banco.
    """
    normalized = str(scope or "").strip().lower()
    if normalized in AUDIT_SCOPES:
        return normalized
    return default


def normalize_audit_status(status: Optional[str], default: Optional[str] = DEFAULT_AUDIT_STATUS) -> Optional[str]:
    """Normaliza `status` (trim+lowercase) e valida contra `AUDIT_STATUSES`.

    Retorna o valor normalizado se válido; senão `default`. Não acessa o banco.
    """
    normalized = str(status or "").strip().lower()
    if normalized in AUDIT_STATUSES:
        return normalized
    return default


def normalize_review_priority(
    priority: Optional[str],
    default: Optional[str] = REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
) -> Optional[str]:
    """Normaliza a prioridade da fila de revisão e valida contra `REVIEW_QUEUE_PRIORITIES`.

    Retorna o valor normalizado se válido; senão `default`
    (`REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY`). Não acessa o banco.
    """
    normalized = str(priority or "").strip().lower()
    if normalized in REVIEW_QUEUE_PRIORITIES:
        return normalized
    return default


def normalize_quality_reference(qualidade: Optional[str]) -> str:
    """Mapeia rótulos de qualidade variados para o vocabulário canônico.

    Reduz sinônimos/plurais a um de: "boa", "ruim", "zerada" ou "indefinida".
    Qualquer valor desconhecido (ou vazio) vira "indefinida". Não acessa o banco.
    """
    if not qualidade:
        return "indefinida"
    valor = qualidade.strip().lower()
    if valor in ("boa", "boas"):
        return "boa"
    if valor in ("ruim", "ruins"):
        return "ruim"
    if valor in ("zerada", "zeradas"):
        return "zerada"
    if valor in ("indefinida", "na", "n/a"):
        return "indefinida"
    return "indefinida"


def normalize_sector_id(value: Optional[str]) -> Optional[str]:
    """Normaliza id de setor (trim + minúsculas); vazio/None vira None."""
    normalized = str(value or "").strip().lower()
    return normalized or None


def normalize_review_status(status: Optional[str]) -> str:
    """Normaliza o status da fila de revisão, traduzindo aliases legados.

    Mapeia rótulos antigos (`classificado`, `auditado`, `ignorado`, `ready`) para os
    status canônicos atuais antes de validar contra `REVIEW_QUEUE_QUERY_STATUSES`.
    Valor desconhecido (ou vazio) vira `REVIEW_QUEUE_STATUS_PENDING`. Não acessa o
    banco.
    """
    valor = str(status or REVIEW_QUEUE_STATUS_PENDING).strip().lower()
    legacy_aliases = {
        "classificado": REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
        "auditado": REVIEW_QUEUE_STATUS_AUDITED,
        "ignorado": REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
        "ready": REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
    }
    valor = legacy_aliases.get(valor, valor)
    if valor in REVIEW_QUEUE_QUERY_STATUSES:
        return valor
    return REVIEW_QUEUE_STATUS_PENDING


def row_to_audit_result(row) -> Optional[AuditResult]:
    """Converte uma linha de `audits` no schema Pydantic `AuditResult`.

    Desserializa as colunas JSON `details_json` e `transcription_json` em listas de
    `AuditResultDetail`/`TranscriptionSegment` e mapeia os demais campos (score,
    summary, operador, timestamp, source_type, escopo, qualidade de áudio,
    ai_feedback). `ai_feedback` é opcional e lido de forma tolerante.

    Retorna None se `row` for falsy. Não acessa o banco — assume a linha já lida.
    """
    if not row:
        return None
    details = [AuditResultDetail(**detail) for detail in json.loads(row["details_json"])]
    transcription = [TranscriptionSegment(**segment) for segment in json.loads(row["transcription_json"])]
    ai_feedback = None
    try:
        ai_feedback = row["ai_feedback"] if "ai_feedback" in row.keys() else None
    except Exception:
        pass

    return AuditResult(
        score=row["score"],
        maxPossibleScore=row["max_score"],
        summary=row["summary"],
        details=details,
        transcription=transcription,
        operatorName=row["operator_name"],
        operatorId=row["operator_id"] or "",
        timestamp=row["timestamp"],
        input_hash=get_row_value(row, "input_hash"),
        source_type=normalize_source_type(row["source_type"], default=DEFAULT_SOURCE_TYPE),
        audit_scope=get_audit_scope(row),
        audio_quality=extract_audio_quality(row),
        audio_date=get_row_value(row, "audit_date"),
        ai_feedback=ai_feedback,
    )
