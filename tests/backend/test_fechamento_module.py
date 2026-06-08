import inspect
import os
import sys
import unittest
from io import BytesIO

import openpyxl

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.export_fechamento import HEADERS, generate_fechamento_excel
from core.fechamento_service import (
    _load_layout_seed,
    _is_receptive,
    _is_uti,
    _is_uti_rj,
    _processo_uti,
    _processo_uti_rj,
    get_fechamento_rows,
    save_fechamento_overrides,
)
from db.domain_constants import AUDIT_STATUS_APPROVED
from db.runtime_schema import ensure_runtime_schema


class _FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.sql = ""
        self.params = None
        self.executions = []

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params
        self.executions.append((sql, params))

    def fetchall(self):
        return self.rows


class _LayoutModeCountCursor(_FakeCursor):
    def fetchone(self):
        return {"total": 1}


class _FakeConnection:
    def __init__(self, cursors):
        self._cursors = list(cursors)
        self.committed = False
        self.closed = False

    def cursor(self):
        if not self._cursors:
            raise AssertionError("cursor() called more times than expected")
        return self._cursors.pop(0)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def _db_row(**overrides):
    row = {
        "colab_id": 10,
        "nome": "Ana Souza",
        "matricula": "123",
        "supervisor": "Sup A",
        "setor": "uti",
        "escala": "Verde",
        "id_huawei": "HW-1",
        "status": "ATIVO",
        "auditavel": 1,
        "nota_mot": 0,
        "nota_pa": 0,
        "nota_cli": 0,
        "nota_policia": 0,
        "operacional_override": None,
        "telefonica_override": None,
        "desempenho_override": None,
        "processo_override": None,
        "final_override": None,
        "media_auditoria": 8.0,
    }
    row.update(overrides)
    return row


