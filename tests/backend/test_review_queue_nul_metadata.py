"""Regressão: um `metadata_json` com escape de NUL (\\u0000) na fila de triagem
(`fila_revisao_classificacao`) não pode derrubar a listagem inteira nem ser
gravado pela esteira.

Mesmo modo de falha do incidente prod de /api/salvos (2026-06-15), mas no fluxo
de Triagem, que roda o dia todo e é alimentado direto por metadata de IA/Huawei:
- LEITURA: o cast `metadata_json::jsonb` é avaliado linha-a-linha; UMA linha com
  `\\u0000` faria a query inteira estourar (500). `harden_jsonb_nul_cast` protege.
- ESCRITA: `strip_json_nul` remove o NUL na serialização, atacando a raiz.
"""
import json
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database

# Escape de NUL = barra invertida + 'u0000' (montado sem literal no source).
_NUL_ESCAPE = chr(92) + "u0000"
_NUL_CHAR = chr(0)


class TestReviewQueueNulMetadata(unittest.TestCase):
    def setUp(self):
        self._hashes: list[str] = []

    def tearDown(self):
        if not self._hashes:
            return
        conn = database.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM fila_revisao_classificacao WHERE input_hash = ANY(%s)",
                (self._hashes,),
            )
            conn.commit()
        finally:
            conn.close()

    def _insert_raw(self, input_hash: str, metadata_json: str) -> None:
        """Insere uma linha CRUA na fila (sem passar pela sanitização de escrita),
        simulando dado já gravado com NUL antes do fix."""
        conn = database.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO fila_revisao_classificacao
                    (input_hash, nome_arquivo, metadata_json, status, criado_em, atualizado_em)
                VALUES (%s, %s, %s, 'pending', %s, %s)
                """,
                (input_hash, "nul.wav", metadata_json, "2026-06-16T00:00:00", "2026-06-16T00:00:00"),
            )
            conn.commit()
            self._hashes.append(input_hash)
        finally:
            conn.close()

    def _read_raw_metadata(self, input_hash: str) -> str:
        conn = database.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT metadata_json FROM fila_revisao_classificacao WHERE input_hash = %s",
                (input_hash,),
            )
            row = cur.fetchone()
            return row["metadata_json"] if row else ""
        finally:
            conn.close()

    def test_listagem_sobrevive_a_nul_em_linha_ja_gravada(self):
        h = "nul-read-test-hash"
        bad = (
            '{"summary": "antes' + _NUL_ESCAPE + 'depois",'
            ' "origem": "manual", "operator_name": "Fulano' + _NUL_ESCAPE + '"}'
        )
        self.assertIn(_NUL_ESCAPE, bad)
        self.assertNotIn(_NUL_CHAR, bad)  # é o escape de 6 chars, não um NUL real
        self._insert_raw(h, bad)

        # Não pode levantar (antes do fix, o cast ::jsonb abortava a query inteira).
        items = database.listar_fila_revisao_classificacao(limit=100, status="pending")
        self.assertTrue(any(it["input_hash"] == h for it in items),
                        "a linha com NUL deve aparecer na fila, não derrubar a lista")

        por_hash = database.obter_fila_revisao_classificacao_por_hash(h)
        self.assertIsNotNone(por_hash)
        self.assertEqual(por_hash["input_hash"], h)

    def test_escrita_sanitiza_nul_na_origem(self):
        h = "nul-write-test-hash"
        self._hashes.append(h)  # garante limpeza mesmo se o insert falhar
        database.sincronizar_fila_revisao_classificacao(
            input_hash=h,
            nome_arquivo="nul.wav",
            metadata={"summary": "antes" + _NUL_CHAR + "depois", "origem": "manual"},
        )
        raw = self._read_raw_metadata(h)
        self.assertNotEqual(raw, "")
        self.assertNotIn(_NUL_ESCAPE, raw)  # escape removido na escrita
        self.assertNotIn(_NUL_CHAR, raw)    # nem o NUL real
        parsed = json.loads(raw)
        self.assertEqual(parsed.get("summary"), "antesdepois")


if __name__ == "__main__":
    unittest.main()
