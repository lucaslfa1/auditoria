import os
import sys
import unittest
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestReportExportsPersistence(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_report_exports_{uuid.uuid4().hex}.db",
        )
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_save_and_list_report_export(self):
        export_id = database.save_report_export(
            report_kind="audit_report",
            file_format="pdf",
            filename="auditoria_teste.pdf",
            media_type="application/pdf",
            generated_by="admin",
            operator_name="Operador QA",
            operator_id="MAT-001",
            alert_id="4.1.1",
            alert_label="Alerta QA",
            sector_id="logistica",
            score=8.5,
            max_score=10.0,
            source_type="audio",
            audit_timestamp="2026-03-04T18:00:00",
            file_size_bytes=2048,
            metadata={"origin": "unit_test"},
        )
        self.assertIsInstance(export_id, int)

        records = database.list_report_exports(limit=10)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["id"], export_id)
        self.assertEqual(record["report_kind"], "audit_report")
        self.assertEqual(record["file_format"], "pdf")
        self.assertEqual(record["operator_id"], "MAT-001")
        self.assertEqual(record["file_size_bytes"], 2048)
        self.assertEqual(record["metadata"], {"origin": "unit_test"})

    def test_report_export_filters(self):
        database.save_report_export(
            report_kind="transcription",
            file_format="docx",
            filename="transcricao.docx",
            operator_name="Alice",
        )
        database.save_report_export(
            report_kind="gestores",
            file_format="xlsx",
            filename="gestores.xlsx",
            operator_name="Bruno",
        )

        by_kind = database.list_report_exports(report_kind="gestores")
        self.assertEqual(len(by_kind), 1)
        self.assertEqual(by_kind[0]["report_kind"], "gestores")

        by_format = database.list_report_exports(file_format="docx")
        self.assertEqual(len(by_format), 1)
        self.assertEqual(by_format[0]["file_format"], "docx")

        by_operator = database.list_report_exports(operator_name="bru")
        self.assertEqual(len(by_operator), 1)
        self.assertEqual(by_operator[0]["operator_name"], "Bruno")


if __name__ == "__main__":
    unittest.main()
