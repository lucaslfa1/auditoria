"""Tests for the DB Knowledge Agent.

These tests require a running PostgreSQL instance (docker-compose up db).
They are skipped automatically when the database is unavailable.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import psycopg2
    from db.connection import get_connection

    _pg_available = True
    try:
        _test_conn = get_connection()
        _test_conn.close()
    except Exception:
        _pg_available = False
except Exception:
    _pg_available = False

from scripts.db_knowledge_agent import DBKnowledgeAgent


EXPECTED_FILES = [
    "colaboradores.md",
    "supervisores.md",
    "setores_e_escalas.md",
    "criterios_auditoria.md",
    "configuracoes.md",
    "usuarios.md",
    "estrutura_banco.md",
    "estatisticas.md",
    "regras_negocio.md",
    "_INDEX.md",
]


@unittest.skipUnless(_pg_available, "PostgreSQL not available")
class TestDBKnowledgeAgent(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output_dir = Path(self._tmp.name) / "rag_output"

    def tearDown(self):
        self._tmp.cleanup()

    def test_agent_generates_all_files(self):
        agent = DBKnowledgeAgent(output_dir=self.output_dir)
        files = agent.run()

        self.assertEqual(len(files), len(EXPECTED_FILES))
        for fname in EXPECTED_FILES:
            self.assertIn(fname, files)
            fpath = self.output_dir / fname
            self.assertTrue(fpath.exists(), f"{fname} should exist")
            self.assertGreater(fpath.stat().st_size, 0, f"{fname} should not be empty")

    def test_agent_is_idempotent(self):
        """Running the agent twice should produce the same number of files."""
        agent1 = DBKnowledgeAgent(output_dir=self.output_dir)
        files1 = agent1.run()

        agent2 = DBKnowledgeAgent(output_dir=self.output_dir)
        files2 = agent2.run()

        self.assertEqual(len(files1), len(files2))
        self.assertEqual(set(files1), set(files2))


if __name__ == "__main__":
    unittest.main()
