"""Cobertura da correcao manual via Triagem (corrigir_classificacao_fila_revisao).

Antes da v1.3.96, a funcao gravava `setor_previsto`, `alerta_previsto` e
metadados de auditoria (`manual_review_*`) mas NAO setava
`metadata.classification_status = 'done'`. Sintoma: depois do auditor corrigir
o setor/alerta na Triagem, o frontend (`RemoteTriageQueue.tsx`) continuava
mostrando o botao "Triar" porque le `metadata.classification_status !== 'done'`.

Confirmado em prod (2026-05-28): 8 itens com `manual_review_source='triagem_ui'`
ficaram com `classification_status=null` apos correcao manual.
"""

import json
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class _FakeCursor:
    """Cursor que retorna dicts (estilo psycopg2 DictCursor) e captura UPDATEs."""

    def __init__(self, *, initial_row: dict, updated_row: dict):
        self.queries: list[tuple[str, tuple]] = []
        self._initial_row = initial_row
        self._updated_row = updated_row
        self._call = 0

    def execute(self, query, params=()):
        self.queries.append((query.strip(), tuple(params) if params else ()))

    def fetchone(self):
        self._call += 1
        # 1a chamada: SELECT inicial; 2a chamada: SELECT pos-UPDATE.
        if self._call == 1:
            return self._initial_row
        return self._updated_row


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def _row(metadata_json: str, **overrides) -> dict:
    base = {
        "id": 26,
        "input_hash": "hash-abc",
        "nome_arquivo": "call.wav",
        "setor_previsto": "desconhecido",
        "alerta_previsto": "desconhecido",
        "confianca": 0.42,
        "operador_previsto": "Operador X",
        "erro": "baixa_confianca",
        "prioridade": "high",
        "motivos_json": "[]",
        "metadata_json": metadata_json,
        "status": "needs_manual_triage",
        "criado_em": "2026-05-27T11:52:11.073477",
        "atualizado_em": "2026-05-27T11:52:11.073477",
    }
    base.update(overrides)
    return base


class TestCorrigirClassificacaoFilaRevisao(unittest.TestCase):

    def test_correcao_manual_seta_classification_status_done(self):
        """Apos correcao manual via Triagem, metadata.classification_status
        deve ser 'done' para o frontend nao exibir o botao "Triar" de novo."""
        from repositories import classification_review as repo

        initial = _row(metadata_json='{"classification_status": "pending"}')
        # Updated row eh consultado apos o UPDATE; o conteudo nao importa
        # para este assert, basta nao quebrar a montagem do dict de retorno.
        updated = _row(
            metadata_json='{"classification_status": "done"}',
            setor_previsto="uti",
            alerta_previsto="UTI-PRIORITARIO-MOT",
        )
        cur = _FakeCursor(initial_row=initial, updated_row=updated)
        conn = _FakeConn(cur)

        def factory():
            return conn

        result = repo.corrigir_classificacao_fila_revisao(
            factory,
            input_hash="hash-abc",
            setor_previsto="uti",
            alerta_previsto="UTI-PRIORITARIO-MOT",
            operador_previsto="Deirilene Deane Lisboa Pereira",
            operator_id="11243",
            revisado_por="lucas",
        )

        self.assertIsNotNone(result)

        # Encontra o UPDATE e extrai o metadata_json serializado (6o parametro
        # do UPDATE conforme posicoes em repositories/classification_review.py).
        update_calls = [(q, p) for (q, p) in cur.queries if q.startswith("UPDATE")]
        self.assertEqual(len(update_calls), 1, "Esperado exatamente um UPDATE")
        _, params = update_calls[0]
        metadata_serialized = params[5]
        metadata_parsed = json.loads(metadata_serialized)

        self.assertEqual(
            metadata_parsed.get("classification_status"),
            "done",
            "metadata.classification_status precisa ser 'done' apos correcao manual",
        )

    def test_correcao_manual_substitui_status_pending_anterior(self):
        """Mesmo que o item tenha sido classificado pela IA com status='pending'
        (erro intermediario), a correcao manual deve forcar 'done'."""
        from repositories import classification_review as repo

        initial = _row(metadata_json='{"classification_status": "pending", "classification_error": "low_confidence"}')
        updated = _row(metadata_json='{}', setor_previsto="uti", alerta_previsto="UTI-PRIORITARIO-MOT")
        cur = _FakeCursor(initial_row=initial, updated_row=updated)
        conn = _FakeConn(cur)

        repo.corrigir_classificacao_fila_revisao(
            lambda: conn,
            input_hash="hash-abc",
            setor_previsto="uti",
            alerta_previsto="UTI-PRIORITARIO-MOT",
            revisado_por="lucas",
        )

        update_calls = [(q, p) for (q, p) in cur.queries if q.startswith("UPDATE")]
        _, params = update_calls[0]
        metadata_parsed = json.loads(params[5])
        self.assertEqual(metadata_parsed.get("classification_status"), "done")


if __name__ == "__main__":
    unittest.main()
