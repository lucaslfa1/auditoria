import os
import sys
import unittest
import uuid


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestDashboardSectorFilters(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_dashboard_sector_{uuid.uuid4().hex}.db",
        )
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

        conn = database.get_connection()
        cursor = conn.cursor()

        ligacoes = [
            ("call-bas.wav", "calls/call-bas.wav", "hash-bas", "grupo", "sub", "bas", "alerta-a", "boa"),
            ("call-log.wav", "calls/call-log.wav", "hash-log", "grupo", "sub", "logistica", "alerta-b", "ruim"),
        ]
        for index, (nome, caminho, hash_arquivo, grupo, subgrupo, setor, alerta, qualidade) in enumerate(ligacoes, start=1):
            cursor.execute(
                """
                INSERT INTO ligacoes_auditadas (
                    nome_arquivo, caminho_relativo, hash_arquivo, grupo, subgrupo,
                    setor_referencia, alerta_referencia, qualidade_referencia,
                    observacao, criado_em, atualizado_em
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '', %s, %s)
                """,
                (
                    nome,
                    caminho,
                    hash_arquivo,
                    grupo,
                    subgrupo,
                    setor,
                    alerta,
                    qualidade,
                    f"2026-03-05T10:0{index}:00",
                    f"2026-03-05T10:0{index}:00",
                ),
            )

        classificacoes = [
            (1, "bas", "alerta-a", 0.95, "Operador A", 1, 1),
            (2, "logistica", "alerta-b", 0.70, "Operador B", 0, 0),
        ]
        for ligacao_id, setor_previsto, alerta_previsto, confianca, operador_previsto, acertou_setor, acertou_alerta in classificacoes:
            cursor.execute(
                """
                INSERT INTO resultados_classificacao (
                    ligacao_id, setor_previsto, alerta_previsto, confianca,
                    operador_previsto, modelo, versao_prompt,
                    acertou_setor, acertou_alerta, erro, metadata_json, executado_em
                ) VALUES (%s, %s, %s, %s, %s, 'modelo-teste', 'v1', %s, %s, NULL, '{}', '2026-03-05T10:30:00')
                """,
                (
                    ligacao_id,
                    setor_previsto,
                    alerta_previsto,
                    confianca,
                    operador_previsto,
                    acertou_setor,
                    acertou_alerta,
                ),
            )

        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_resumo_ligacoes_can_be_filtered_by_sector(self):
        resumo = database.get_resumo_ligacoes_auditadas("bas")

        self.assertEqual(resumo["total_ligacoes"], 1)
        self.assertEqual(resumo["classificadas"], 1)
        self.assertEqual(resumo["qualidade"]["boa"], 1)
        self.assertEqual(resumo["qualidade"]["ruim"], 0)
        self.assertEqual(resumo["por_setor"], [{"setor": "bas", "total": 1}])
        self.assertEqual(resumo["taxa_acerto_setor"], 100.0)
        self.assertEqual(resumo["taxa_acerto_alerta"], 100.0)

    def test_listar_ligacoes_auditadas_can_filter_by_sector(self):
        ligacoes = database.listar_ligacoes_auditadas(limit=10, setor="bas")

        self.assertEqual(len(ligacoes), 1)
        self.assertEqual(ligacoes[0]["setor_referencia"], "bas")
        self.assertEqual(ligacoes[0]["classificacao"]["setor_previsto"], "bas")


if __name__ == "__main__":
    unittest.main()
