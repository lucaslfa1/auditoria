"""Regressão: um `metadata_json` com escape de NUL (\\u0000) não pode derrubar a
listagem inteira de Arquivos Salvos.

jsonb do Postgres rejeita o escape de NUL (`\\u0000`) mesmo sendo JSON válido a
nível de texto. A query de `list_arquivos_salvos` casta `metadata_json::jsonb`
numa subquery LATERAL — antes do fix, UMA linha corrompida fazia o cast abortar e
toda a lista retornava 500 (incidente prod 2026-06-15, arquivo_salvo id=206).
O fix remove o escape antes do cast (`replace(..., chr(92)||'u0000', '')`).
"""
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database

# Escape de NUL = barra invertida + 'u0000' (montado sem literal no source).
_NUL_ESCAPE = chr(92) + "u0000"


class TestSavedFilesNulMetadata(unittest.TestCase):
    def setUp(self):
        self._ids: list[int] = []

    def tearDown(self):
        if not self._ids:
            return
        conn = database.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM arquivos_salvos WHERE id = ANY(%s)", (self._ids,)
            )
            conn.commit()
        finally:
            conn.close()

    def _insert(self, metadata_json: str) -> int:
        conn = database.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO arquivos_salvos (tipo, conteudo, arquivo, metadata_json) "
                "VALUES ('auditoria', 'c', 'f', %s) RETURNING id",
                (metadata_json,),
            )
            new_id = cur.fetchone()["id"]
            conn.commit()
            self._ids.append(new_id)
            return new_id
        finally:
            conn.close()

    def test_list_survives_nul_escape_in_metadata(self):
        bad = '{"summary": "antes' + _NUL_ESCAPE + 'depois", "operator_id": "OP-NUL"}'
        self.assertIn(_NUL_ESCAPE, bad)
        self.assertNotIn("\x00", bad)  # é o escape de 6 chars, não um NUL real
        new_id = self._insert(bad)

        # Não pode levantar (antes do fix, o cast ::jsonb abortava a query inteira).
        items = database.list_arquivos_salvos(
            limit=100, offset=0, tipo="auditoria", include_audits=True
        )
        alvo = [item for item in items if item["id"] == new_id]
        self.assertEqual(len(alvo), 1, "a linha com \\u0000 deve aparecer, não derrubar a lista")
        # O escape de NUL foi removido ao sanitizar o metadata.
        self.assertEqual(alvo[0]["metadata"].get("summary"), "antesdepois")
        self.assertEqual(alvo[0]["metadata"].get("operator_id"), "OP-NUL")


if __name__ == "__main__":
    unittest.main()
