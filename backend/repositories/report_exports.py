"""Repositório de registros de exportação de relatórios (tabela `report_exports`).

Mantém o histórico/auditoria de cada relatório gerado e baixado pelo sistema
(DOCX/XLSX/etc.): tipo do relatório, formato, operador, alerta, setor, score e
metadados. Não armazena o arquivo em si — só os metadados da geração.

A tabela é criada sob demanda via `ensure_report_exports_table`. O campo
`metadata_json` é saneado contra o escape de NUL (U+0000) na escrita
(`strip_json_nul`) para não quebrar casts `::jsonb` posteriores.

Sem custo de API (apenas acesso a banco/CPU).
"""

import json
from typing import Callable, Optional, Any

from db.runtime_schema import ensure_report_exports_table
from repositories.common import extract_returning_id, json_loads, normalize_source_type, strip_json_nul


ConnectionFactory = Callable[[], Any]

def save_report_export(
    get_connection: ConnectionFactory,
    report_kind: str,
    file_format: str,
    filename: str = "",
    media_type: str = "",
    generated_by: str = "",
    operator_name: str = "",
    operator_id: str = "",
    alert_id: str = "",
    alert_label: str = "",
    sector_id: str = "",
    score: Optional[float] = None,
    max_score: Optional[float] = None,
    source_type: str = "",
    audit_timestamp: str = "",
    file_size_bytes: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> int:
    """Registra a geração de um relatório exportado e retorna o id da linha criada.

    `report_kind` e `file_format` são normalizados (trim+lowercase); `source_type` é
    validado via `normalize_source_type`. `metadata` (dict opcional) é serializado em
    JSON saneado de NUL na coluna `metadata_json`. Os demais campos (operador, alerta,
    setor, score, etc.) são gravados como vieram.

    Garante a existência da tabela antes de inserir. Retorna o id do registro.
    Efeito colateral: possível DDL (criação da tabela), INSERT em `report_exports` +
    commit.
    """
    normalized_report_kind = str(report_kind or "").strip().lower()
    normalized_file_format = str(file_format or "").strip().lower()
    normalized_source_type = normalize_source_type(source_type, default=None)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        ensure_report_exports_table(cursor)
        cursor.execute(
            """
            INSERT INTO report_exports (
                report_kind, file_format, filename, media_type, generated_by,
                operator_name, operator_id, alert_id, alert_label, sector_id,
                score, max_score, source_type, audit_timestamp, file_size_bytes, metadata_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                normalized_report_kind,
                normalized_file_format,
                filename,
                media_type,
                generated_by,
                operator_name,
                operator_id,
                alert_id,
                alert_label,
                sector_id,
                score,
                max_score,
                normalized_source_type,
                audit_timestamp,
                file_size_bytes,
                strip_json_nul(json.dumps(metadata or {}, ensure_ascii=False)),
            ),
        )
        export_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        return int(export_id)
    finally:
        conn.close()


def list_report_exports(
    get_connection: ConnectionFactory,
    limit: int = 100,
    report_kind: Optional[str] = None,
    file_format: Optional[str] = None,
    operator_name: Optional[str] = None,
) -> list[dict]:
    """Lista exportações de relatórios, das mais recentes para as mais antigas.

    Filtros opcionais: `report_kind` e `file_format` (match exato, normalizados) e
    `operator_name` (LIKE case-insensitive, substring). `limit` é clampado em
    [1, 1000]. Garante a existência da tabela antes de consultar.

    Retorna uma lista de dicts com os campos do registro; `metadata_json` é
    desserializado de volta na chave `metadata` (default {}). Efeito colateral:
    possível DDL (criação da tabela) + leitura no banco.
    """
    conn = get_connection()
    try:
        # conn.row_factory handled by DictCursor
        cursor = conn.cursor()
        ensure_report_exports_table(cursor)

        query = """
            SELECT *
            FROM report_exports
            WHERE 1=1
        """
        params: list = []

        if report_kind:
            query += " AND report_kind = %s"
            params.append(report_kind.strip().lower())

        if file_format:
            query += " AND file_format = %s"
            params.append(file_format.strip().lower())

        if operator_name:
            query += " AND LOWER(COALESCE(operator_name, '')) LIKE %s"
            params.append(f"%{operator_name.strip().lower()}%")

        query += " ORDER BY created_at DESC, id DESC LIMIT %s"
        params.append(max(1, min(int(limit), 1000)))

        cursor.execute(query, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    return [
        {
            "id": row["id"],
            "created_at": row["created_at"],
            "report_kind": row["report_kind"],
            "file_format": row["file_format"],
            "filename": row["filename"],
            "media_type": row["media_type"],
            "generated_by": row["generated_by"],
            "operator_name": row["operator_name"],
            "operator_id": row["operator_id"],
            "alert_id": row["alert_id"],
            "alert_label": row["alert_label"],
            "sector_id": row["sector_id"],
            "score": row["score"],
            "max_score": row["max_score"],
            "source_type": row["source_type"],
            "audit_timestamp": row["audit_timestamp"],
            "file_size_bytes": row["file_size_bytes"],
            "metadata": json_loads(row["metadata_json"], {}),
        }
        for row in rows
    ]
