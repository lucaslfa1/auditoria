import os
import sys
import unittest


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.operators import (  # noqa: E402
    buscar_colaborador_por_id_huawei,
    ensure_colaborador_exists,
    get_colaboradores_lookup,
    list_colaboradores,
    resolve_auditable_colaborador,
    upsert_colaborador_telefonia,
)


def _row(**overrides):
    base = {
        "id": 1,
        "nome": "Operador Valido",
        "supervisor": "Supervisor",
        "setor": "LOGISTICA",
        "escala": "LOGISTICA",
        "matricula": "MAT-001",
        "id_huawei": "HUA-001",
        "id_telefonia": "",
        "softphone_number": "",
        "telefonia_account": "",
        "organizacao_telefonia": "LOGISTICA",
        "tipo_agente": "",
        "status": "ATIVO",
        "status_telefonia": "Normal",
        "id_weon": "",
        "auditavel": 1,
    }
    base.update(overrides)
    return base


class FakeCursor:
    def __init__(self, rows=None, fetchone_rows=None):
        self.rows = rows or []
        self.fetchone_rows = list(fetchone_rows or [])
        self.executions = []

    def execute(self, query, params=None):
        self.executions.append((query, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        if self.fetchone_rows:
            return self.fetchone_rows.pop(0)
        return None


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class TestOperatorAuditability(unittest.TestCase):
    def test_resolve_requires_active_auditable_operator_in_same_sector(self):
        cursor = FakeCursor(rows=[
            _row(nome="Operador Fantasma", matricula="MAT-404", auditavel=0),
            _row(nome="Operador Valido", matricula="MAT-001", auditavel=1),
        ])
        conn = FakeConnection(cursor)

        blocked = resolve_auditable_colaborador(lambda: conn, "Operador Fantasma", sector_id="logistica")
        allowed = resolve_auditable_colaborador(lambda: conn, "Operador Valido", sector_id="logistica")

        self.assertIsNone(blocked)
        self.assertIsNotNone(allowed)
        self.assertEqual(allowed["name"], "Operador Valido")
        self.assertIn("COALESCE(auditavel, 1) = 1", cursor.executions[-1][0])

    def test_resolve_matches_operator_id_and_skips_technical_rows(self):
        cursor = FakeCursor(rows=[
            _row(
                id=10,
                nome="CONTENCAO",
                supervisor="",
                matricula="",
                id_huawei="500",
                telefonia_account="contencao",
            ),
            _row(id=11, nome="Ana Souza", matricula="MAT-011", id_huawei="700"),
        ])
        conn = FakeConnection(cursor)

        technical = resolve_auditable_colaborador(lambda: conn, "", operator_id="500", sector_id="logistica")
        valid = resolve_auditable_colaborador(lambda: conn, "", operator_id="700", sector_id="logistica")

        self.assertIsNone(technical)
        self.assertIsNotNone(valid)
        self.assertEqual(valid["name"], "Ana Souza")

    def test_lookup_hides_non_auditable_and_technical_rows(self):
        cursor = FakeCursor(rows=[
            _row(nome="Operador Fantasma", matricula="MAT-404", auditavel=0),
            _row(nome="CONTENCAO", supervisor="", matricula="", telefonia_account="contencao"),
            _row(nome="Operador Tora", escala="Operacao Tora", organizacao_telefonia="Operacao Tora"),
            _row(nome="Operador Valido", matricula="MAT-001", auditavel=1),
        ])
        conn = FakeConnection(cursor)

        operators = get_colaboradores_lookup(lambda: conn, sector_id="logistica", limit=10)

        self.assertEqual([item["name"] for item in operators], ["Operador Valido"])
        self.assertIn("COALESCE(auditavel, 1) = 1", cursor.executions[0][0])

    def test_admin_list_hides_removed_operations(self):
        cursor = FakeCursor(rows=[
            _row(nome="Operador Profarma", escala="Operacao Profarma", organizacao_telefonia="Operacao Profarma"),
            _row(nome="Operador Valido", matricula="MAT-001", auditavel=1),
        ])
        conn = FakeConnection(cursor)

        rows = list_colaboradores(lambda: conn)

        self.assertEqual([item["nome"] for item in rows], ["Operador Valido"])

    def test_ensure_colaborador_exists_does_not_create_unknown_operator(self):
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)

        result = ensure_colaborador_exists(lambda: conn, "Novo Fantasma", "999", "logistica")

        self.assertEqual(result, {"action": "not_found", "reason": "operator_must_exist_in_operadores"})
        self.assertFalse(any("INSERT INTO colaboradores" in query for query, _ in cursor.executions))
        self.assertFalse(conn.committed)

    def test_telefonia_import_creates_new_accounts_inactive_and_not_auditable(self):
        cursor = FakeCursor(rows=[])
        conn = FakeConnection(cursor)

        upsert_colaborador_telefonia(
            lambda: conn,
            nome="Conta Telefonia",
            id_telefonia="999",
            organizacao_telefonia="LOGISTICA",
            status_telefonia="Normal",
        )

        insert_query, insert_params = cursor.executions[-1]
        self.assertIn("INSERT INTO colaboradores", insert_query)
        self.assertEqual(insert_params[5], "INATIVO")
        self.assertEqual(insert_params[6], 0)
        self.assertTrue(conn.committed)

    def test_buscar_colaborador_por_id_huawei_nao_usa_id_telefonia_como_fallback(self):
        cursor = FakeCursor(fetchone_rows=[])
        conn = FakeConnection(cursor)

        result = buscar_colaborador_por_id_huawei(lambda: conn, "999")

        self.assertIsNone(result)
        query, params = cursor.executions[0]
        self.assertIn("id_huawei", query)
        self.assertNotIn("OR id_telefonia", query)
        self.assertEqual(params, ("999",))

    def test_telefonia_import_skips_removed_operations_and_nameless_services(self):
        excluded_cursor = FakeCursor(rows=[])
        excluded_conn = FakeConnection(excluded_cursor)
        upsert_colaborador_telefonia(
            lambda: excluded_conn,
            nome="Operador Tora",
            id_telefonia="800",
            organizacao_telefonia="Operacao Tora",
            status_telefonia="Normal",
        )

        nameless_cursor = FakeCursor(rows=[])
        nameless_conn = FakeConnection(nameless_cursor)
        upsert_colaborador_telefonia(
            lambda: nameless_conn,
            nome="",
            id_telefonia="801",
            telefonia_account="servico.telefonia",
            organizacao_telefonia="LOGISTICA",
            status_telefonia="Normal",
        )

        self.assertFalse(any("INSERT INTO colaboradores" in query for query, _ in excluded_cursor.executions))
        self.assertFalse(any("INSERT INTO colaboradores" in query for query, _ in nameless_cursor.executions))
        self.assertFalse(excluded_conn.committed)
        self.assertFalse(nameless_conn.committed)


if __name__ == "__main__":
    unittest.main()
