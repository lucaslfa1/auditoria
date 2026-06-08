import os
import sys
import tempfile
import unittest


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database  # noqa: E402
from repositories import saved_files as saved_files_repository  # noqa: E402


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestSavedFilesRepository(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.db_path = os.path.join(temp_dir.name, "saved-files-repository.db")
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.original_db_name

    def test_roundtrip_saved_file_via_repository(self):
        saved_id = saved_files_repository.save_arquivo(
            database.get_connection,
            tipo="auditoria",
            conteudo="conteudo inicial",
            arquivo="audit.txt",
            audit_id=None,
            operator_name="Operador Repo",
            sector_id="bas",
            alert_label="4.1.1",
            score=88.5,
            metadata={"origin": "repo-test"},
            criado_por="repo_tester",
        )

        self.assertEqual(saved_files_repository.count_arquivos_salvos(database.get_connection, "auditoria"), 1)

        item = saved_files_repository.get_arquivo_salvo(database.get_connection, saved_id)
        self.assertIsNotNone(item)
        self.assertEqual(item["operator_name"], "Operador Repo")
        self.assertEqual(item["metadata"], {"origin": "repo-test"})

        listed = saved_files_repository.list_arquivos_salvos(database.get_connection, limit=10, offset=0, tipo="auditoria")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], saved_id)

        self.assertTrue(saved_files_repository.update_arquivo_salvo(database.get_connection, saved_id, "conteudo atualizado"))
        updated = saved_files_repository.get_arquivo_salvo(database.get_connection, saved_id)
        self.assertEqual(updated["conteudo"], "conteudo atualizado")

        self.assertTrue(saved_files_repository.delete_arquivo_salvo(database.get_connection, saved_id))
        self.assertEqual(saved_files_repository.count_arquivos_salvos(database.get_connection), 0)
