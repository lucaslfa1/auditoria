import json
from pathlib import Path
import unicodedata
from typing import List, Dict, Any

from core.operator_filters import is_excluded_operation_values, is_technical_telephony_values
from db.domain_constants import AUDIT_PASS_THRESHOLD, FECHAMENTO_NOTA_STATUSES

MESES_PT = {
    1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
    7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'
}


# Tokens canonicos (sem acento, lowercase) que identificam notas telefonicas
# no fluxo legado. O layout novo define a coluna OP/TEL por operador.
RECEPTIVE_TOKENS = ('mondelez', 'receptivo')
LAYOUT_PATH = Path(__file__).resolve().parents[1] / "config" / "fechamento_qualidade_final_layout.json"
LAYOUT_NOTE_TELEFONICA = "TELEFONICA"
FECHAMENTO_DESEMPENHO_MIN_SCORE = AUDIT_PASS_THRESHOLD * 10


def _strip_accents(value: str) -> str:
    if not value:
        return ''
    nfkd = unicodedata.normalize('NFKD', value)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _canon(value: Any) -> str:
    return _strip_accents(str(value or '')).lower().strip()


def _is_removed_operator_row(row: Dict[str, Any]) -> bool:
    return is_excluded_operation_values(
        row.get('setor'),
        row.get('escala'),
        row.get('organizacao_telefonia'),
        row.get('telefonia_account'),
    ) or is_technical_telephony_values(
        nome=row.get('nome'),
        matricula=row.get('matricula'),
        supervisor=row.get('supervisor'),
        telefonia_account=row.get('telefonia_account'),
        organizacao_telefonia=row.get('organizacao_telefonia'),
        tipo_agente=row.get('tipo_agente'),
        status_telefonia=row.get('status_telefonia'),
        id_telefonia=row.get('id_telefonia'),
        softphone_number=row.get('softphone_number'),
    )


def _normalize_setor_fechamento(escala: str, setor_original: str) -> str:
    """Aplica o padrao oficial de fechamento (normalizacao) para a coluna SETOR."""
    escala_upper = str(escala).upper()
    setor_upper = str(setor_original).upper()
    texto_upper = f"{escala_upper} {setor_upper}"
    if 'FÊNIX' in escala_upper or 'FENIX' in escala_upper:
        return 'TRANSFERÊNCIA'
    if 'MONDELEZ' in texto_upper or 'UNILEVER' in texto_upper:
        return 'LOGÍSTICA'
    if 'CENTRAL' in texto_upper:
        return 'TRANSFERÊNCIA'
    if 'RJ' in escala_upper:
        return 'UTI (RJ)'
    if 'BAS' in escala_upper:
        return 'BAS'
    if 'UTI' in escala_upper:
        return 'UTI'
    return setor_original


def _is_receptive(setor: str, escala: str) -> bool:
    setor_n = _canon(setor)
    escala_n = _canon(escala)
    return any(tok in setor_n or tok in escala_n for tok in RECEPTIVE_TOKENS)


def _is_uti_rj(setor: str, escala: str) -> bool:
    """UTI/RJ: qualquer mencao a 'rj' no setor ou escala."""
    texto = _canon(setor) + ' ' + _canon(escala)
    return ' rj ' in f' {texto} ' or '-rj' in texto or '/rj' in texto or 'rj/' in texto


def _is_uti(setor: str, escala: str) -> bool:
    """UTI: mencao explicita a 'uti' no setor ou escala, incluindo UTI-COMBO."""
    texto = _canon(setor) + ' ' + _canon(escala)
    return 'uti' in texto


def _processo_uti(soma: float) -> float:
    """Formula oficial da coluna Processo - Cadeia de Contatos."""
    soma = round(float(soma), 2)
    if soma == 4 or soma > 4:
        return 1.10
    if soma == 3:
        return 1.00
    if soma in (2, 2.5):
        return 0.90
    if soma == 1:
        return 0.80
    return 0.70


def _processo_uti_rj(soma: float) -> float:
    """UTI/RJ fica na mesma tabela; so muda o criterio/peso das notas."""
    return _processo_uti(soma)


def _month_bounds(month: int, year: int) -> tuple[str, str]:
    date_start = f"{year:04d}-{month:02d}-01"
    date_end = f"{year + 1:04d}-01-01" if month == 12 else f"{year:04d}-{month + 1:02d}-01"
    return date_start, date_end


