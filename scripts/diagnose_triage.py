"""Diagnostico SOMENTE-LEITURA da fila de triagem.

Investiga:
1) Items presos em needs_manual_triage agrupados por motivos_revisao
2) Caso especifico: Nicolas Gabriel Martins Furtado (operador sem cadastro)
3) Caso especifico: Camila Lamin / matricula 11208 (cadastrada mas nao-identificada)
4) Mismatches de id_huawei entre colaboradores e metadata da fila

Uso: python scripts/diagnose_triage.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import database  # noqa: E402


def _section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def _print_row(row: dict) -> None:
    print(json.dumps(row, ensure_ascii=False, default=str, indent=2))


def listar_needs_manual_triage(cur) -> list[dict]:
    cur.execute(
        """
        SELECT
            id,
            nome_arquivo,
            status,
            COALESCE(setor_previsto, '') AS setor_previsto,
            COALESCE(alerta_previsto, '') AS alerta_previsto,
            COALESCE(operador_previsto, '') AS operador_previsto,
            confianca,
            motivos_json,
            metadata_json::jsonb ->> 'origem' AS origem,
            metadata_json::jsonb ->> 'operator_id_huawei_real' AS oid_real,
            metadata_json::jsonb ->> 'huawei_agent_id' AS huawei_agent_id,
            metadata_json::jsonb ->> 'huawei_work_no' AS huawei_work_no,
            metadata_json::jsonb ->> 'is_oficial' AS is_oficial_meta,
            metadata_json::jsonb ->> 'classification_status' AS classification_status,
            criado_em,
            atualizado_em
        FROM fila_revisao_classificacao
        WHERE status IN ('needs_manual_triage', 'blocked_operator')
        ORDER BY atualizado_em DESC, id DESC
        """
    )
    rows = []
    for r in cur.fetchall():
        motivos = []
        try:
            motivos = json.loads(r["motivos_json"] or "[]")
        except Exception:
            motivos = []
        rows.append(dict(r) | {"motivos_revisao": motivos})
    return rows


def buscar_por_nome(cur, padrao: str) -> list[dict]:
    cur.execute(
        """
        SELECT
            f.id,
            f.nome_arquivo,
            f.status,
            COALESCE(f.setor_previsto, '') AS setor_previsto,
            COALESCE(f.alerta_previsto, '') AS alerta_previsto,
            COALESCE(f.operador_previsto, '') AS operador_previsto,
            f.confianca,
            f.motivos_json,
            f.metadata_json::jsonb ->> 'origem' AS origem,
            f.metadata_json::jsonb ->> 'operator_id_huawei_real' AS oid_real,
            f.metadata_json::jsonb ->> 'huawei_agent_id' AS huawei_agent_id,
            f.metadata_json::jsonb ->> 'huawei_work_no' AS huawei_work_no,
            f.metadata_json::jsonb ->> 'operator_id' AS operator_id_meta,
            f.metadata_json::jsonb ->> 'id_huawei' AS id_huawei_meta,
            f.metadata_json::jsonb ->> 'operator_name' AS operator_name_meta,
            f.metadata_json::jsonb ->> 'huawei_operator_name' AS huawei_operator_name_meta,
            f.metadata_json::jsonb ->> 'classification_status' AS classification_status,
            f.atualizado_em
        FROM fila_revisao_classificacao f
        WHERE LOWER(COALESCE(f.operador_previsto, '')) LIKE %s
           OR LOWER(COALESCE(f.nome_arquivo, '')) LIKE %s
           OR LOWER(COALESCE(f.metadata_json::jsonb ->> 'operator_name', '')) LIKE %s
        ORDER BY f.atualizado_em DESC, f.id DESC
        LIMIT 10
        """,
        (f"%{padrao.lower()}%", f"%{padrao.lower()}%", f"%{padrao.lower()}%"),
    )
    out = []
    for r in cur.fetchall():
        motivos = []
        try:
            motivos = json.loads(r["motivos_json"] or "[]")
        except Exception:
            motivos = []
        out.append(dict(r) | {"motivos_revisao": motivos})
    return out


def buscar_colaborador(cur, *, nome: str | None = None, matricula: str | None = None) -> list[dict]:
    clauses = []
    params: list = []
    if matricula:
        clauses.append("matricula = %s")
        params.append(str(matricula))
    if nome:
        clauses.append("LOWER(nome) LIKE %s")
        params.append(f"%{nome.lower()}%")
    if not clauses:
        return []
    where = " OR ".join(clauses)
    cur.execute(
        f"""
        SELECT id, nome, matricula, status, COALESCE(auditavel, 1) AS auditavel,
               id_huawei, setor, escala
        FROM colaboradores
        WHERE {where}
        ORDER BY nome
        LIMIT 20
        """,
        params,
    )
    return [dict(r) for r in cur.fetchall()]


def main() -> None:
    conn = database.get_connection()
    try:
        cur = conn.cursor()

        _section("1) Items presos em needs_manual_triage / blocked_operator")
        presos = listar_needs_manual_triage(cur)
        print(f"Total: {len(presos)} items")
        contador_motivos: Counter[str] = Counter()
        contador_origem: Counter[str] = Counter()
        contador_status: Counter[str] = Counter()
        for item in presos:
            for m in item["motivos_revisao"]:
                contador_motivos[str(m)] += 1
            contador_origem[str(item.get("origem") or "(sem origem)")] += 1
            contador_status[str(item.get("status"))] += 1
        print("\nMotivos por contagem:")
        for motivo, qtd in contador_motivos.most_common():
            print(f"  {qtd:4d}  {motivo}")
        print("\nOrigem por contagem:")
        for origem, qtd in contador_origem.most_common():
            print(f"  {qtd:4d}  {origem}")
        print("\nStatus por contagem:")
        for status, qtd in contador_status.most_common():
            print(f"  {qtd:4d}  {status}")

        print("\nUltimos 5 items (detalhe):")
        for item in presos[:5]:
            _print_row(item)

        _section("2) Caso Nicolas Gabriel (operador sem cadastro)")
        nicolas_fila = buscar_por_nome(cur, "nicolas")
        print(f"Items na fila: {len(nicolas_fila)}")
        for item in nicolas_fila:
            _print_row(item)
        nicolas_colab = buscar_colaborador(cur, nome="nicolas")
        print(f"\nColaboradores com 'nicolas' no nome: {len(nicolas_colab)}")
        for c in nicolas_colab:
            _print_row(c)

        _section("3) Caso Camila Lamin (matricula 11208, Distribuicao)")
        camila_fila = buscar_por_nome(cur, "camila lamin")
        print(f"Items na fila: {len(camila_fila)}")
        for item in camila_fila:
            _print_row(item)
        camila_colab = buscar_colaborador(cur, nome="camila lamin", matricula="11208")
        print(f"\nColaboradores 'camila lamin' OR matricula='11208': {len(camila_colab)}")
        for c in camila_colab:
            _print_row(c)

        _section("4a) Items 'audited' SEM colaborador oficial (auditoria suspeita)")
        cur.execute(
            """
            WITH audited AS (
                SELECT
                    f.id,
                    f.nome_arquivo,
                    f.operador_previsto,
                    f.setor_previsto,
                    f.alerta_previsto,
                    f.confianca,
                    f.motivos_json,
                    f.status,
                    f.atualizado_em,
                    COALESCE(
                        NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id_huawei_real'), ''),
                        NULLIF(TRIM(f.metadata_json::jsonb ->> 'id_huawei'), ''),
                        NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id'), ''),
                        NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_work_no'), ''),
                        NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_agent_id'), '')
                    ) AS huawei_id_na_fila,
                    f.metadata_json::jsonb ->> 'origem' AS origem
                FROM fila_revisao_classificacao f
                WHERE f.status = 'audited'
                  AND f.metadata_json::jsonb ->> 'origem' = 'huawei_sync'
            )
            SELECT a.*,
                   (SELECT c.nome FROM colaboradores c
                     WHERE c.status='ATIVO' AND COALESCE(c.auditavel,1)=1
                       AND TRIM(c.id_huawei) = TRIM(a.huawei_id_na_fila)
                     LIMIT 1) AS colab_oficial_match
            FROM audited a
            WHERE NOT EXISTS (
                SELECT 1 FROM colaboradores c
                 WHERE c.status='ATIVO' AND COALESCE(c.auditavel,1)=1
                   AND TRIM(c.id_huawei) = TRIM(a.huawei_id_na_fila)
            )
            ORDER BY a.atualizado_em DESC
            LIMIT 25
            """
        )
        audited_sem_match = cur.fetchall()
        print(f"Total audited sem colaborador oficial: {len(audited_sem_match)}")
        for r in audited_sem_match[:10]:
            _print_row(dict(r))

        _section("4b) Distribuicao geral de status na fila")
        cur.execute(
            """
            SELECT status, COUNT(*) AS qtd
            FROM fila_revisao_classificacao
            GROUP BY status
            ORDER BY qtd DESC
            """
        )
        for r in cur.fetchall():
            print(f"  {r['qtd']:5d}  {r['status']}")

        _section("0) Audit log de colaboradores nas ultimas 48h (forensics)")
        cur.execute(
            """
            SELECT acao, entity_id, alterado_em, alterado_por, origem, motivo,
                   payload_antes::jsonb -> 'nome' AS nome_antes,
                   payload_antes::jsonb -> 'id_huawei' AS idh_antes,
                   payload_antes::jsonb -> 'status' AS status_antes,
                   payload_antes::jsonb -> 'auditavel' AS auditavel_antes,
                   payload_depois::jsonb -> 'nome' AS nome_depois,
                   payload_depois::jsonb -> 'id_huawei' AS idh_depois,
                   payload_depois::jsonb -> 'status' AS status_depois,
                   payload_depois::jsonb -> 'auditavel' AS auditavel_depois
            FROM colaboradores_audit_log
            WHERE alterado_em > NOW() - INTERVAL '48 hours'
            ORDER BY alterado_em DESC
            LIMIT 200
            """
        )
        log_rows = cur.fetchall()
        print(f"Total mudancas em 48h: {len(log_rows)}")

        por_origem: Counter[str] = Counter()
        por_acao: Counter[str] = Counter()
        por_user: Counter[str] = Counter()
        for r in log_rows:
            por_origem[str(r.get("origem") or "(sem origem)")] += 1
            por_acao[str(r.get("acao") or "?")] += 1
            por_user[str(r.get("alterado_por") or "(anonimo)")] += 1
        print("\nPor origem:")
        for k, v in por_origem.most_common():
            print(f"  {v:4d}  {k}")
        print("\nPor acao:")
        for k, v in por_acao.most_common():
            print(f"  {v:4d}  {k}")
        print("\nPor alterado_por:")
        for k, v in por_user.most_common():
            print(f"  {v:4d}  {k}")
        print("\nUltimas 30 mudancas:")
        for r in log_rows[:30]:
            _print_row(dict(r))

        _section("5) Detalhe completo de cada duplicata de id_huawei")
        cur.execute(
            """
            WITH dup_ids AS (
                SELECT id_huawei
                FROM colaboradores
                WHERE status = 'ATIVO'
                  AND COALESCE(auditavel, 1) = 1
                  AND COALESCE(NULLIF(TRIM(id_huawei), ''), '') <> ''
                GROUP BY id_huawei
                HAVING COUNT(*) > 1
            )
            SELECT c.id, c.id_huawei, c.nome, c.matricula, c.setor, c.escala, c.status, c.auditavel
            FROM colaboradores c
            INNER JOIN dup_ids d ON d.id_huawei = c.id_huawei
            WHERE c.status = 'ATIVO'
              AND COALESCE(c.auditavel, 1) = 1
            ORDER BY c.id_huawei, c.nome, c.id
            """
        )
        for r in cur.fetchall():
            _print_row(dict(r))

        _section("4i) TODOS os items huawei com is_oficial=false (calculo da LATERAL JOIN)")
        cur.execute(
            """
            SELECT f.id, f.nome_arquivo, f.status, f.operador_previsto,
                   f.metadata_json::jsonb ->> 'operator_id_huawei_real' AS oid_real,
                   f.metadata_json::jsonb ->> 'huawei_work_no' AS work_no,
                   f.atualizado_em
            FROM fila_revisao_classificacao f
            LEFT JOIN LATERAL (
                SELECT c.id_huawei
                FROM colaboradores c
                WHERE c.status = 'ATIVO'
                  AND COALESCE(c.auditavel, 1) = 1
                  AND COALESCE(NULLIF(TRIM(c.id_huawei), ''), '') <> ''
                  AND TRIM(c.id_huawei) = COALESCE(
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id_huawei_real'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'id_huawei'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_work_no'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_agent_id'), '')
                  )
                LIMIT 1
            ) official ON TRUE
            WHERE COALESCE(f.metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
              AND official.id_huawei IS NULL
            ORDER BY f.atualizado_em DESC
            """
        )
        nao_oficiais = cur.fetchall()
        print(f"Total Huawei items com is_oficial=FALSE: {len(nao_oficiais)}")
        for r in nao_oficiais[:20]:
            _print_row(dict(r))

        _section("4j) TODOS os items com 'nicolas' no nome do arquivo (qualquer status)")
        cur.execute(
            """
            SELECT id, nome_arquivo, status, operador_previsto,
                   metadata_json::jsonb ->> 'operator_id_huawei_real' AS oid_real,
                   atualizado_em
            FROM fila_revisao_classificacao
            WHERE LOWER(nome_arquivo) LIKE '%nicolas%'
               OR LOWER(COALESCE(operador_previsto, '')) LIKE '%nicolas%'
            ORDER BY atualizado_em DESC
            """
        )
        for r in cur.fetchall():
            _print_row(dict(r))

        _section("4g) Configuracoes huawei_auto_audit / thresholds")
        cur.execute(
            """
            SELECT chave, valor
            FROM configuracoes
            WHERE chave LIKE 'huawei_%' OR chave LIKE '%threshold%' OR chave LIKE '%confidence%'
            ORDER BY chave
            """
        )
        for r in cur.fetchall():
            _print_row(dict(r))

        _section("4h) Todos os 14 pendentes: alerta, confianca, motivos resumidos")
        cur.execute(
            """
            SELECT id, nome_arquivo, status,
                   COALESCE(operador_previsto, '') AS operador,
                   COALESCE(setor_previsto, '') AS setor,
                   COALESCE(alerta_previsto, '') AS alerta,
                   confianca,
                   motivos_json,
                   metadata_json::jsonb ->> 'is_oficial' AS is_oficial_meta,
                   metadata_json::jsonb ->> 'classification_status' AS class_status,
                   atualizado_em
            FROM fila_revisao_classificacao
            WHERE status IN ('pending', 'needs_manual_triage', 'blocked_operator')
            ORDER BY atualizado_em DESC
            """
        )
        for r in cur.fetchall():
            _print_row(dict(r))

        _section("4e) id_huawei duplicados em colaboradores (ATIVO + auditavel)")
        cur.execute(
            """
            SELECT id_huawei, COUNT(*) AS qtd,
                   string_agg(nome, ' | ' ORDER BY nome) AS nomes,
                   string_agg(matricula, ', ' ORDER BY nome) AS matriculas,
                   string_agg(setor, ', ' ORDER BY nome) AS setores
            FROM colaboradores
            WHERE status = 'ATIVO'
              AND COALESCE(auditavel, 1) = 1
              AND COALESCE(NULLIF(TRIM(id_huawei), ''), '') <> ''
            GROUP BY id_huawei
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, id_huawei
            """
        )
        dups = cur.fetchall()
        print(f"Total de id_huawei duplicados: {len(dups)}")
        for r in dups:
            _print_row(dict(r))

        _section("4f) Items audited com motivos contraditorios (ex: direction_mismatch + auditada_instantaneamente)")
        cur.execute(
            """
            SELECT id, nome_arquivo, status, motivos_json, confianca,
                   atualizado_em
            FROM fila_revisao_classificacao
            WHERE status = 'audited'
              AND motivos_json::jsonb @> '["direction_mismatch"]'
            ORDER BY atualizado_em DESC
            LIMIT 10
            """
        )
        suspeitos = cur.fetchall()
        print(f"Total audited com direction_mismatch: {len(suspeitos)}")
        for r in suspeitos:
            _print_row(dict(r))

        _section("4d) Reproduzir LATERAL JOIN exato (is_oficial) para Nicolas e Camila")
        cur.execute(
            """
            SELECT
                f.id,
                f.nome_arquivo,
                f.status,
                f.metadata_json::jsonb ->> 'operator_id_huawei_real' AS oid_real,
                f.metadata_json::jsonb ->> 'huawei_work_no' AS work_no,
                f.metadata_json::jsonb ->> 'origem' AS origem,
                official_by_huawei.nome AS official_name,
                official_by_huawei.id_huawei AS official_id,
                CASE
                    WHEN COALESCE(f.metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
                        THEN official_by_huawei.id_huawei IS NOT NULL
                    ELSE EXISTS(SELECT 1
                                  FROM colaboradores c
                                  WHERE LOWER(TRIM(c.nome)) = LOWER(TRIM(COALESCE(NULLIF(f.operador_previsto, ''), f.metadata_json::jsonb ->> 'operator_name')))
                                     AND c.status = 'ATIVO'
                                )
                END as is_oficial
            FROM fila_revisao_classificacao f
            LEFT JOIN LATERAL (
                SELECT c.nome, c.id_huawei
                FROM colaboradores c
                WHERE c.status = 'ATIVO'
                  AND COALESCE(c.auditavel, 1) = 1
                  AND COALESCE(NULLIF(TRIM(c.id_huawei), ''), '') <> ''
                  AND TRIM(c.id_huawei) = COALESCE(
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id_huawei_real'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'id_huawei'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_work_no'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_agent_id'), '')
                  )
                ORDER BY c.nome
                LIMIT 1
            ) official_by_huawei ON TRUE
            WHERE f.id IN (2021, 2207, 2202)
            ORDER BY f.id
            """
        )
        for r in cur.fetchall():
            _print_row(dict(r))

        _section("4c) Mismatch id_huawei (colaboradores vs metadata da fila)")
        cur.execute(
            """
            WITH fila AS (
                SELECT
                    f.id,
                    f.nome_arquivo,
                    COALESCE(
                        NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id_huawei_real'), ''),
                        NULLIF(TRIM(f.metadata_json::jsonb ->> 'id_huawei'), ''),
                        NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id'), ''),
                        NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_work_no'), ''),
                        NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_agent_id'), '')
                    ) AS huawei_id_na_fila,
                    f.metadata_json::jsonb ->> 'operator_name' AS operator_name,
                    f.status,
                    f.atualizado_em
                FROM fila_revisao_classificacao f
                WHERE f.metadata_json::jsonb ->> 'origem' = 'huawei_sync'
                  AND f.status IN ('pending', 'needs_manual_triage', 'blocked_operator')
            )
            SELECT
                fila.id,
                fila.nome_arquivo,
                fila.operator_name,
                fila.huawei_id_na_fila,
                fila.status,
                fila.atualizado_em,
                (SELECT c.nome FROM colaboradores c
                  WHERE c.status='ATIVO' AND COALESCE(c.auditavel,1)=1
                    AND TRIM(c.id_huawei) = TRIM(fila.huawei_id_na_fila)
                  LIMIT 1) AS bate_exato,
                (SELECT c.nome FROM colaboradores c
                  WHERE c.status='ATIVO' AND COALESCE(c.auditavel,1)=1
                    AND LTRIM(TRIM(c.id_huawei),'0') = LTRIM(TRIM(fila.huawei_id_na_fila),'0')
                    AND TRIM(c.id_huawei) <> TRIM(fila.huawei_id_na_fila)
                  LIMIT 1) AS bate_sem_zero
            FROM fila
            ORDER BY fila.atualizado_em DESC
            LIMIT 25
            """
        )
        for r in cur.fetchall():
            _print_row(dict(r))

    finally:
        conn.close()


if __name__ == "__main__":
    main()
