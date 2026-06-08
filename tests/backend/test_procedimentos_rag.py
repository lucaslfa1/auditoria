import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.audit_evaluator as audit_evaluator
import db.database as database
from core import rag_triagem
from core.procedimentos_rag import (
    build_procedimento_chunks,
    find_procedimento_section,
    get_procedimento_prompt_block,
)


class TestProcedimentosRag(unittest.TestCase):
    def _dependencies(self):
        return audit_evaluator.AuditEvaluationDependencies(
            prompts_config={"audit_system": {}},
            get_config_value=lambda _key, default="": default,
            get_colaboradores_para_prompt=lambda **_kwargs: [],
            parse_json_with_repair=lambda *_args, **_kwargs: {},
            ai_client=None,
            ai_audit_model="model",
            generation_config=None,
            azure_openai_key=None,
            azure_openai_endpoint=None,
            azure_openai_deployment="deployment",
            ai_priority="azure",
            ai_enabled=False,
        )

    def test_resolves_cadastro_pop_by_alert_id(self):
        section = find_procedimento_section(
            sector_id="cadastro",
            alert_id="CADASTRO-ANTECEDENTES",
            alert_label="Antecedentes - Receptivo",
        )

        self.assertIsNotNone(section)
        self.assertEqual(section.source_path, "rag/sources/procedimentos_operacionais/cadastro.md")
        self.assertIn("CADASTRO", section.title.upper())
        self.assertIn("CPF/Placa", section.content)

    def test_resolves_risk_area_police_pop_by_pop_ref_even_for_bas(self):
        block = get_procedimento_prompt_block(
            sector_id="bas",
            alert_id="4.1.10",
            alert_label="Alerta Prioritario - Policia",
        )

        self.assertIn("PROCEDIMENTO OPERACIONAL OFICIAL", block)
        self.assertIn("ACIONAMENTO POLICIAL", block)
        self.assertIn("solicitou deslocamento e/ou reporte", block.lower())

    def test_unknown_or_pending_pop_returns_empty_block(self):
        block = get_procedimento_prompt_block(
            sector_id="logistica",
            alert_id="LOGISTICA-PARADA",
            alert_label="Parada Indevida - Motorista",
        )

        self.assertEqual(block, "")

    def test_audit_prompt_injects_pop_before_criteria(self):
        prompt = audit_evaluator.get_audit_system_prompt(
            "Auditoria de antecedentes.",
            "- ID: cpf | Peso: 1.0 | Solicitou CPF/Placa",
            sector_id="cadastro",
            alert_id="CADASTRO-ANTECEDENTES",
            alert_label="Antecedentes - Receptivo",
            dependencies=self._dependencies(),
        )

        self.assertIn("PROCEDIMENTO OPERACIONAL OFICIAL", prompt)
        self.assertLess(
            prompt.index("PROCEDIMENTO OPERACIONAL OFICIAL"),
            prompt.index("CRITERIOS (AVALIE SOMENTE ESTES"),
        )
        self.assertIn("O operador solicitou CPF/Placa", prompt)

    def test_builds_chunks_for_all_current_pop_sources(self):
        chunks = build_procedimento_chunks(max_chars=2500)
        sources = {chunk.source_path for chunk in chunks}

        self.assertIn("rag/sources/procedimentos_operacionais/cadastro.md", sources)
        self.assertIn("rag/sources/procedimentos_operacionais/areas_de_risco.md", sources)
        self.assertGreaterEqual(len(chunks), 21)
        self.assertTrue(any("BAS-PRIORITARIO-POLICIA" in chunk.alert_ids for chunk in chunks))

    def test_semantic_chunk_search_matches_alert_aliases(self):
        class FakeCursor:
            def __init__(self):
                self.sql = ""
                self.params = ()

            def execute(self, sql, params):
                self.sql = sql
                self.params = params

            def fetchall(self):
                return [
                    {
                        "source_path": "rag/sources/procedimentos_operacionais/areas_de_risco.md",
                        "source_hash": "hash",
                        "setor": "areas_de_risco",
                        "alert_id": "BAS-PRIORITARIO-POLICIA",
                        "alert_label": "ACIONAMENTO POLICIAL",
                        "section_title": "ACIONAMENTO POLICIAL",
                        "chunk_index": 0,
                        "content": "conteudo",
                        "metadata_json": '{"alert_ids": ["BAS-PRIORITARIO-POLICIA", "4.1.10"]}',
                        "distance": 0.12,
                    }
                ]

        class FakeConnection:
            def __init__(self):
                self.cursor_instance = FakeCursor()
                self.closed = False

            def cursor(self):
                return self.cursor_instance

            def close(self):
                self.closed = True

        fake_conn = FakeConnection()
        original_get_connection = database.get_connection
        database.get_connection = lambda: fake_conn
        try:
            rows = rag_triagem.buscar_procedimento_chunks(
                [0.1, 0.2],
                setor="bas",
                alert_id="4.1.10",
                limit=5,
            )
        finally:
            database.get_connection = original_get_connection

        self.assertEqual(rows[0]["alert_id"], "BAS-PRIORITARIO-POLICIA")
        self.assertIn("metadata_json::jsonb -> 'alert_ids' ? %s", fake_conn.cursor_instance.sql)
        self.assertEqual(fake_conn.cursor_instance.params[1:3], ("4.1.10", "4.1.10"))
        self.assertTrue(fake_conn.closed)


if __name__ == "__main__":
    unittest.main()