def _normalize_compare(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _override_or_none(value: Any, base_value: Any) -> Any:
    if _normalize_compare(value) == _normalize_compare(base_value):
        return None
    return value


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if hasattr(row, "keys"):
        return row[key] if key in row.keys() else default
    try:
        return row[key]
    except Exception:
        return default


def _load_layout_seed() -> list[dict[str, Any]]:
    with LAYOUT_PATH.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    return list(payload.get("rows") or [])


def _layout_count(cursor) -> int:
    cursor.execute("SELECT COUNT(*) AS total FROM fechamento_layout_operadores")
    row = cursor.fetchone()
    return int(_row_value(row, "total", _row_value(row, 0, 0)) or 0)


def _layout_match_key(value: Any) -> str:
    return _canon(value).replace(" ", "")


def _resolve_layout_colaborador_ids(cursor, layout_rows: list[dict[str, Any]]) -> dict[int, int | None]:
    cursor.execute("SELECT id, matricula, nome FROM colaboradores")
    colaboradores = cursor.fetchall()
    by_matricula: dict[str, int] = {}
    by_nome: dict[str, int] = {}
    for row in colaboradores:
        colab_id = _row_value(row, "id")
        if colab_id is None:
            continue
        matricula = _layout_match_key(_row_value(row, "matricula"))
        nome = _layout_match_key(_row_value(row, "nome"))
        if matricula and matricula not in by_matricula:
            by_matricula[matricula] = int(colab_id)
        if nome and nome not in by_nome:
            by_nome[nome] = int(colab_id)

    resolved: dict[int, int | None] = {}
    for index, layout_row in enumerate(layout_rows):
        matricula = _layout_match_key(layout_row.get("matricula"))
        nome = _layout_match_key(layout_row.get("nome"))
        resolved[index] = by_matricula.get(matricula) or by_nome.get(nome)
    return resolved


def _ensure_fechamento_layout_seeded(conn) -> bool:
    cursor = conn.cursor()
    try:
        if _layout_count(cursor) > 0:
            cursor.execute(
                """
                UPDATE fechamento_layout_operadores l
                   SET colaborador_id = c.id,
                       atualizado_em = CURRENT_TIMESTAMP
                  FROM colaboradores c
                 WHERE l.colaborador_id IS NULL
                   AND COALESCE(NULLIF(TRIM(l.matricula), ''), '') <> ''
                   AND TRIM(c.matricula) = TRIM(l.matricula)
                """
            )
            # Fallback por nome para linhas do layout sem matricula: sem ele,
            # um colaborador recriado/importado sem matricula nunca seria
            # re-vinculado e sumiria do fechamento (linhas orfas sao ocultas).
            cursor.execute(
                """
                UPDATE fechamento_layout_operadores l
                   SET colaborador_id = c.id,
                       atualizado_em = CURRENT_TIMESTAMP
                  FROM colaboradores c
                 WHERE l.colaborador_id IS NULL
                   AND COALESCE(NULLIF(TRIM(l.matricula), ''), '') = ''
                   AND LOWER(TRIM(c.nome)) = LOWER(TRIM(l.nome))
                """
            )
            conn.commit()
            return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            setattr(conn, "_fechamento_fallback_cursor", cursor)
        except Exception:
            pass
        return False

    layout_rows = _load_layout_seed()
    resolved_ids = _resolve_layout_colaborador_ids(cursor, layout_rows)
    for index, row in enumerate(layout_rows):
        cursor.execute(
            """
            INSERT INTO fechamento_layout_operadores (
                sequencia_bloco, posicao, id_visual, matricula, nome,
                turno_operacao, supervisor, setor, nota_coluna, status_base,
                huawei, weon, colaborador_id
            ) VALUES (
                %(sequencia_bloco)s, %(posicao)s, %(id_visual)s, %(matricula)s, %(nome)s,
                %(turno)s, %(supervisor)s, %(setor)s, %(nota_coluna)s, %(status_base)s,
                %(huawei)s, %(weon)s, %(colaborador_id)s
            )
            ON CONFLICT (sequencia_bloco, posicao) DO NOTHING
            """,
            {
                **row,
                "colaborador_id": resolved_ids.get(index),
            },
        )
    conn.commit()
    return True


def _format_note_value(value: Any) -> str:
    if value in ("", None):
        return ""
    return str(value)


def _auditavel_is_false(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return int(value) == 0
    normalized = _canon(value)
    return normalized in {"0", "false", "f", "nao", "não", "no", "n"}


def _resolve_fechamento_status(row: dict[str, Any], fallback_status: Any = "ATIVO") -> str:
    # Importante: NAO converter `auditavel=False` em "INATIVO" no fechamento.
    # Um operador pode estar ATIVO + nao-auditavel (decisao operacional —
    # exemplo: pessoa atua na operacao mas a IA nao avalia ela). Forcar
    # INATIVO escondia esses operadores do fechamento (BUG-026 reportado por
    # Fatima de Jesus Gutierrez em 2026-05-26: "a Fernanda precisa ficar para
    # o fechamento mesmo nao sendo auditada").
    # A flag `auditavel` so vale para o pipeline da IA; o status visual no
    # fechamento deve refletir apenas `colaboradores.status`.
    status = str(fallback_status or "ATIVO").strip().upper()
    return "INATIVO" if status == "INATIVO" else "ATIVO"


def _resolve_desempenho(status: str, media_auditoria: Any) -> str:
    if str(status or "").upper() == "INATIVO":
        return "INATIVO"
    if media_auditoria is None:
        return ""
    try:
        nota = float(media_auditoria)
    except (TypeError, ValueError):
        return ""
    return "BOM" if nota >= FECHAMENTO_DESEMPENHO_MIN_SCORE else "RUIM"


def _calculate_process_and_final(
    row: dict[str, Any],
    *,
    status: str,
    setor: str,
    turno: str,
    processo_override: Any = None,
    final_override: Any = None,
    apply_overrides: bool = True,
) -> tuple[str, str]:
    cadeia_val = 0.70
    uti_rj = _is_uti_rj(setor, turno)
    uti_simples = (not uti_rj) and _is_uti(setor, turno)
    if uti_rj or uti_simples:
        soma = (
            float(row.get('nota_mot', 0) or 0)
            + float(row.get('nota_pa', 0) or 0)
            + float(row.get('nota_cli', 0) or 0)
            + float(row.get('nota_policia', 0) or 0)
        )
        cadeia_val = _processo_uti_rj(soma) if uti_rj else _processo_uti(soma)

    processo_val = f"{int(cadeia_val * 100)}%"
    if apply_overrides and processo_override is not None:
        processo_val = processo_override

    if status.upper() == 'INATIVO':
        final_val = 'Adeus'
    elif cadeia_val == 0.70:
        final_val = '-4%'
    elif 0.80 < cadeia_val < 1.00:
        final_val = '-2%'
    elif cadeia_val == 1.00:
        final_val = '2%'
    elif cadeia_val > 1.00:
        final_val = '4%'
    else:
        final_val = ''
    if apply_overrides and final_override is not None:
        final_val = final_override

    return processo_val, final_val


def _format_registered_layout_row(
    row: dict[str, Any],
    *,
    layout_id: int | None = None,
    row_id: int,
    mes_str: str,
    apply_overrides: bool,
) -> Dict[str, Any]:
    nome = row.get('nome_override') if apply_overrides and row.get('nome_override') is not None else row.get('nome')
    matricula = (
        row.get('matricula_override')
        if apply_overrides and row.get('matricula_override') is not None
        else row.get('matricula')
    )
    # Supervisor acompanha o cadastro atual do colaborador; fechamento nao
    # pode manter um nome antigo via override.
    supervisor = row.get('supervisor')
    setor = row.get('setor_override') if apply_overrides and row.get('setor_override') is not None else row.get('setor')
    escala = row.get('turno_override') if apply_overrides and row.get('turno_override') is not None else row.get('escala')
    huawei = row.get('huawei_override') if apply_overrides and row.get('huawei_override') is not None else row.get('id_huawei')
    weon = row.get('weon_override') if apply_overrides and row.get('weon_override') is not None else row.get('id_weon')

    status_base = _resolve_fechamento_status(row, row.get('status') or 'ATIVO')
    status = (
        row.get('status_override')
        if apply_overrides and row.get('status_override') is not None
        else status_base
    )
    status = _resolve_fechamento_status(row, status)

    media_auditoria = row.get('media_auditoria')
    is_receptivo = _is_receptive(setor or '', escala or '')
    escala_lower = _canon(escala)

    operacional_val = ''
    telefonica_val = ''
    if media_auditoria is not None:
        if is_receptivo:
            telefonica_val = float(media_auditoria)
        else:
            operacional_val = float(media_auditoria)

    if apply_overrides and row.get('operacional_override') is not None:
        operacional_val = row.get('operacional_override')
    if apply_overrides and row.get('telefonica_override') is not None:
        telefonica_val = row.get('telefonica_override')

    desempenho = _resolve_desempenho(status, media_auditoria)
    if apply_overrides and row.get('desempenho_override') is not None:
        desempenho = row.get('desempenho_override')

    processo_override = row.get('processo_override')
    final_override = row.get('final_override')
    processo_val, final_val = _calculate_process_and_final(
        row,
        status=status,
        setor=setor or '',
        turno=escala or '',
        processo_override=processo_override,
        final_override=final_override,
        apply_overrides=apply_overrides,
    )

    huawei_val = '-' if 'mondelez' in escala_lower else (huawei or '')
    weon_val = '-' if 'mondelez' in escala_lower else (weon or '')

    return {
        'layout_id': layout_id,
        'colab_id': row.get('colab_id'),
        'id': row_id,
        'mes_str': mes_str,
        'matricula': matricula or '',
        'nome': nome or '',
        'operacional': str(operacional_val) if operacional_val != '' else '',
        'telefonica': str(telefonica_val) if telefonica_val != '' else '',
        'desempenho': desempenho,
        'status': status,
        'turno': escala or '',
        'supervisor': supervisor or '',
        'setor': _normalize_setor_fechamento(escala if escala else setor, setor or ''),
        'nota_mot': float(row.get('nota_mot', 0) or 0),
        'nota_pa': float(row.get('nota_pa', 0) or 0),
        'nota_cli': float(row.get('nota_cli', 0) or 0),
        'nota_policia': float(row.get('nota_policia', 0) or 0),
        'processo': processo_val,
        'final': final_val,
        'huawei': huawei_val,
        'weon': weon_val,
    }


def _append_and_link_registered_rows_for_layout(
    conn,
    results: list[Dict[str, Any]],
    month: int,
    year: int,
    *,
    apply_overrides: bool,
) -> None:
    """Vincula ao layout os colaboradores cadastrados ainda ausentes.

    O layout oficial preserva a ordem/estrutura da planilha de fechamento,
    mas a fonte de verdade sobre quem esta cadastrado e `colaboradores`.
    Assim, qualquer colaborador elegivel que nao tenha linha no layout ganha
    uma linha vinculada por `colaborador_id`. Se o auditor removeu alguem do
    fechamento, a linha desativada no layout continua bloqueando o retorno
    automatico.
    """
    cursor = conn.cursor()
    date_start, date_end = _month_bounds(month, year)
    sql = """
    WITH media_mensal AS (
        SELECT
            colaborador_id,
            ROUND(CAST(AVG(CASE WHEN max_score > 0 THEN (score * 1.0 / max_score) * 10 ELSE 0 END) AS NUMERIC), 2) as media_auditoria
        FROM audits
        WHERE status = ANY(%s)
          AND COALESCE(audit_date, timestamp)::TIMESTAMP >= %s
          AND COALESCE(audit_date, timestamp)::TIMESTAMP < %s
        GROUP BY colaborador_id
    )
    SELECT
        c.id AS colab_id,
        c.nome,
        c.matricula,
        c.supervisor,
        c.setor,
        c.escala,
        c.status,
        c.id_huawei,
        c.id_weon,
        c.id_telefonia,
        c.softphone_number,
        c.telefonia_account,
        c.organizacao_telefonia,
        c.tipo_agente,
        c.status_telefonia,
        c.auditavel,
        COALESCE(f.nota_mot, 0) AS nota_mot,
        COALESCE(f.nota_pa, 0) AS nota_pa,
        COALESCE(f.nota_cli, 0) AS nota_cli,
        COALESCE(f.nota_policia, 0) AS nota_policia,
        f.matricula_override,
        f.nome_override,
        f.operacional_override,
        f.telefonica_override,
        f.desempenho_override,
        f.status_override,
        f.turno_override,
        f.supervisor_override,
        f.setor_override,
        f.processo_override,
        f.final_override,
        f.huawei_override,
        f.weon_override,
        m.media_auditoria
    FROM colaboradores c
    LEFT JOIN fechamento_cadeia_contatos f
      ON c.id = f.colaborador_id AND f.mes = %s AND f.ano = %s
    LEFT JOIN media_mensal m
      ON c.id = m.colaborador_id
    WHERE (
        UPPER(COALESCE(c.status, '')) = 'ATIVO'
        OR UPPER(COALESCE(c.status, '')) = 'INATIVO'
        OR m.media_auditoria IS NOT NULL
    )
      AND c.nome IS NOT NULL
      AND TRIM(c.nome) != ''
      -- Quem ja tem linha no layout (ativa OU removida pelo auditor) nao
      -- entra pelo complemento: linha ativa ja aparece pelo layout, e linha
      -- desativada e uma remocao explicita que nao pode reviver aqui.
      AND NOT EXISTS (
        SELECT 1 FROM fechamento_layout_operadores lx
        WHERE lx.colaborador_id = c.id
      )
    ORDER BY COALESCE(NULLIF(c.supervisor, ''), '') ASC, c.nome ASC
    """
    cursor.execute(sql, (list(FECHAMENTO_NOTA_STATUSES), date_start, date_end, month, year))

    seen_colab_ids = {int(row['colab_id']) for row in results if row.get('colab_id')}
    seen_matriculas = {_layout_match_key(row.get('matricula')) for row in results if _layout_match_key(row.get('matricula'))}
    next_id = max([int(row.get('id') or 0) for row in results] or [0]) + 1
    mes_str = MESES_PT.get(month, '')
    candidate_rows: list[dict[str, Any]] = []

    for raw_row in cursor.fetchall():
        row = dict(raw_row) if not isinstance(raw_row, dict) else raw_row
        if _is_removed_operator_row(row):
            continue

        colab_id = row.get('colab_id')
        matricula_key = _layout_match_key(row.get('matricula'))
        if (
            (colab_id and int(colab_id) in seen_colab_ids)
            or (matricula_key and matricula_key in seen_matriculas)
        ):
            continue
        candidate_rows.append(row)
        if colab_id:
            seen_colab_ids.add(int(colab_id))
        if matricula_key:
            seen_matriculas.add(matricula_key)

    if not candidate_rows:
        return

    cursor.execute("SELECT COALESCE(MAX(sequencia_bloco), 0) AS max_seq FROM fechamento_layout_operadores")
    next_sequence = int(_row_value(cursor.fetchone(), "max_seq", 0) or 0) + 1

    for row in candidate_rows:
        colab_id = row.get('colab_id')
        nota_coluna = (
            LAYOUT_NOTE_TELEFONICA
            if _is_receptive(row.get("setor") or "", row.get("escala") or "")
            else "OPERACIONAL"
        )
        cursor.execute(
            """
            INSERT INTO fechamento_layout_operadores (
                sequencia_bloco, posicao, id_visual, matricula, nome,
                turno_operacao, supervisor, setor, nota_coluna, status_base,
                huawei, weon, colaborador_id, ativo
            ) VALUES (
                %(sequencia_bloco)s, 1, %(id_visual)s, %(matricula)s, %(nome)s,
                %(turno)s, %(supervisor)s, %(setor)s, %(nota_coluna)s, %(status_base)s,
                %(huawei)s, %(weon)s, %(colaborador_id)s, TRUE
            )
            RETURNING id
            """,
            {
                "sequencia_bloco": next_sequence,
                "id_visual": next_id,
                "matricula": row.get("matricula") or "",
                "nome": row.get("nome") or "",
                "turno": row.get("escala") or "",
                "supervisor": row.get("supervisor") or "",
                "setor": row.get("setor") or "",
                "nota_coluna": nota_coluna,
                "status_base": str(row.get("status") or "ATIVO").strip().upper() or "ATIVO",
                "huawei": row.get("id_huawei") or "",
                "weon": row.get("id_weon") or "",
                "colaborador_id": colab_id,
            },
        )
        inserted = cursor.fetchone()
        layout_id = _row_value(inserted, "id")

        results.append(
            _format_registered_layout_row(
                row,
                layout_id=int(layout_id) if layout_id else None,
                row_id=next_id,
                mes_str=mes_str,
                apply_overrides=apply_overrides,
            )
        )
        next_id += 1
        next_sequence += 1
    conn.commit()


def _get_fechamento_rows_from_layout(conn, month: int, year: int, *, apply_overrides: bool = True) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    date_start, date_end = _month_bounds(month, year)

    sql = """
    WITH media_mensal AS (
        SELECT
            colaborador_id,
            ROUND(CAST(AVG(CASE WHEN max_score > 0 THEN (score * 1.0 / max_score) * 10 ELSE 0 END) AS NUMERIC), 2) as media_auditoria
        FROM audits
        WHERE status = ANY(%s)
          AND COALESCE(audit_date, timestamp)::TIMESTAMP >= %s
          AND COALESCE(audit_date, timestamp)::TIMESTAMP < %s
        GROUP BY colaborador_id
    )
    SELECT
        l.id AS layout_id,
        l.id_visual,
        l.sequencia_bloco,
        l.posicao,
        l.matricula AS layout_matricula,
        l.nome AS layout_nome,
        l.turno_operacao AS layout_turno,
        l.supervisor AS layout_supervisor,
        l.setor AS layout_setor,
        l.nota_coluna,
        l.status_base,
        l.huawei AS layout_huawei,
        l.weon AS layout_weon,
        c.id AS colab_id,
        c.nome AS db_nome,
        c.matricula AS db_matricula,
        c.supervisor AS db_supervisor,
        c.status AS db_status,
        c.id_huawei AS db_huawei,
        c.id_weon AS db_weon,
        c.setor AS db_setor,
        c.escala AS db_escala,
        c.id_telefonia,
        c.softphone_number,
        c.telefonia_account,
        c.organizacao_telefonia,
        c.tipo_agente,
        c.status_telefonia,
        c.auditavel,
        COALESCE(lo.nota_mot, f.nota_mot, 0) AS nota_mot,
        COALESCE(lo.nota_pa, f.nota_pa, 0) AS nota_pa,
        COALESCE(lo.nota_cli, f.nota_cli, 0) AS nota_cli,
        COALESCE(lo.nota_policia, f.nota_policia, 0) AS nota_policia,
        lo.matricula_override AS layout_matricula_override,
        lo.nome_override AS layout_nome_override,
        lo.operacional_override AS layout_operacional_override,
        lo.telefonica_override AS layout_telefonica_override,
        lo.desempenho_override AS layout_desempenho_override,
        lo.status_override AS layout_status_override,
        lo.turno_override AS layout_turno_override,
        lo.supervisor_override AS layout_supervisor_override,
        lo.setor_override AS layout_setor_override,
        lo.processo_override AS layout_processo_override,
        lo.final_override AS layout_final_override,
        lo.huawei_override AS layout_huawei_override,
        lo.weon_override AS layout_weon_override,
        f.matricula_override,
        f.nome_override,
        f.operacional_override,
        f.telefonica_override,
        f.desempenho_override,
        f.status_override,
        f.turno_override,
        f.supervisor_override,
        f.setor_override,
        f.processo_override,
        f.final_override,
        f.huawei_override,
        f.weon_override,
        m.media_auditoria
    FROM fechamento_layout_operadores l
    LEFT JOIN colaboradores c
      ON c.id = l.colaborador_id
    LEFT JOIN fechamento_layout_overrides lo
      ON lo.layout_id = l.id AND lo.mes = %s AND lo.ano = %s
    LEFT JOIN fechamento_cadeia_contatos f
      ON c.id = f.colaborador_id AND f.mes = %s AND f.ano = %s
    LEFT JOIN media_mensal m
      ON c.id = m.colaborador_id
    WHERE l.ativo = TRUE
      AND c.id IS NOT NULL
    ORDER BY l.sequencia_bloco ASC, l.posicao ASC
    """
    # `c.id IS NOT NULL`: colaborador apagado (FK ON DELETE SET NULL) deixava
    # a linha do layout viva com o nome congelado da planilha — fechamento
    # exibia gente que ja saiu (revisao 2026-06-12, item 2). O re-vinculo por
    # matricula/nome roda a cada carga, entao recriar o colaborador revive a
    # linha automaticamente.
    # ANY(%s) exige list (tuple vira "record" no psycopg2, nao array).
    cursor.execute(sql, (list(FECHAMENTO_NOTA_STATUSES), date_start, date_end, month, year, month, year))
    db_rows = cursor.fetchall()
    mes_str = MESES_PT.get(month, '')
    results = []

    for raw_row in db_rows:
        row = dict(raw_row) if not isinstance(raw_row, dict) else raw_row

        # Base de nome/matricula/status vem de `colaboradores` (dado vivo);
        # a copia do layout (planilha de fevereiro) e so fallback. Sem isso,
        # renomes e inativacoes nao apareciam no fechamento. Overrides do
        # auditor continuam tendo precedencia sobre tudo.
        status_base = _resolve_fechamento_status(row, row.get('db_status') or row.get('status_base') or 'ATIVO')
        status = row.get('layout_status_override') if apply_overrides and row.get('layout_status_override') is not None else None
        if status is None:
            status = row.get('status_override') if apply_overrides and row.get('status_override') is not None else status_base
        status = _resolve_fechamento_status(row, status)

        matricula = row.get('layout_matricula_override') if apply_overrides and row.get('layout_matricula_override') is not None else None
        if matricula is None:
            matricula = (
                row.get('matricula_override')
                if apply_overrides and row.get('matricula_override') is not None
                else (row.get('db_matricula') or row.get('layout_matricula'))
            )

        nome = row.get('layout_nome_override') if apply_overrides and row.get('layout_nome_override') is not None else None
        if nome is None:
            nome = (
                row.get('nome_override')
                if apply_overrides and row.get('nome_override') is not None
                else (row.get('db_nome') or row.get('layout_nome'))
            )

        turno = row.get('layout_turno_override') if apply_overrides and row.get('layout_turno_override') is not None else None
        if turno is None:
            turno = row.get('turno_override') if apply_overrides and row.get('turno_override') is not None else row.get('layout_turno')

        # Supervisor segue a mesma regra do operador: a fonte de verdade e o
        # cadastro atual do colaborador. O fechamento nao pode manter supervisor
        # antigo via layout/override, porque um supervisor removido do cadastro
        # continuaria aparecendo no Excel.
        supervisor = row.get('db_supervisor') or ''

        setor = row.get('layout_setor_override') if apply_overrides and row.get('layout_setor_override') is not None else None
        if setor is None:
            setor = row.get('setor_override') if apply_overrides and row.get('setor_override') is not None else row.get('layout_setor')

        huawei_layout = row.get('layout_huawei') or ''
        huawei_base = huawei_layout if huawei_layout == '-' else (row.get('db_huawei') or huawei_layout or '')
        huawei = row.get('layout_huawei_override') if apply_overrides and row.get('layout_huawei_override') is not None else None
        if huawei is None:
            huawei = row.get('huawei_override') if apply_overrides and row.get('huawei_override') is not None else huawei_base

        weon_layout = row.get('layout_weon') or ''
        weon_base = weon_layout if weon_layout == '-' else (row.get('db_weon') or weon_layout or '')
        weon = row.get('layout_weon_override') if apply_overrides and row.get('layout_weon_override') is not None else None
        if weon is None:
            weon = row.get('weon_override') if apply_overrides and row.get('weon_override') is not None else weon_base

        media_auditoria = row.get('media_auditoria')
        nota_coluna = str(row.get('nota_coluna') or 'OPERACIONAL').upper()
        operacional_val = ''
        telefonica_val = ''
        if media_auditoria is not None:
            if nota_coluna == LAYOUT_NOTE_TELEFONICA:
                telefonica_val = float(media_auditoria)
            else:
                operacional_val = float(media_auditoria)

        operacional_override = row.get('layout_operacional_override')
        if operacional_override is None:
            operacional_override = row.get('operacional_override')
        telefonica_override = row.get('layout_telefonica_override')
        if telefonica_override is None:
            telefonica_override = row.get('telefonica_override')
        if apply_overrides and operacional_override is not None:
            operacional_val = operacional_override
        if apply_overrides and telefonica_override is not None:
            telefonica_val = telefonica_override

        desempenho = _resolve_desempenho(status, media_auditoria)
        desempenho_override = row.get('layout_desempenho_override')
        if desempenho_override is None:
            desempenho_override = row.get('desempenho_override')
        if apply_overrides and desempenho_override is not None:
            desempenho = desempenho_override

        processo_override = row.get('layout_processo_override')
        if processo_override is None:
            processo_override = row.get('processo_override')
        final_override = row.get('layout_final_override')
        if final_override is None:
            final_override = row.get('final_override')
        processo_val, final_val = _calculate_process_and_final(
            row,
            status=status,
            setor=setor or '',
            turno=turno or '',
            processo_override=processo_override,
            final_override=final_override,
            apply_overrides=apply_overrides,
        )

        results.append({
            'layout_id': row.get('layout_id'),
            'colab_id': row.get('colab_id') or 0,
            'id': row.get('id_visual'),
            'mes_str': mes_str,
            'matricula': matricula or '',
            'nome': nome or '',
            'operacional': _format_note_value(operacional_val),
            'telefonica': _format_note_value(telefonica_val),
            'desempenho': desempenho,
            'status': status,
            'turno': turno or '',
            'supervisor': supervisor or '',
            'setor': setor or '',
            'nota_mot': float(row.get('nota_mot', 0) or 0),
            'nota_pa': float(row.get('nota_pa', 0) or 0),
            'nota_cli': float(row.get('nota_cli', 0) or 0),
            'nota_policia': float(row.get('nota_policia', 0) or 0),
            'processo': processo_val,
            'final': final_val,
            'huawei': huawei or '',
            'weon': weon or '',
        })

    _append_and_link_registered_rows_for_layout(conn, results, month, year, apply_overrides=apply_overrides)
    return results


def _get_fechamento_rows_legacy(conn, month: int, year: int, *, apply_overrides: bool = True) -> List[Dict[str, Any]]:
    cursor = getattr(conn, "_fechamento_fallback_cursor", None)
    if cursor is not None:
        try:
            delattr(conn, "_fechamento_fallback_cursor")
        except Exception:
            pass
    else:
        cursor = conn.cursor()
    date_start, date_end = _month_bounds(month, year)

    if apply_overrides:
        nome_expr = "COALESCE(f.nome_override, c.nome)"
        matricula_expr = "COALESCE(f.matricula_override, c.matricula)"
        supervisor_expr = "c.supervisor"
        setor_expr = "COALESCE(f.setor_override, c.setor)"
        escala_expr = "COALESCE(f.turno_override, c.escala)"
        huawei_expr = "COALESCE(f.huawei_override, c.id_huawei)"
        weon_expr = "COALESCE(f.weon_override, c.id_weon)"
        status_expr = "COALESCE(f.status_override, c.status)"
    else:
        nome_expr = "c.nome"
        matricula_expr = "c.matricula"
        supervisor_expr = "c.supervisor"
        setor_expr = "c.setor"
        escala_expr = "c.escala"
        huawei_expr = "c.id_huawei"
        weon_expr = "c.id_weon"
        status_expr = "c.status"
    
    sql = f"""
    WITH media_mensal AS (
        SELECT 
            colaborador_id,
            ROUND(CAST(AVG(CASE WHEN max_score > 0 THEN (score * 1.0 / max_score) * 10 ELSE 0 END) AS NUMERIC), 2) as media_auditoria
        FROM audits
        WHERE status = ANY(%s)
          AND COALESCE(audit_date, timestamp)::TIMESTAMP >= %s
          AND COALESCE(audit_date, timestamp)::TIMESTAMP < %s
        GROUP BY colaborador_id
    )
    SELECT 
        c.id as colab_id, 
        {nome_expr} as nome, 
        {matricula_expr} as matricula, 
        {supervisor_expr} as supervisor, 
        {setor_expr} as setor, 
        {escala_expr} as escala,
        {huawei_expr} as id_huawei, 
        {weon_expr} as id_weon,
        {status_expr} as status,
        c.id_telefonia,
        c.softphone_number,
        c.telefonia_account,
        c.organizacao_telefonia,
        c.tipo_agente,
        c.status_telefonia,
        c.auditavel,
        COALESCE(f.nota_mot, 0) as nota_mot, 
        COALESCE(f.nota_pa, 0) as nota_pa, 
        COALESCE(f.nota_cli, 0) as nota_cli, 
        COALESCE(f.nota_policia, 0) as nota_policia,
        f.operacional_override,
        f.telefonica_override,
        f.desempenho_override,
        f.processo_override,
        f.final_override,
        f.weon_override,
        m.media_auditoria
    FROM colaboradores c
    LEFT JOIN fechamento_cadeia_contatos f 
      ON c.id = f.colaborador_id AND f.mes = %s AND f.ano = %s
    LEFT JOIN media_mensal m
      ON c.id = m.colaborador_id
    WHERE (
        UPPER(c.status) = 'ATIVO' 
        OR UPPER(c.status) = 'INATIVO'
        OR m.media_auditoria IS NOT NULL
    )
      AND c.nome IS NOT NULL
      AND TRIM(c.nome) != ''
    ORDER BY COALESCE(c.supervisor, '') ASC, COALESCE(f.nome_override, c.nome) ASC
    """
    cursor.execute(sql, (list(FECHAMENTO_NOTA_STATUSES), date_start, date_end, month, year))
    db_rows = cursor.fetchall()
    
    results = []
    current_supervisor = None
    current_id = 1
    mes_str = MESES_PT.get(month, '')

    for r in db_rows:
        row = dict(r) if not isinstance(r, dict) else r
        
        # Puxar dados brutos
        nome = row.get('nome', '') or ''
        matricula = row.get('matricula', '') or ''
        supervisor = row.get('supervisor', '') or ''
        setor = row.get('setor', '') or ''
        escala = row.get('escala', '') or '' # Usaremos como Turno/Operacao
        id_huawei = row.get('id_huawei', '') or ''
        id_weon = row.get('id_weon', '') or ''
        status = _resolve_fechamento_status(row, row.get('status', '') or 'ATIVO')
        media_auditoria = row.get('media_auditoria')

        if not nome.strip() or _is_removed_operator_row(row):
            continue
        
        # Manual overrides
        operacional_override = row.get('operacional_override')
        telefonica_override = row.get('telefonica_override')
        desempenho_override = row.get('desempenho_override')
        processo_override = row.get('processo_override')
        final_override = row.get('final_override')
        
        if supervisor != current_supervisor:
            current_supervisor = supervisor
            current_id = 1
        else:
            current_id += 1

        is_receptivo = _is_receptive(setor, escala)
        escala_lower = _canon(escala)

        operacional_val = ''
        telefonica_val = ''
        if media_auditoria is not None:
            if is_receptivo:
                telefonica_val = float(media_auditoria)
            else:
                operacional_val = float(media_auditoria)
                
        if apply_overrides and operacional_override is not None:
            operacional_val = operacional_override
        if apply_overrides and telefonica_override is not None:
            telefonica_val = telefonica_override

        desempenho = _resolve_desempenho(status, media_auditoria)
        if apply_overrides and desempenho_override is not None:
            desempenho = desempenho_override

        processo_val, final_val = _calculate_process_and_final(
            row,
            status=status,
            setor=setor,
            turno=escala,
            processo_override=processo_override,
            final_override=final_override,
            apply_overrides=apply_overrides,
        )
            
        huawei_val = '-' if 'mondelez' in escala_lower else id_huawei
        weon_val = '-' if 'mondelez' in escala_lower else id_weon

        results.append({
            'layout_id': None,
            'colab_id': row.get('colab_id'),
            'id': current_id,
            'mes_str': mes_str,
            'matricula': matricula,
            'nome': nome,
            'operacional': str(operacional_val) if operacional_val != '' else '',
            'telefonica': str(telefonica_val) if telefonica_val != '' else '',
            'desempenho': desempenho,
            'status': status,
            'turno': escala,
            'supervisor': supervisor,
            'setor': _normalize_setor_fechamento(escala if escala else setor, setor),
            'nota_mot': float(row.get('nota_mot', 0)),
            'nota_pa': float(row.get('nota_pa', 0)),
            'nota_cli': float(row.get('nota_cli', 0)),
            'nota_policia': float(row.get('nota_policia', 0)),
            'processo': processo_val,
            'final': final_val,
            'huawei': huawei_val,
            'weon': weon_val,
        })
        
    return results


def get_fechamento_rows(conn, month: int, year: int, *, apply_overrides: bool = True) -> List[Dict[str, Any]]:
    if _ensure_fechamento_layout_seeded(conn):
        return _get_fechamento_rows_from_layout(conn, month, year, apply_overrides=apply_overrides)
    return _get_fechamento_rows_legacy(conn, month, year, apply_overrides=apply_overrides)


def add_fechamento_layout_operador(conn, colaborador_id: int) -> Dict[str, Any]:
    """Inclui (ou reativa) um colaborador no layout do fechamento.

    Se ja existir linha no layout para o colaborador, ela e reativada
    (preserva posicao/overrides historicos). Caso contrario, cria uma linha
    nova no fim da planilha (bloco proprio, ID visual 1 — editavel depois
    pela propria tela). Levanta ValueError se o colaborador nao existe.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, nome, matricula, supervisor, setor, escala, status, id_huawei, id_weon
        FROM colaboradores WHERE id = %s
        """,
        (colaborador_id,),
    )
    colab_row = cursor.fetchone()
    if not colab_row:
        raise ValueError(f"Colaborador {colaborador_id} nao encontrado")
    colab = dict(colab_row) if not isinstance(colab_row, dict) else colab_row

    cursor.execute(
        "SELECT id FROM fechamento_layout_operadores WHERE colaborador_id = %s ORDER BY id LIMIT 1",
        (colaborador_id,),
    )
    existing = cursor.fetchone()
    if existing:
        layout_id = int(_row_value(existing, "id"))
        cursor.execute(
            """
            UPDATE fechamento_layout_operadores
               SET ativo = TRUE, atualizado_em = CURRENT_TIMESTAMP
             WHERE id = %s
            """,
            (layout_id,),
        )
        conn.commit()
        return {"layout_id": layout_id, "reativado": True}

    nota_coluna = (
        LAYOUT_NOTE_TELEFONICA
        if _is_receptive(colab.get("setor") or "", colab.get("escala") or "")
        else "OPERACIONAL"
    )
    cursor.execute("SELECT COALESCE(MAX(sequencia_bloco), 0) AS max_seq FROM fechamento_layout_operadores")
    max_seq = int(_row_value(cursor.fetchone(), "max_seq", 0) or 0)
    cursor.execute(
        """
        INSERT INTO fechamento_layout_operadores (
            sequencia_bloco, posicao, id_visual, matricula, nome,
            turno_operacao, supervisor, setor, nota_coluna, status_base,
            huawei, weon, colaborador_id, ativo
        ) VALUES (%s, 1, 1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING id
        """,
        (
            max_seq + 1,
            colab.get("matricula") or "",
            colab.get("nome") or "",
            colab.get("escala") or "",
            colab.get("supervisor") or "",
            colab.get("setor") or "",
            nota_coluna,
            str(colab.get("status") or "ATIVO").strip().upper() or "ATIVO",
            colab.get("id_huawei") or "",
            colab.get("id_weon") or "",
            colaborador_id,
        ),
    )
    layout_id = int(_row_value(cursor.fetchone(), "id"))
    conn.commit()
    return {"layout_id": layout_id, "reativado": False}


def remove_fechamento_layout_operador(conn, *, layout_id: int | None = None, colaborador_id: int | None = None) -> None:
    """Remove um operador do fechamento (desativa a linha; nada e apagado).

    - Linha do layout fixo: desativa por `layout_id`.
    - Linha dinamica de complemento do cadastro (sem layout_id): materializa
      uma linha desativada para o colaborador — o NOT EXISTS do complemento
      passa a suprimi-lo nos proximos carregamentos.
    Reverter = adicionar de novo pela tela (reativa a mesma linha).
    """
    cursor = conn.cursor()
    if layout_id:
        cursor.execute(
            """
            UPDATE fechamento_layout_operadores
               SET ativo = FALSE, atualizado_em = CURRENT_TIMESTAMP
             WHERE id = %s
            """,
            (layout_id,),
        )
        conn.commit()
        return

    if not colaborador_id:
        raise ValueError("Informe layout_id ou colaborador_id")

    cursor.execute(
        "SELECT id FROM fechamento_layout_operadores WHERE colaborador_id = %s ORDER BY id LIMIT 1",
        (colaborador_id,),
    )
    existing = cursor.fetchone()
    if existing:
        cursor.execute(
            """
            UPDATE fechamento_layout_operadores
               SET ativo = FALSE, atualizado_em = CURRENT_TIMESTAMP
             WHERE id = %s
            """,
            (int(_row_value(existing, "id")),),
        )
        conn.commit()
        return

    cursor.execute(
        """
        SELECT id, nome, matricula, supervisor, setor, escala, status
        FROM colaboradores WHERE id = %s
        """,
        (colaborador_id,),
    )
    colab_row = cursor.fetchone()
    if not colab_row:
        raise ValueError(f"Colaborador {colaborador_id} nao encontrado")
    colab = dict(colab_row) if not isinstance(colab_row, dict) else colab_row

    cursor.execute("SELECT COALESCE(MAX(sequencia_bloco), 0) AS max_seq FROM fechamento_layout_operadores")
    max_seq = int(_row_value(cursor.fetchone(), "max_seq", 0) or 0)
    cursor.execute(
        """
        INSERT INTO fechamento_layout_operadores (
            sequencia_bloco, posicao, id_visual, matricula, nome,
            turno_operacao, supervisor, setor, nota_coluna, status_base,
            huawei, weon, colaborador_id, ativo
        ) VALUES (%s, 1, 1, %s, %s, %s, %s, %s, 'OPERACIONAL', %s, '', '', %s, FALSE)
        """,
        (
            max_seq + 1,
            colab.get("matricula") or "",
            colab.get("nome") or "",
            colab.get("escala") or "",
            colab.get("supervisor") or "",
            colab.get("setor") or "",
            str(colab.get("status") or "ATIVO").strip().upper() or "ATIVO",
            colaborador_id,
        ),
    )
    conn.commit()


def save_fechamento_overrides(conn, month: int, year: int, rows: List[Dict[str, Any]]):
    cursor = conn.cursor()
    base_rows = {}
    for base_row in get_fechamento_rows(conn, month, year, apply_overrides=False):
        if base_row.get("layout_id"):
            base_rows[("layout", int(base_row["layout_id"]))] = base_row
        elif base_row.get("colab_id"):
            base_rows[("colab", int(base_row["colab_id"]))] = base_row

    for row in rows:
        layout_id = row.get("layout_id")
        colab_id = row.get("colab_id")
        if layout_id:
            base_row = base_rows.get(("layout", int(layout_id)), {})
            sql = """
            INSERT INTO fechamento_layout_overrides (
                layout_id, mes, ano,
                nota_mot, nota_pa, nota_cli, nota_policia,
                matricula_override, nome_override, operacional_override, telefonica_override,
                desempenho_override, status_override, turno_override, supervisor_override,
                setor_override, processo_override, final_override, huawei_override, weon_override
            ) VALUES (
                %(layout_id)s, %(mes)s, %(ano)s,
                %(nota_mot)s, %(nota_pa)s, %(nota_cli)s, %(nota_policia)s,
                %(matricula)s, %(nome)s, %(operacional)s, %(telefonica)s,
                %(desempenho)s, %(status)s, %(turno)s, %(supervisor)s,
                %(setor)s, %(processo)s, %(final)s, %(huawei)s, %(weon)s
            )
            ON CONFLICT (layout_id, mes, ano) DO UPDATE SET
                nota_mot = EXCLUDED.nota_mot,
                nota_pa = EXCLUDED.nota_pa,
                nota_cli = EXCLUDED.nota_cli,
                nota_policia = EXCLUDED.nota_policia,
                matricula_override = EXCLUDED.matricula_override,
                nome_override = EXCLUDED.nome_override,
                operacional_override = EXCLUDED.operacional_override,
                telefonica_override = EXCLUDED.telefonica_override,
                desempenho_override = EXCLUDED.desempenho_override,
                status_override = EXCLUDED.status_override,
                turno_override = EXCLUDED.turno_override,
                supervisor_override = EXCLUDED.supervisor_override,
                setor_override = EXCLUDED.setor_override,
                processo_override = EXCLUDED.processo_override,
                final_override = EXCLUDED.final_override,
                huawei_override = EXCLUDED.huawei_override,
                weon_override = EXCLUDED.weon_override,
                atualizado_em = CURRENT_TIMESTAMP
            """
            data = {
                'layout_id': layout_id,
                'mes': month,
                'ano': year,
                'nota_mot': row.get('nota_mot', 0),
                'nota_pa': row.get('nota_pa', 0),
                'nota_cli': row.get('nota_cli', 0),
                'nota_policia': row.get('nota_policia', 0),
                'matricula': _override_or_none(row.get('matricula'), base_row.get('matricula')),
                'nome': _override_or_none(row.get('nome'), base_row.get('nome')),
                'operacional': _override_or_none(row.get('operacional'), base_row.get('operacional')),
                'telefonica': _override_or_none(row.get('telefonica'), base_row.get('telefonica')),
                'desempenho': _override_or_none(row.get('desempenho'), base_row.get('desempenho')),
                'status': _override_or_none(row.get('status'), base_row.get('status')),
                'turno': _override_or_none(row.get('turno'), base_row.get('turno')),
                # Supervisor e dado cadastral, nao override de fechamento.
                # Alteracao deve acontecer no cadastro do colaborador.
                'supervisor': None,
                'setor': _override_or_none(row.get('setor'), base_row.get('setor')),
                'processo': _override_or_none(row.get('processo'), base_row.get('processo')),
                'final': _override_or_none(row.get('final'), base_row.get('final')),
                'huawei': _override_or_none(row.get('huawei'), base_row.get('huawei')),
                'weon': _override_or_none(row.get('weon'), base_row.get('weon')),
            }
            cursor.execute(sql, data)

            # Coluna ID e estrutural (vale para todos os meses), nao um
            # override mensal: edicao na tela persiste direto no layout.
            try:
                new_id_visual = int(row.get('id'))
            except (TypeError, ValueError):
                new_id_visual = None
            base_id_visual = base_row.get('id')
            if (
                new_id_visual is not None
                and base_id_visual is not None
                and int(base_id_visual) != new_id_visual
            ):
                cursor.execute(
                    """
                    UPDATE fechamento_layout_operadores
                       SET id_visual = %s, atualizado_em = CURRENT_TIMESTAMP
                     WHERE id = %s
                    """,
                    (new_id_visual, layout_id),
                )
            continue

        if not colab_id:
            continue

        base_row = base_rows.get(("colab", int(colab_id)), {})
        sql = """
        INSERT INTO fechamento_cadeia_contatos (
            colaborador_id, mes, ano, 
            nota_mot, nota_pa, nota_cli, nota_policia,
            matricula_override, nome_override, operacional_override, telefonica_override,
            desempenho_override, status_override, turno_override, supervisor_override,
            setor_override, processo_override, final_override, huawei_override, weon_override
        ) VALUES (
            %(colab_id)s, %(mes)s, %(ano)s,
            %(nota_mot)s, %(nota_pa)s, %(nota_cli)s, %(nota_policia)s,
            %(matricula)s, %(nome)s, %(operacional)s, %(telefonica)s,
            %(desempenho)s, %(status)s, %(turno)s, %(supervisor)s,
            %(setor)s, %(processo)s, %(final)s, %(huawei)s, %(weon)s
        )
        ON CONFLICT (colaborador_id, mes, ano) DO UPDATE SET
            nota_mot = EXCLUDED.nota_mot,
            nota_pa = EXCLUDED.nota_pa,
            nota_cli = EXCLUDED.nota_cli,
            nota_policia = EXCLUDED.nota_policia,
            matricula_override = EXCLUDED.matricula_override,
            nome_override = EXCLUDED.nome_override,
            operacional_override = EXCLUDED.operacional_override,
            telefonica_override = EXCLUDED.telefonica_override,
            desempenho_override = EXCLUDED.desempenho_override,
            status_override = EXCLUDED.status_override,
            turno_override = EXCLUDED.turno_override,
            supervisor_override = EXCLUDED.supervisor_override,
            setor_override = EXCLUDED.setor_override,
            processo_override = EXCLUDED.processo_override,
            final_override = EXCLUDED.final_override,
            huawei_override = EXCLUDED.huawei_override,
            weon_override = EXCLUDED.weon_override,
            atualizado_em = CURRENT_TIMESTAMP
        """
        data = {
            'colab_id': colab_id,
            'mes': month,
            'ano': year,
            'nota_mot': row.get('nota_mot', 0),
            'nota_pa': row.get('nota_pa', 0),
            'nota_cli': row.get('nota_cli', 0),
            'nota_policia': row.get('nota_policia', 0),
            'matricula': _override_or_none(row.get('matricula'), base_row.get('matricula')),
            'nome': _override_or_none(row.get('nome'), base_row.get('nome')),
            'operacional': _override_or_none(row.get('operacional'), base_row.get('operacional')),
            'telefonica': _override_or_none(row.get('telefonica'), base_row.get('telefonica')),
            'desempenho': _override_or_none(row.get('desempenho'), base_row.get('desempenho')),
            'status': _override_or_none(row.get('status'), base_row.get('status')),
            'turno': _override_or_none(row.get('turno'), base_row.get('turno')),
            # Supervisor e dado cadastral, nao override de fechamento.
            # Alteracao deve acontecer no cadastro do colaborador.
            'supervisor': None,
            'setor': _override_or_none(row.get('setor'), base_row.get('setor')),
            'processo': _override_or_none(row.get('processo'), base_row.get('processo')),
            'final': _override_or_none(row.get('final'), base_row.get('final')),
            'huawei': _override_or_none(row.get('huawei'), base_row.get('huawei')),
            'weon': _override_or_none(row.get('weon'), base_row.get('weon')),
        }
        cursor.execute(sql, data)
    conn.commit()
