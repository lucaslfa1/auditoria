"""Dataset de benchmark de classificação (ground truth) — gabarito humano.

Tabelas: `ligacoes_auditadas` (ligações com setor/alerta/qualidade de
referência definidos por humano), `resultados_classificacao` (o que a IA
previu para cada ligação + flags de acerto) e `resultados_auditoria`
(histórico de notas do dataset, separado da tabela `audits` do fluxo
principal). Serve para medir a taxa de acerto de setor/alerta da IA contra o
gabarito.

Extraído de `repositories/classification_review.py` (v1.3.141) sem mudança de
comportamento; os nomes continuam reexportados de
`repositories.classification_review` (e, por consequência, da fachada
`db.database`) para compatibilidade total com callers e testes.

Todas as funções públicas recebem `get_connection` (factory) e gerenciam a
própria conexão/transação. Sem custo de API (apenas acesso a banco).
"""

import json
from datetime import datetime
from typing import Callable, Optional, Any

from repositories.common import (
    extract_returning_id,
    normalize_quality_reference,
    normalize_sector_id as _normalize_sector_id,
)


ConnectionFactory = Callable[[], Any]


def upsert_ligacao_auditada(
    get_connection: ConnectionFactory,
    nome_arquivo: str,
    caminho_relativo: str,
    hash_arquivo: str,
    grupo: Optional[str] = None,
    subgrupo: Optional[str] = None,
    setor_referencia: Optional[str] = None,
    alerta_referencia: Optional[str] = None,
    qualidade_referencia: Optional[str] = None,
    observacao: Optional[str] = None,
) -> int:
    """Insere/atualiza uma ligação no dataset de ground truth (`ligacoes_auditadas`).

    Dedupe por `hash_arquivo` (ON CONFLICT atualiza os campos de referência).
    `setor_referencia`/`alerta_referencia`/`qualidade_referencia` são o gabarito
    humano contra o qual `resultados_classificacao` mede o acerto da IA.

    Retorna o id da linha (existente ou recém-criada). Efeito: UPSERT + commit.
    """
    if not nome_arquivo or not caminho_relativo or not hash_arquivo:
        raise ValueError("nome_arquivo, caminho_relativo e hash_arquivo são obrigatórios")

    now = datetime.now().isoformat()
    qualidade_normalizada = normalize_quality_reference(qualidade_referencia)
    setor_normalizado = _normalize_sector_id(setor_referencia)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ligacoes_auditadas (
                nome_arquivo, caminho_relativo, hash_arquivo,
                grupo, subgrupo, setor_referencia, alerta_referencia,
                qualidade_referencia, observacao, criado_em, atualizado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(hash_arquivo) DO UPDATE SET
                nome_arquivo = excluded.nome_arquivo,
                caminho_relativo = excluded.caminho_relativo,
                grupo = excluded.grupo,
                subgrupo = excluded.subgrupo,
                setor_referencia = excluded.setor_referencia,
                alerta_referencia = excluded.alerta_referencia,
                qualidade_referencia = excluded.qualidade_referencia,
                observacao = excluded.observacao,
                atualizado_em = excluded.atualizado_em
            """,
            (
                nome_arquivo,
                caminho_relativo,
                hash_arquivo,
                grupo,
                subgrupo,
                setor_normalizado,
                alerta_referencia,
                qualidade_normalizada,
                observacao or "",
                now,
                now,
            ),
        )
        cursor.execute("SELECT id FROM ligacoes_auditadas WHERE hash_arquivo = %s", (hash_arquivo,))
        ligacao_id = cursor.fetchone()[0]
        conn.commit()
        return int(ligacao_id)
    finally:
        conn.close()


def get_ligacao_auditada_por_hash(get_connection: ConnectionFactory, hash_arquivo: str) -> Optional[dict]:
    """Busca uma ligação do dataset de ground truth pelo hash do arquivo; None se ausente."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ligacoes_auditadas WHERE hash_arquivo = %s", (hash_arquivo,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "nome_arquivo": row["nome_arquivo"],
            "caminho_relativo": row["caminho_relativo"],
            "hash_arquivo": row["hash_arquivo"],
            "grupo": row["grupo"],
            "subgrupo": row["subgrupo"],
            "setor_referencia": row["setor_referencia"],
            "alerta_referencia": row["alerta_referencia"],
            "qualidade_referencia": row["qualidade_referencia"],
            "observacao": row["observacao"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
        }
    finally:
        conn.close()


def registrar_resultado_classificacao(
    get_connection: ConnectionFactory,
    ligacao_id: int,
    setor_previsto: Optional[str] = None,
    alerta_previsto: Optional[str] = None,
    confianca: Optional[float] = None,
    operador_previsto: Optional[str] = None,
    modelo: Optional[str] = None,
    versao_prompt: Optional[str] = None,
    acertou_setor: Optional[bool] = None,
    acertou_alerta: Optional[bool] = None,
    erro: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> int:
    """Registra uma execução de classificação contra o gabarito (`resultados_classificacao`).

    Persiste o que a IA previu (setor/alerta/operador, confiança, modelo e
    versão do prompt) e, quando o caller já comparou com o gabarito, os flags
    `acertou_setor`/`acertou_alerta` (gravados como 0/1; None = sem comparação).

    Retorna o id do registro criado. Efeito: INSERT + commit.
    """
    now = datetime.now().isoformat()
    setor_previsto_normalizado = _normalize_sector_id(setor_previsto)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO resultados_classificacao (
                ligacao_id, setor_previsto, alerta_previsto, confianca,
                operador_previsto, modelo, versao_prompt,
                acertou_setor, acertou_alerta, erro, metadata_json, executado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                ligacao_id,
                setor_previsto_normalizado,
                alerta_previsto,
                confianca,
                operador_previsto,
                modelo,
                versao_prompt,
                None if acertou_setor is None else int(acertou_setor),
                None if acertou_alerta is None else int(acertou_alerta),
                erro,
                json.dumps(metadata or {}, ensure_ascii=False),
                now,
            ),
        )
        resultado_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        return int(resultado_id)
    finally:
        conn.close()


def registrar_resultado_auditoria(
    get_connection: ConnectionFactory,
    ligacao_id: int,
    nota: Optional[float] = None,
    nota_maxima: Optional[float] = None,
    resumo: Optional[str] = None,
    detalhes: Optional[list[dict]] = None,
) -> int:
    """Insere um resultado de auditoria em `resultados_auditoria` e retorna o id.

    Histórico do dataset `ligacoes_auditadas` (importação/benchmark), separado
    da tabela `audits` do fluxo principal.
    """
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO resultados_auditoria (
                ligacao_id, nota, nota_maxima, resumo, detalhes_json, executado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (ligacao_id, nota, nota_maxima, resumo, json.dumps(detalhes or [], ensure_ascii=False), now),
        )
        resultado_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        return int(resultado_id)
    finally:
        conn.close()


def get_resumo_ligacoes_auditadas(get_connection: ConnectionFactory, setor: Optional[str] = None) -> dict:
    """Agrega contadores de `ligacoes_auditadas` (total, por qualidade e por setor)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        setor_normalizado = _normalize_sector_id(setor)

        filtros: list[str] = []
        params: list = []
        if setor_normalizado:
            filtros.append("setor_referencia = %s")
            params.append(setor_normalizado)
        where_clause = f"WHERE {' AND '.join(filtros)}" if filtros else ""

        cursor.execute(f"SELECT COUNT(*) AS total FROM ligacoes_auditadas {where_clause}", params)
        total_ligacoes = int(cursor.fetchone()["total"] or 0)

        qualidade = {"boa": 0, "ruim": 0, "zerada": 0, "indefinida": 0}
        cursor.execute(
            f"""
            SELECT qualidade_referencia, COUNT(*) AS total
            FROM ligacoes_auditadas
            {where_clause}
            GROUP BY qualidade_referencia
            """,
            params,
        )
        for row in cursor.fetchall():
            chave = row["qualidade_referencia"] or "indefinida"
            qualidade[chave] = int(row["total"] or 0)

        cursor.execute(
            f"""
            SELECT COALESCE(setor_referencia, 'indefinido') AS setor, COUNT(*) AS total
            FROM ligacoes_auditadas
            {where_clause}
            GROUP BY COALESCE(setor_referencia, 'indefinido')
            ORDER BY total DESC
            """,
            params,
        )
        por_setor = [{"setor": row["setor"], "total": int(row["total"] or 0)} for row in cursor.fetchall()]

        if setor_normalizado:
            cursor.execute(
                """
                SELECT COUNT(DISTINCT rc.ligacao_id) AS total
                FROM resultados_classificacao rc
                INNER JOIN ligacoes_auditadas la ON la.id = rc.ligacao_id
                WHERE la.setor_referencia = %s
                """,
                (setor_normalizado,),
            )
        else:
            cursor.execute("SELECT COUNT(DISTINCT ligacao_id) AS total FROM resultados_classificacao")
        classificadas = int(cursor.fetchone()["total"] or 0)

        if setor_normalizado:
            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN rc.acertou_setor = 1 THEN 1 ELSE 0 END) AS acertos_setor,
                    SUM(CASE WHEN rc.acertou_alerta = 1 THEN 1 ELSE 0 END) AS acertos_alerta,
                    COUNT(CASE WHEN rc.acertou_setor IS NOT NULL THEN 1 END) AS total_comparacao_setor,
                    COUNT(CASE WHEN rc.acertou_alerta IS NOT NULL THEN 1 END) AS total_comparacao_alerta
                FROM resultados_classificacao rc
                INNER JOIN ligacoes_auditadas la ON la.id = rc.ligacao_id
                WHERE la.setor_referencia = %s
                """,
                (setor_normalizado,),
            )
        else:
            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN acertou_setor = 1 THEN 1 ELSE 0 END) AS acertos_setor,
                    SUM(CASE WHEN acertou_alerta = 1 THEN 1 ELSE 0 END) AS acertos_alerta,
                    COUNT(CASE WHEN acertou_setor IS NOT NULL THEN 1 END) AS total_comparacao_setor,
                    COUNT(CASE WHEN acertou_alerta IS NOT NULL THEN 1 END) AS total_comparacao_alerta
                FROM resultados_classificacao
                """
            )
        metricas = cursor.fetchone()
        total_comp_setor = int(metricas["total_comparacao_setor"] or 0)
        total_comp_alerta = int(metricas["total_comparacao_alerta"] or 0)
        taxa_acerto_setor = round((int(metricas["acertos_setor"] or 0) / total_comp_setor) * 100, 2) if total_comp_setor else None
        taxa_acerto_alerta = round((int(metricas["acertos_alerta"] or 0) / total_comp_alerta) * 100, 2) if total_comp_alerta else None
    finally:
        conn.close()

    return {
        "total_ligacoes": total_ligacoes,
        "classificadas": classificadas,
        "qualidade": qualidade,
        "por_setor": por_setor,
        "taxa_acerto_setor": taxa_acerto_setor,
        "taxa_acerto_alerta": taxa_acerto_alerta,
    }


def listar_ligacoes_auditadas(
    get_connection: ConnectionFactory,
    limit: int = 100,
    qualidade: Optional[str] = None,
    setor: Optional[str] = None,
) -> list[dict]:
    """Lista o dataset `ligacoes_auditadas` com filtros de qualidade/setor (cap 500)."""
    limite = max(1, min(int(limit), 500))
    qualidade_normalizada = normalize_quality_reference(qualidade) if qualidade else None
    setor_normalizado = _normalize_sector_id(setor)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        filtros = []
        params: list = []
        if qualidade_normalizada and qualidade_normalizada != "indefinida":
            filtros.append("la.qualidade_referencia = %s")
            params.append(qualidade_normalizada)
        if setor_normalizado:
            filtros.append("la.setor_referencia = %s")
            params.append(setor_normalizado)
        where_clause = f"WHERE {' AND '.join(filtros)}" if filtros else ""

        query = f"""
            SELECT
                la.id, la.nome_arquivo, la.caminho_relativo, la.hash_arquivo, la.grupo, la.subgrupo,
                la.setor_referencia, la.alerta_referencia, la.qualidade_referencia, la.observacao,
                la.criado_em, la.atualizado_em,
                rc.setor_previsto, rc.alerta_previsto, rc.confianca, rc.operador_previsto,
                rc.acertou_setor, rc.acertou_alerta, rc.erro, rc.executado_em AS classificacao_em
            FROM ligacoes_auditadas la
            LEFT JOIN resultados_classificacao rc
                ON rc.id = (
                    SELECT id FROM resultados_classificacao sub
                    WHERE sub.ligacao_id = la.id
                    ORDER BY sub.id DESC
                    LIMIT 1
                )
            {where_clause}
            ORDER BY la.id DESC
            LIMIT %s
        """
        params.append(limite)
        cursor.execute(query, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    return [
        {
            "id": row["id"],
            "nome_arquivo": row["nome_arquivo"],
            "caminho_relativo": row["caminho_relativo"],
            "hash_arquivo": row["hash_arquivo"],
            "grupo": row["grupo"],
            "subgrupo": row["subgrupo"],
            "setor_referencia": row["setor_referencia"],
            "alerta_referencia": row["alerta_referencia"],
            "qualidade_referencia": row["qualidade_referencia"],
            "observacao": row["observacao"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
            "classificacao": {
                "setor_previsto": row["setor_previsto"],
                "alerta_previsto": row["alerta_previsto"],
                "confianca": row["confianca"],
                "operador_previsto": row["operador_previsto"],
                "acertou_setor": None if row["acertou_setor"] is None else bool(row["acertou_setor"]),
                "acertou_alerta": None if row["acertou_alerta"] is None else bool(row["acertou_alerta"]),
                "erro": row["erro"],
                "executado_em": row["classificacao_em"],
            },
        }
        for row in rows
    ]
