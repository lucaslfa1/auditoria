import os
import sys
import unittest


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories import saved_files as saved_files_repository  # noqa: E402


class FakeCursor:
    def __init__(self):
        self.query = ""
        self.params = None

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchall(self):
        return []

    def fetchone(self):
        return (0,)


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


class TestSavedFilesRepositoryFilters(unittest.TestCase):
    def test_list_tipo_filter_is_case_insensitive(self):
        conn = FakeConnection()

        result = saved_files_repository.list_arquivos_salvos(
            lambda: conn,
            limit=10,
            offset=0,
            tipo="Auditoria",
        )

        self.assertEqual(result, [])
        self.assertIn("LOWER(TRIM(COALESCE(a.tipo, ''))) = LOWER(TRIM(%s))", conn.cursor_obj.query)
        # Blindagem adicionada: filtra audits discarded -> 'discarded' entra nos params
        self.assertEqual(conn.cursor_obj.params, ["Auditoria", "discarded", 10, 0])
        self.assertTrue(conn.closed)

    def test_list_orders_by_newest_saved_row(self):
        conn = FakeConnection()

        result = saved_files_repository.list_arquivos_salvos(
            lambda: conn,
            limit=10,
            offset=0,
        )

        self.assertEqual(result, [])
        self.assertIn("ORDER BY a.id DESC", conn.cursor_obj.query)
        self.assertNotIn("ORDER BY a.data_analise DESC", conn.cursor_obj.query)
        self.assertEqual(conn.cursor_obj.params, ["discarded", 10, 0])
        self.assertTrue(conn.closed)

    def test_count_tipo_filter_is_case_insensitive(self):
        conn = FakeConnection()

        count = saved_files_repository.count_arquivos_salvos(
            lambda: conn,
            tipo="Auditoria",
        )

        self.assertEqual(count, 0)
        self.assertIn("LOWER(TRIM(COALESCE(a.tipo, ''))) = LOWER(TRIM(%s))", conn.cursor_obj.query)
        self.assertEqual(conn.cursor_obj.params, ["Auditoria", "discarded"])
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
