import os
import sys
import unittest


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.import_funcionarios_rh import (  # noqa: E402
    _build_existing_lookup,
    _find_existing_colaborador,
    _get_row_value,
    _resolve_sector_id,
    _should_skip_workbook,
    _upsert_funcionario,
    parse_filename,
)

try:
    from db.connection import get_connection

    _pg_available = True
    try:
        _test_conn = get_connection()
        _test_conn.close()
    except Exception:
        _pg_available = False
except Exception:
    _pg_available = False


class TestImportFuncionariosRh(unittest.TestCase):
    def test_parse_filename_sets_scale_override_for_logistica_variants(self):
        parsed = parse_filename("2602-LOG-MONDELEZ.xlsx")
        self.assertEqual(parsed["setor_id"], "LOGISTICA")
        self.assertEqual(parsed["escala"], "MONDELEZ")

    def test_resolve_sector_id_prefers_actual_row_sector_over_file_fallback(self):
        self.assertEqual(_resolve_sector_id("RECEPTIVO", "CHECKLIST"), "RECEPTIVO")
        self.assertEqual(_resolve_sector_id("TRANSFERENCIA", "DISTRIBUICAO"), "TRANSFERENCIA")

    def test_resolve_sector_id_keeps_fenix_as_own_sector_when_source_is_fenix(self):
        self.assertEqual(_resolve_sector_id("TRANSFERENCIA", "FENIX", "FENIX"), "FENIX")
        self.assertEqual(_resolve_sector_id("UTI", "FENIX", "FENIX"), "FENIX")

    def test_get_row_value_accepts_corrupted_turno_header(self):
        row = {
            "TURNO / OPERAO": "NOITE",
            "SETOR": "CHECKLIST",
        }
        self.assertEqual(_get_row_value(row, "tipo_escala"), "NOITE")

    def test_should_skip_consolidated_workbook(self):
        self.assertTrue(_should_skip_workbook("FUNCIONARIOS_CONSOLIDADO.xlsx"))
        self.assertFalse(_should_skip_workbook("2602-FENIX.xlsx"))

    def test_find_existing_colaborador_reconciles_unique_legacy_name_without_matricula(self):
        by_matricula = {}
        by_normalized_name = {
            "adryancelso": [{"id": 7, "nome": "Adryan Celso", "matricula": "", "supervisor": ""}],
        }

        found, matched_by = _find_existing_colaborador(
            {"nome": "Adryan Celso", "matricula": "12345"},
            by_matricula,
            by_normalized_name,
        )

        self.assertIsNotNone(found)
        self.assertEqual(found["id"], 7)
        self.assertEqual(matched_by, "nome")

    def test_find_existing_colaborador_does_not_reconcile_ambiguous_name(self):
        by_matricula = {}
        by_normalized_name = {
            "amandacarla": [
                {"id": 1, "nome": "Amanda Carla", "matricula": "", "supervisor": ""},
                {"id": 2, "nome": "Amanda Carla", "matricula": "", "supervisor": ""},
            ],
        }

        found, matched_by = _find_existing_colaborador(
            {"nome": "Amanda Carla", "matricula": "12345"},
            by_matricula,
            by_normalized_name,
        )

        self.assertIsNone(found)
        self.assertIsNone(matched_by)

    @unittest.skipUnless(_pg_available, "PostgreSQL not available - integration test")
    def test_upsert_funcionario_reuses_legacy_row_by_name_when_matricula_is_missing(self):
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Create a temp table for isolation
            cursor.execute("CREATE TEMP TABLE colaboradores (LIKE colaboradores INCLUDING ALL)")
            cursor.execute(
                "INSERT INTO colaboradores (nome, matricula, supervisor, setor, escala, status) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                ("Adryan Celso", "", "", "fenix", "TIME FENIX", "ATIVO"),
            )

            by_matricula, by_normalized_name = _build_existing_lookup(cursor)
            action = _upsert_funcionario(
                cursor,
                {
                    "nome": "Adryan Celso",
                    "matricula": "12345",
                    "supervisor": "Adryan Celso",
                    "setor": "TRANSFERENCIA",
                    "status": "ATIVO",
                    "id_weon": "77",
                    "id_huawei": "88",
                    "tipo_escala": "FENIX",
                },
                "FENIX",
                "FENIX",
                by_matricula,
                by_normalized_name,
            )

            self.assertEqual(action, "reconciled_name")

            cursor.execute("SELECT id, nome, matricula, supervisor, setor, escala FROM colaboradores")
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["matricula"], "12345")
            self.assertEqual(rows[0]["supervisor"], "Adryan Celso")
            self.assertEqual(rows[0]["setor"], "FENIX")
            self.assertEqual(rows[0]["escala"], "FENIX")
        finally:
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()
