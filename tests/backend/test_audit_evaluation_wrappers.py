import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import services


class TestAuditEvaluationWrappers(unittest.IsolatedAsyncioTestCase):
    def test_get_audit_system_prompt_delegates(self):
        dependencies = MagicMock(spec=services.AuditEvaluationDependencies)
        with patch("core.evaluation._get_audit_evaluation_dependencies", return_value=dependencies) as dependency_factory:
            with patch("core.evaluation.build_audit_system_prompt", return_value="prompt") as mocked:
                result = services.get_audit_system_prompt(
                    "contexto",
                    "criterios",
                    {"score": 0.4},
                    "SEC01",
                )

        dependency_factory.assert_called_once_with()
        self.assertEqual(result, "prompt")
        args, kwargs = mocked.call_args
        self.assertEqual(args, ("contexto", "criterios", {"score": 0.4}, "SEC01"))
        self.assertIs(kwargs["dependencies"], dependencies)

    async def test_evaluate_transcription_delegates(self):
        alert = MagicMock()
        criteria = [MagicMock()]
        transcription = [{"text": "ok"}]
        dependencies = MagicMock(spec=services.AuditEvaluationDependencies)

        with patch("core.evaluation._get_audit_evaluation_dependencies", return_value=dependencies) as dependency_factory:
            with patch("core.evaluation.run_ai_audit_evaluation", new=AsyncMock(return_value={"score": 10})) as mocked:
                result = await services.evaluate_transcription(
                    transcription,
                    alert,
                    criteria,
                    "Ana",
                    "Carlos",
                    {"score": 0.8},
                    "SEC01",
                )

        dependency_factory.assert_called_once_with()
        self.assertEqual(result, {"score": 10})
        args, kwargs = mocked.call_args
        self.assertEqual(
            args,
            (transcription, alert, criteria, "Ana", "Carlos", {"score": 0.8}, "SEC01"),
        )
        self.assertIs(kwargs["dependencies"], dependencies)

    async def test_evaluate_with_azure_delegates(self):
        alert = MagicMock()
        criteria = [MagicMock()]
        transcription = [{"text": "ok"}]
        dependencies = MagicMock(spec=services.AuditEvaluationDependencies)

        with patch("core.evaluation._get_audit_evaluation_dependencies", return_value=dependencies) as dependency_factory:
            with patch("core.evaluation.run_azure_audit_evaluation", new=AsyncMock(return_value={"score": 20})) as mocked:
                result = await services.evaluate_with_azure(
                    transcription,
                    alert,
                    criteria,
                    "Ana",
                    {"score": 0.6},
                    "SEC02",
                )

        dependency_factory.assert_called_once_with()
        self.assertEqual(result, {"score": 20})
        args, kwargs = mocked.call_args
        self.assertEqual(
            args,
            (transcription, alert, criteria, "Ana", {"score": 0.6}, "SEC02"),
        )
        self.assertIs(kwargs["dependencies"], dependencies)

    async def test_evaluate_with_ai_priority_delegates(self):
        alert = MagicMock()
        criteria = [MagicMock()]
        transcription = [{"text": "ok"}]
        dependencies = MagicMock(spec=services.AuditEvaluationDependencies)

        with patch("core.evaluation._get_audit_evaluation_dependencies", return_value=dependencies) as dependency_factory:
            with patch("core.evaluation.run_prioritized_audit_evaluation", new=AsyncMock(return_value={"score": 30})) as mocked:
                result = await services.evaluate_with_ai_priority(
                    transcription,
                    alert,
                    criteria,
                    "Ana",
                    {"score": 0.9},
                    "SEC03",
                )

        dependency_factory.assert_called_once_with()
        self.assertEqual(result, {"score": 30})
        args, kwargs = mocked.call_args
        self.assertEqual(
            args,
            (transcription, alert, criteria, "Ana", {"score": 0.9}, "SEC03"),
        )
        self.assertIs(kwargs["dependencies"], dependencies)


class TestReportExportWrappers(unittest.TestCase):
    def test_generate_excel_report_delegates(self):
        result = MagicMock()
        with patch("core.export.build_excel_report", return_value="excel") as mocked:
            response = services.generate_excel_report(result)

        self.assertEqual(response, "excel")
        mocked.assert_called_once_with(result)

    def test_generate_docx_report_delegates(self):
        result = MagicMock()
        with patch("core.export.build_docx_report", return_value="docx") as mocked:
            response = services.generate_docx_report(result)

        self.assertEqual(response, "docx")
        mocked.assert_called_once_with(result)

    def test_generate_docx_transcription_delegates(self):
        result = MagicMock()
        with patch("core.export.build_docx_transcription", return_value="docx-transcription") as mocked:
            response = services.generate_docx_transcription(result)

        self.assertEqual(response, "docx-transcription")
        mocked.assert_called_once_with(result)

    def test_generate_pdf_report_delegates(self):
        result = MagicMock()
        with patch("core.export.build_pdf_report", return_value="pdf") as mocked:
            response = services.generate_pdf_report(result)

        self.assertEqual(response, "pdf")
        mocked.assert_called_once_with(result)

    def test_generate_pdf_transcription_delegates(self):
        result = MagicMock()
        with patch("core.export.build_pdf_transcription", return_value="pdf-transcription") as mocked:
            response = services.generate_pdf_transcription(result)

        self.assertEqual(response, "pdf-transcription")
        mocked.assert_called_once_with(result)


if __name__ == "__main__":
    unittest.main()
