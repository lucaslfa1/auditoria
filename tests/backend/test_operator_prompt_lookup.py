import os
import sys
import unittest
import uuid
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database
from repositories import audits
from repositories import operators
from schemas import AuditResult


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestOperatorPromptLookup(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_operator_prompt_{uuid.uuid4().hex}.db",
        )
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

        fixtures = [
            ("MAT-001", "Transfer Operator", "Supervisor A", "TRANSFERÊNCIA", "CENTRAL - VERDE", "ATIVO"),
            ("MAT-002", "Fenix Operator", "Supervisor A", "TRANSFERÊNCIA", "FÊNIX", "ATIVO"),
            ("MAT-003", "Logistica Operator", "Supervisor B", "LOGÍSTICA", "LOGÍSTICA", "ATIVO"),
            ("MAT-004", "Unilever Operator", "Supervisor B", "LOGÍSTICA", "UNILEVER", "ATIVO"),
            ("MAT-005", "Mondelez Operator", "Supervisor B", "LOGÍSTICA", "MONDELEZ", "ATIVO"),
            ("MAT-006", "Taborda Operator", "Supervisor B", "LOGÍSTICA", "TABORDA", "ATIVO"),
            ("MAT-007", "Celula Operator", "Supervisor C", "RECEPTIVO", "CÉLULA", "ATIVO"),
            ("MAT-008", "Checklist Operator", "Supervisor C", "CHECKLIST", "CHECKLIST", "ATIVO"),
            ("MAT-009", "UTI Operator", "Supervisor D", "UTI (RJ)", "RJ - VERDE", "ATIVO"),
        ]
        for matricula, nome, supervisor, setor, escala, status in fixtures:
            operators.upsert_colaborador(database.get_connection, matricula, nome, supervisor, setor, escala, status, "", "")

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_sector_lookup_maps_special_cases(self):
        self.assertEqual(
            operators.get_colaboradores_para_prompt(database.get_connection, sector_id="transferencia"),
            ["Transfer Operator"],
        )
        self.assertEqual(
            operators.get_colaboradores_para_prompt(database.get_connection, sector_id="fenix"),
            ["Fenix Operator"],
        )
        self.assertEqual(
            sorted(operators.get_colaboradores_para_prompt(database.get_connection, sector_id="logistica")),
            sorted(["Logistica Operator", "Taborda Operator"]),
        )
        self.assertEqual(
            operators.get_colaboradores_para_prompt(database.get_connection, sector_id="logistica_unilever"),
            ["Unilever Operator"],
        )
        self.assertEqual(
            operators.get_colaboradores_para_prompt(database.get_connection, sector_id="mondelez"),
            ["Mondelez Operator"],
        )
        self.assertEqual(
            operators.get_colaboradores_para_prompt(database.get_connection, sector_id="celula_atendimento"),
            ["Celula Operator"],
        )
        self.assertEqual(
            operators.get_colaboradores_para_prompt(database.get_connection, sector_id="checklist"),
            ["Checklist Operator"],
        )
        self.assertEqual(
            operators.get_colaboradores_para_prompt(database.get_connection, sector_id="uti"),
            ["UTI Operator"],
        )

    def test_existing_supervisor_and_escala_filters_are_preserved(self):
        self.assertEqual(
            operators.get_colaboradores_para_prompt(database.get_connection, supervisor="Supervisor A", sector_id="fenix"),
            ["Fenix Operator"],
        )
        self.assertEqual(
            operators.get_colaboradores_para_prompt(database.get_connection, escala="UNILEVER", sector_id="logistica_unilever"),
            ["Unilever Operator"],
        )
        self.assertEqual(
            operators.get_colaboradores_para_prompt(database.get_connection, supervisor="Supervisor A", sector_id="logistica"),
            [],
        )

    def test_lookup_returns_preferred_telephony_id_filtered_by_sector(self):
        operators.upsert_colaborador(database.get_connection, "MAT-020", "Lookup Operator", "Supervisor L", "LOGÍSTICA", "LOGÍSTICA", "ATIVO", "", "")
        operators.upsert_colaborador_telefonia(database.get_connection, 
            nome="Lookup Operator",
            id_telefonia="5001",
            softphone_number="66665001",
            telefonia_account="lookup.operator",
            organizacao_telefonia="LOGISTICA",
            tipo_agente="Agente versátil",
            status_telefonia="Normal",
        )

        operators = operators.get_colaboradores_lookup(database.get_connection, sector_id="logistica", search="lookup")
        self.assertEqual(len(operators), 1)
        self.assertEqual(operators[0]["name"], "Lookup Operator")
        self.assertEqual(operators[0]["preferredId"], "5001")
        self.assertEqual(operators[0]["preferredIdSource"], "ID Huawei")
        self.assertEqual(operators[0]["idHuawei"], "5001")

    def test_lookup_ignores_legacy_weon_id_in_search_and_payload(self):
        operators.upsert_colaborador(database.get_connection, "MAT-021", "Legacy Operator", "Supervisor L", "LOGISTICA", "LOGISTICA", "ATIVO", "WEON-999", "")

        operators_by_name = operators.get_colaboradores_lookup(database.get_connection, search="legacy")
        self.assertEqual(len(operators_by_name), 1)
        self.assertEqual(operators_by_name[0]["preferredId"], "MAT-021")
        self.assertNotIn("idWeon", operators_by_name[0])

        operators_by_weon = operators.get_colaboradores_lookup(database.get_connection, search="WEON-999")
        self.assertEqual(operators_by_weon, [])

    def test_active_collaborators_remain_visible_even_if_legacy_auditavel_is_false(self):
        operators.create_colaborador(database.get_connection, 
            nome="Hidden Operator",
            supervisor="Supervisor H",
            setor="LOGISTICA",
            escala="LOGISTICA",
            status="ATIVO",
            auditavel=False,
            matricula="MAT-022",
        )

        self.assertEqual(len(operators.get_colaboradores_lookup(database.get_connection, search="hidden")), 1)
        self.assertIn(
            "Hidden Operator",
            operators.get_colaboradores_para_prompt(database.get_connection, sector_id="logistica"),
        )
        self.assertIsNotNone(operators.buscar_colaborador_por_nome(database.get_connection, "Hidden Operator"))

    def test_telephony_import_enriches_existing_operator_without_losing_supervisor(self):
        operators.upsert_colaborador(database.get_connection, "MAT-010", "Operador Telefonia", "Supervisor T", "LOGÍSTICA", "LOGÍSTICA", "ATIVO", "", "")
        operators.upsert_colaborador_telefonia(database.get_connection, 
            nome="Operador Telefonia",
            id_telefonia="2447",
            softphone_number="66662337",
            telefonia_account="operador.telefonia",
            organizacao_telefonia="LOGISTICA",
            tipo_agente="Agente versátil",
            status_telefonia="Normal",
        )

        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM colaboradores WHERE nome = %s", ("Operador Telefonia",))
        row = c.fetchone()
        conn.close()

        self.assertEqual(row["supervisor"], "Supervisor T")
        self.assertEqual(row["id_huawei"], "2447")
        self.assertEqual(row["id_telefonia"], "2447")
        self.assertEqual(row["softphone_number"], "66662337")
        self.assertEqual(row["telefonia_account"], "operador.telefonia")
        self.assertEqual(row["organizacao_telefonia"], "LOGISTICA")

    def test_audits_export_matches_operator_by_softphone_number(self):
        operators.upsert_colaborador(database.get_connection, "MAT-011", "Operador Softphone", "Supervisor S", "LOGÍSTICA", "UNILEVER", "ATIVO", "", "")
        operators.upsert_colaborador_telefonia(database.get_connection, 
            nome="Operador Softphone",
            id_telefonia="3001",
            softphone_number="66660001",
            telefonia_account="softphone.user",
            organizacao_telefonia="UNILEVER",
            tipo_agente="Agente versátil",
            status_telefonia="Normal",
        )

        result = AuditResult(
            score=8.0,
            maxPossibleScore=10.0,
            summary="Teste softphone",
            details=[],
            transcription=[],
            operatorName="Operador Softphone",
            operatorId="66660001",
            timestamp=datetime.now().isoformat(),
        )
        database.save_audit(
            result,
            input_hash="hash-softphone",
            alert_id="alerta",
            alert_label="Alerta",
            operator_id="66660001",
            sector_id="logistica_unilever",
            status="approved",
        )

        audits = database.get_audits_for_export()
        matched = next(audit for audit in audits if audit["operator_name"] == "Operador Softphone")

        self.assertEqual(matched["supervisor"], "Supervisor S")
        self.assertEqual(matched["escala"], "UNILEVER")


    def test_bulk_actions_keep_lookup_and_prompt_in_sync_with_status(self):
        operators.create_colaborador(database.get_connection, 
            nome="Bulk Operator",
            supervisor="Supervisor Bulk",
            setor="LOGISTICA",
            escala="LOGISTICA",
            status="ATIVO",
            auditavel=True,
            matricula="MAT-023",
        )
        operators.create_colaborador(database.get_connection, 
            nome="Inactive Bulk Operator",
            supervisor="Supervisor Bulk",
            setor="LOGISTICA",
            escala="LOGISTICA",
            status="INATIVO",
            auditavel=False,
            matricula="MAT-024",
        )

        rows_by_name = {
            row["nome"]: row
            for row in operators.list_colaboradores(database.get_connection)
            if row["nome"] in {"Bulk Operator", "Inactive Bulk Operator"}
        }
        bulk_operator_id = rows_by_name["Bulk Operator"]["id"]
        inactive_operator_id = rows_by_name["Inactive Bulk Operator"]["id"]

        self.assertEqual(len(operators.get_colaboradores_lookup(database.get_connection, search="bulk operator")), 1)

        rows_by_name = {
            row["nome"]: row
            for row in operators.list_colaboradores(database.get_connection)
            if row["nome"] in {"Bulk Operator", "Inactive Bulk Operator"}
        }
        self.assertTrue(rows_by_name["Bulk Operator"]["auditavel"])
        self.assertFalse(rows_by_name["Inactive Bulk Operator"]["auditavel"])
        self.assertEqual(len(operators.get_colaboradores_lookup(database.get_connection, search="bulk operator")), 1)

        updated = operators.bulk_apply_colaborador_action(database.get_connection, [bulk_operator_id], "inactivate")
        self.assertEqual(updated, 1)
        self.assertEqual(operators.get_colaboradores_lookup(database.get_connection, search="bulk operator"), [])

        rows_by_name = {
            row["nome"]: row
            for row in operators.list_colaboradores(database.get_connection)
            if row["nome"] in {"Bulk Operator", "Inactive Bulk Operator"}
        }
        self.assertEqual(rows_by_name["Bulk Operator"]["status"], "INATIVO")
        self.assertFalse(rows_by_name["Bulk Operator"]["auditavel"])

        updated = operators.bulk_apply_colaborador_action(database.get_connection, [bulk_operator_id], "activate")
        self.assertEqual(updated, 1)

        rows_by_name = {
            row["nome"]: row
            for row in operators.list_colaboradores(database.get_connection)
            if row["nome"] in {"Bulk Operator", "Inactive Bulk Operator"}
        }
        self.assertEqual(rows_by_name["Bulk Operator"]["status"], "ATIVO")
        self.assertTrue(rows_by_name["Bulk Operator"]["auditavel"])
        self.assertEqual(len(operators.get_colaboradores_lookup(database.get_connection, search="bulk operator")), 1)

    def test_fenix_is_persisted_as_fenix_even_when_raw_sector_arrives_as_transferencia(self):
        operators.upsert_colaborador(database.get_connection, 
            "MAT-025",
            "Fenix Persistido",
            "Supervisor F",
            "TRANSFERENCIA",
            "FENIX",
            "ATIVO",
            "",
            "",
        )

        row = next(
            item for item in operators.list_colaboradores(database.get_connection) if item["matricula"] == "MAT-025"
        )
        self.assertEqual(row["setor"], "FENIX")
        self.assertNotIn(
            "Fenix Persistido",
            operators.get_colaboradores_para_prompt(database.get_connection, sector_id="transferencia"),
        )
        self.assertIn(
            "Fenix Persistido",
            operators.get_colaboradores_para_prompt(database.get_connection, sector_id="fenix"),
        )

if __name__ == "__main__":
    unittest.main()
