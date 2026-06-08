import inspect
import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import export_planejamento, export_planejamento_pdf, report_exports
from core.export_gestores import convert_audit_to_gestores_row
from db.domain_constants import AUDIT_STATUS_APPROVED


class _FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.sql = ""
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


class _FakeDoc:
    last_story = None

    def __init__(self, *args, **kwargs):
        pass

    def build(self, story):
        _FakeDoc.last_story = story


class _FakeTable:
    created = []

    def __init__(self, data, *args, **kwargs):
        self.data = data
        _FakeTable.created.append(self)

    def setStyle(self, style):
        self.style = style


class TestExportHardening(unittest.TestCase):
    def test_planejamento_sql_uses_cte_range_and_single_colaborador_join(self):
        cursor = _FakeCursor(rows=[])
        conn = _FakeConnection(cursor)

        export_planejamento._fetch_operator_audit_scores(lambda: conn, 4, 2026)

        self.assertIn("WITH audit_stats AS", cursor.sql)
        self.assertIn("GROUP BY operator_name", cursor.sql)
        self.assertIn("SELECT id FROM colaboradores c", cursor.sql)
        self.assertIn("COALESCE(audit_date, timestamp)::TIMESTAMP >= %s", cursor.sql)
        self.assertIn("COALESCE(audit_date, timestamp)::TIMESTAMP < %s", cursor.sql)
        self.assertNotIn("EXTRACT(MONTH", cursor.sql)
        self.assertEqual(cursor.params, [AUDIT_STATUS_APPROVED, "2026-04-01", "2026-05-01"])
        self.assertTrue(conn.closed)

    def test_planejamento_pdf_sql_returns_media_percentual_and_handles_december(self):
        cursor = _FakeCursor(rows=[
            {
                "operator_name": "Operador A",
                "media_nota": 7.5,
                "max_score": 10,
                "total_ligacoes": 2,
                "media_percentual": 100,
            }
        ])
        conn = _FakeConnection(cursor)

        result = export_planejamento_pdf._fetch_operator_data(lambda: conn, 12, 2026)

        self.assertIn("media_percentual", cursor.sql)
        self.assertNotIn("EXTRACT(YEAR", cursor.sql)
        self.assertEqual(cursor.params, [AUDIT_STATUS_APPROVED, "2026-12-01", "2027-01-01"])
        self.assertEqual(result["Operador A"]["media_percentual"], 100)

    def test_planejamento_pdf_kpis_use_database_percentual(self):
        _FakeTable.created = []
        operators = {
            "Operador A": {
                "media_nota": 7.5,
                "max_score": 10,
                "total_ligacoes": 2,
                "media_percentual": 100,
                "status": "ATIVO",
            }
        }

        with patch("core.export_planejamento_pdf._fetch_operator_data", return_value=operators):
            with patch("core.export_planejamento_pdf.SimpleDocTemplate", _FakeDoc):
                with patch("core.export_planejamento_pdf.Table", _FakeTable):
                    export_planejamento_pdf.generate_planejamento_pdf(lambda: None, 4, 2026)

        kpi_table = _FakeTable.created[0].data
        self.assertEqual(kpi_table[0][2].getPlainText(), "100.0%")
        self.assertEqual(kpi_table[0][3].getPlainText(), "100%")

    def test_report_exports_no_canvas_truncation_or_dynamic_openpyxl_import(self):
        report_pdf = inspect.getsource(report_exports.generate_pdf_report)
        transcription_pdf = inspect.getsource(report_exports.generate_pdf_transcription)
        excel = inspect.getsource(report_exports.generate_excel_report)

        self.assertIn("SimpleDocTemplate", report_pdf)
        self.assertIn("Paragraph", report_pdf)
        self.assertNotIn("canvas.Canvas", report_pdf)
        self.assertNotIn("[:80]", report_pdf)
        self.assertIn("SimpleDocTemplate", transcription_pdf)
        self.assertNotIn("canvas.Canvas", transcription_pdf)
        self.assertNotIn("[:100]", transcription_pdf)
        self.assertNotIn("__import__", excel)

    def test_gestores_export_strips_timezone_for_openpyxl(self):
        row = convert_audit_to_gestores_row(
            {
                "timestamp": "2026-04-12T10:30:00+00:00",
                "operator_name": "Operador A",
                "operator_id": "123",
                "details": [],
            },
            1,
            {},
        )

        self.assertIsNone(row["Hora Atual"].tzinfo)


if __name__ == "__main__":
    unittest.main()