class TestFechamentoModule(unittest.TestCase):
    def test_rows_use_audit_date_range_for_month(self):
        cursor = _FakeCursor(rows=[_db_row()])
        conn = _FakeConnection([cursor])

        rows = get_fechamento_rows(conn, 4, 2026)

        self.assertEqual(rows[0]["operacional"], "8.0")
        self.assertIn("COALESCE(audit_date, timestamp)::TIMESTAMP >= %s", cursor.sql)
        self.assertIn("COALESCE(audit_date, timestamp)::TIMESTAMP < %s", cursor.sql)
        self.assertIn("NULLIF(c.supervisor, '')", cursor.sql)
        self.assertNotIn("EXTRACT(MONTH", cursor.sql)
        self.assertEqual(cursor.params, (AUDIT_STATUS_APPROVED, "2026-04-01", "2026-05-01", 4, 2026))

    def test_rows_exclude_removed_operations_and_nameless_telephony_services(self):
        cursor = _FakeCursor(rows=[
            _db_row(colab_id=1, nome="Operador Sanofi", escala="Time Sanofi"),
            _db_row(
                colab_id=2,
                nome="",
                escala="Telefonia",
                telefonia_account="servico.telefonia",
                organizacao_telefonia="LOGISTICA",
                id_telefonia="999",
            ),
            _db_row(colab_id=3, nome="Operador Valido", escala="LOGISTICA"),
        ])
        conn = _FakeConnection([cursor])

        rows = get_fechamento_rows(conn, 4, 2026)

        self.assertEqual([row["nome"] for row in rows], ["Operador Valido"])
        self.assertEqual(rows[0]["id"], 1)

    def test_desempenho_uses_final_audit_score_after_review(self):
        cursor = _FakeCursor(rows=[
            _db_row(colab_id=1, nome="Ana Alta", media_auditoria=8.0),
            _db_row(colab_id=2, nome="Bia Baixa", media_auditoria=7.99),
            _db_row(colab_id=3, nome="Carla Sem Nota", media_auditoria=None),
        ])
        conn = _FakeConnection([cursor])

        rows = get_fechamento_rows(conn, 4, 2026)

        desempenho_by_nome = {row["nome"]: row["desempenho"] for row in rows}
        self.assertEqual(desempenho_by_nome["Ana Alta"], "BOM")
        self.assertEqual(desempenho_by_nome["Bia Baixa"], "RUIM")
        self.assertEqual(desempenho_by_nome["Carla Sem Nota"], "")

    def test_nao_auditavel_keeps_ativo_status_in_fechamento(self):
        # BUG-026 (2026-05-26): operadores ATIVO+auditavel=0 (ex: Fernanda Sant
        # Anna) devem aparecer no fechamento como ATIVO. A flag `auditavel` so
        # vale para o pipeline da IA; o fechamento exibe o status real do
        # colaborador. Anteriormente _resolve_fechamento_status forcava
        # INATIVO e escondia esses operadores do relatorio mensal.
        cursor = _FakeCursor(rows=[
            _db_row(status="ATIVO", auditavel=0, media_auditoria=8.5),
        ])
        conn = _FakeConnection([cursor])

        rows = get_fechamento_rows(conn, 4, 2026)

        self.assertEqual(rows[0]["status"], "ATIVO")
        # desempenho continua sendo BOM porque media >= threshold (8.5 >= 7)
        self.assertEqual(rows[0]["desempenho"], "BOM")

    def test_save_only_persists_overrides_that_differ_from_base_row(self):
        insert_cursor = _FakeCursor()
        select_cursor = _FakeCursor(rows=[_db_row()])
        conn = _FakeConnection([insert_cursor, select_cursor])

        save_fechamento_overrides(
            conn,
            4,
            2026,
            [
                {
                    "colab_id": 10,
                    "matricula": "123",
                    "nome": "Ana Souza",
                    "operacional": "8.0",
                    "telefonica": "",
                    "desempenho": "BOM",
                    "status": "ATIVO",
                    "turno": "Verde",
                    "supervisor": "Sup B",
                    "setor": "uti",
                    "nota_mot": 0,
                    "nota_pa": 0,
                    "nota_cli": 0,
                    "nota_policia": 0,
                    "processo": "70%",
                    "final": "-4%",
                    "huawei": "HW-1",
                }
            ],
        )

        saved = insert_cursor.params
        self.assertTrue(conn.committed)
        self.assertIsNone(saved["matricula"])
        self.assertIsNone(saved["nome"])
        self.assertIsNone(saved["operacional"])
        self.assertEqual(saved["supervisor"], "Sup B")

    def test_runtime_schema_creates_colaboradores_before_fechamento_fk(self):
        source = inspect.getsource(ensure_runtime_schema)

        colaboradores_pos = source.index("CREATE TABLE IF NOT EXISTS colaboradores")
        fechamento_pos = source.index("CREATE TABLE IF NOT EXISTS fechamento_cadeia_contatos")
        layout_pos = source.index("CREATE TABLE IF NOT EXISTS fechamento_layout_operadores")
        self.assertLess(colaboradores_pos, fechamento_pos)
        self.assertLess(colaboradores_pos, layout_pos)

    def test_qualidade_final_layout_seed_preserves_contract_rows(self):
        rows = _load_layout_seed()

        self.assertEqual(len(rows), 224)
        self.assertEqual(rows[0]["id_visual"], 1)
        self.assertEqual(rows[0]["nome"], "JULIANE CRISTINA DA SILVA ASSIS COLAÇO")
        self.assertEqual(rows[0]["turno"], "CADASTRO")
        self.assertEqual(rows[-1]["id_visual"], 17)
        self.assertEqual(rows[-1]["turno"], "CENTRAL - VERDE")
        mondelez_rows = [row for row in rows if row["turno"] == "MONDELEZ"]
        self.assertEqual(len(mondelez_rows), 3)
        self.assertTrue(all(row["huawei"] == "-" and row["weon"] == "-" for row in mondelez_rows))

    def test_layout_mode_appends_uti_collaborators_outside_fixed_layout(self):
        conn = _FakeConnection([
            _LayoutModeCountCursor(),
            _FakeCursor(rows=[]),
            _FakeCursor(rows=[
                _db_row(
                    colab_id=40,
                    nome="Operadora UTI",
                    matricula="400",
                    setor="UTI",
                    escala="Verde",
                    media_auditoria=None,
                ),
                _db_row(
                    colab_id=41,
                    nome="Operadora BAS",
                    matricula="401",
                    setor="BAS",
                    escala="Azul",
                    media_auditoria=None,
                ),
            ]),
        ])

        rows = get_fechamento_rows(conn, 4, 2026)

        self.assertTrue(conn.committed)
        self.assertEqual([row["nome"] for row in rows], ["Operadora UTI"])
        self.assertIsNone(rows[0]["layout_id"])
        self.assertEqual(rows[0]["colab_id"], 40)
        self.assertEqual(rows[0]["setor"], "UTI")
        self.assertEqual(rows[0]["processo"], "70%")

    def test_uti_rj_detection_distinguishes_from_plain_uti(self):
        self.assertTrue(_is_uti_rj("UTI RJ", ""))
        self.assertTrue(_is_uti_rj("uti-rj", ""))
        self.assertTrue(_is_uti_rj("UTI/RJ", ""))
        self.assertTrue(_is_uti_rj("", "RJ"))
        self.assertFalse(_is_uti_rj("UTI", "Verde"))
        self.assertFalse(_is_uti_rj("UTI-COMBO", ""))
        self.assertTrue(_is_uti("UTI", ""))

    def test_processo_uti_table_matches_doc(self):
        self.assertAlmostEqual(_processo_uti(4), 1.10)
        self.assertAlmostEqual(_processo_uti(3), 1.00)
        self.assertAlmostEqual(_processo_uti(2), 0.90)
        self.assertAlmostEqual(_processo_uti(1), 0.80)
        self.assertAlmostEqual(_processo_uti(0), 0.70)

    def test_processo_uti_rj_uses_official_excel_formula_after_weighted_sum(self):
        # UTI/RJ faz parte da mesma tabela de cadeia. Apenas os criterios
        # de pontuacao mudam; depois disso vale a mesma formula do DOCX.
        self.assertAlmostEqual(_processo_uti_rj(5.5), 1.10)
        self.assertAlmostEqual(_processo_uti_rj(4.5), 1.10)
        self.assertAlmostEqual(_processo_uti_rj(4.0), 1.10)
        self.assertAlmostEqual(_processo_uti_rj(3.0), 1.00)
        self.assertAlmostEqual(_processo_uti_rj(2.5), 0.90)
        self.assertAlmostEqual(_processo_uti_rj(1.5), 0.70)
        self.assertAlmostEqual(_processo_uti_rj(1.0), 0.80)
        self.assertAlmostEqual(_processo_uti_rj(0), 0.70)

    def test_uti_rj_row_applies_weighted_sum_with_official_formula(self):
        row = _db_row(
            setor="UTI RJ",
            escala="RJ",
            nota_mot=1.5,
            nota_pa=1,
            nota_cli=1.5,
            nota_policia=1.5,
        )
        cursor = _FakeCursor(rows=[row])
        conn = _FakeConnection([cursor])

        rows = get_fechamento_rows(conn, 4, 2026)

        self.assertEqual(rows[0]["processo"], "110%")
        self.assertEqual(rows[0]["final"], "4%")

    def test_uti_simples_row_applies_uti_table(self):
        row = _db_row(setor="UTI", escala="Verde", nota_mot=1, nota_pa=1, nota_cli=1, nota_policia=0)
        cursor = _FakeCursor(rows=[row])
        conn = _FakeConnection([cursor])

        rows = get_fechamento_rows(conn, 4, 2026)

        self.assertEqual(rows[0]["processo"], "100%")
        self.assertEqual(rows[0]["final"], "2%")

    def test_final_formula_matches_official_excel_formula_for_80_percent(self):
        row = _db_row(setor="UTI", escala="Verde", nota_mot=1, nota_pa=0, nota_cli=0, nota_policia=0)
        cursor = _FakeCursor(rows=[row])
        conn = _FakeConnection([cursor])

        rows = get_fechamento_rows(conn, 4, 2026)

        self.assertEqual(rows[0]["processo"], "80%")
        self.assertEqual(rows[0]["final"], "")

    def test_uti_rj_uses_same_process_formula_as_document(self):
        row = _db_row(setor="UTI RJ", escala="RJ", nota_mot=1.5, nota_pa=0, nota_cli=1.5, nota_policia=0)
        cursor = _FakeCursor(rows=[row])
        conn = _FakeConnection([cursor])

        rows = get_fechamento_rows(conn, 4, 2026)

        self.assertEqual(rows[0]["processo"], "100%")
        self.assertEqual(rows[0]["final"], "2%")

    def test_receptive_detection_handles_accents_and_variants(self):
        self.assertFalse(_is_receptive("Cadastro", ""))
        self.assertFalse(_is_receptive("Checklist", ""))
        self.assertFalse(_is_receptive("Célula", ""))
        self.assertFalse(_is_receptive("celula", ""))
        self.assertFalse(_is_receptive("celula_atendimento", ""))
        self.assertTrue(_is_receptive("", "MONDELEZ"))
        self.assertFalse(_is_receptive("UTI", "Verde"))
        self.assertFalse(_is_receptive("Distribuição", ""))
        self.assertFalse(_is_receptive("BAS", ""))

    def test_mondelez_receptive_goes_to_telefonica_column(self):
        row = _db_row(setor="Mondelez", escala="MONDELEZ-DIURNO", media_auditoria=8.5)
        cursor = _FakeCursor(rows=[row])
        conn = _FakeConnection([cursor])

        rows = get_fechamento_rows(conn, 4, 2026)

        self.assertEqual(rows[0]["telefonica"], "8.5")
        self.assertEqual(rows[0]["operacional"], "")
        self.assertEqual(rows[0]["huawei"], "-")

    def test_celula_with_accent_goes_to_operacional_column(self):
        row = _db_row(setor="Célula", escala="", media_auditoria=7.0)
        cursor = _FakeCursor(rows=[row])
        conn = _FakeConnection([cursor])

        rows = get_fechamento_rows(conn, 4, 2026)

        self.assertEqual(rows[0]["operacional"], "7.0")
        self.assertEqual(rows[0]["telefonica"], "")

    def test_export_contract_formats_excel_as_official_sheet(self):
        conn = _FakeConnection([
            _FakeCursor(rows=[
                _db_row(
                    setor="UTI RJ",
                    escala="RJ",
                    nota_mot=1.5,
                    nota_pa=1,
                    nota_cli=1.5,
                    nota_policia=1.5,
                    media_auditoria=8.25,
                )
            ])
        ])

        workbook_bytes = generate_fechamento_excel(lambda: conn, 4, 2026)
        wb = openpyxl.load_workbook(BytesIO(workbook_bytes), data_only=True)
        ws = wb["Planilha1"]

        self.assertTrue(conn.closed)
        self.assertEqual([cell.value for cell in ws[1]], [header for header, _ in HEADERS])
        self.assertIsNone(ws.freeze_panes)
        self.assertEqual(ws.max_column, 15)
        self.assertEqual(ws["E2"].value, 8.25)
        self.assertEqual(ws["E2"].number_format, "0.00")
        self.assertEqual(ws["L2"].value, 1.10)
        self.assertEqual(ws["L2"].number_format, "0%")
        self.assertEqual(ws["M2"].value, 0.04)
        self.assertEqual(ws["M2"].number_format, "0%")


if __name__ == "__main__":
    unittest.main()
