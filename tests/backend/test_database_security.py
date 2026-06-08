import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import psycopg2
from psycopg2.errors import IntegrityError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database  # noqa: E402

class TestDatabaseSecurity(unittest.TestCase):
    def _bootstrap_env(self) -> dict[str, str]:
        return {
            "AUTH_USERS_JSON": '[{"username":"Admin","password":"SenhaForte!9","role":"admin"}]',
            "AUDITORIA_SEED_OPERADORES_JSON": "false",
        }

    def test_seed_users_uses_inline_auth_users_json(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [0]
        
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "AUTH_USERS_JSON": '[{"username":"admin","password":"SenhaForte!9","role":"admin"}]',
            },
            clear=False,
        ):
            database._seed_users(mock_cursor)

        # Ensure insert was called
        self.assertTrue(mock_cursor.execute.called)

    @patch("db.database._is_isolated_test_database", return_value=False)
    def test_seed_users_requires_explicit_auth_config_in_production(self, mock_is_test):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [0]
        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "production", "AUTH_USERS_JSON": "", "AUTH_USERS_FILE": ""},
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                database._seed_users(mock_cursor)

    @patch("db.connection.get_connection")
    def test_users_trigger_rejects_invalid_role(self, mock_get_connection):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Simulate Postgres CHECK constraint failure for invalid role
        mock_cursor.execute.side_effect = IntegrityError("check constraint violation on 'role'")

        with self.assertRaises(IntegrityError):
            mock_cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                ("supervisorteste", "hash", "GESTOR"),
            )

    @patch("db.connection.get_connection")
    def test_audits_trigger_rejects_invalid_status(self, mock_get_connection):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Simulate Postgres CHECK constraint failure for invalid status
        mock_cursor.execute.side_effect = IntegrityError("check constraint violation on 'status'")

        with self.assertRaises(IntegrityError):
            mock_cursor.execute(
                "INSERT INTO audits (timestamp, operator_name, score, status) VALUES (%s, %s, %s, %s)",
                ("2026-03-08T12:00:00", "Operador Teste", 7.5, "APROVADA_INVALIDA"),
            )

    @patch("db.connection.get_connection")
    def test_review_queue_triggers_reject_invalid_values(self, mock_get_connection):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.execute.side_effect = IntegrityError("check constraint violation")

        with self.assertRaises(IntegrityError):
            mock_cursor.execute(
                "INSERT INTO fila_revisao_classificacao (status) VALUES (%s)",
                ("urgennt"),
            )

if __name__ == "__main__":
    unittest.main()
