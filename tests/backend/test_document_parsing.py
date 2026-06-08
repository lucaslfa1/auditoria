"""Testes do parser de documentos (PDF de chat Service Cloud).

Fixture real: texto cru extraído da auditoria 92 (`5 - RECEPTIVO.pdf`, setor Célula),
preservado antes de deletar o registro do banco.
"""
import unittest
from pathlib import Path

from core.document_parsing import (
    detect_document_format,
    parse_document,
    parse_service_cloud,
    parse_whatsapp_log,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "pdf_chat" / "auditoria_92_servicecloud_raw.txt"
)


def _raw() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class DetectFormatTests(unittest.TestCase):
    def test_detects_service_cloud(self):
        self.assertEqual(detect_document_format(_raw()), "service_cloud")

    def test_detects_whatsapp(self):
        text = (
            "[04/05/2026 06:41:51] Rafael: Bom dia\n"
            "[04/05/2026 06:42:00] Selma: Ola, em que posso ajudar?"
        )
        self.assertEqual(detect_document_format(text), "whatsapp")

    def test_generic_when_unknown(self):
        self.assertEqual(
            detect_document_format("apenas um texto qualquer sem estrutura de chat"),
            "generic",
        )

    def test_empty_is_generic(self):
        self.assertEqual(detect_document_format("   "), "generic")


class ServiceCloudCleaningTests(unittest.TestCase):
    def setUp(self):
        self.segments = parse_document(_raw(), operator_name="Atendente Exemplo")
        self.full = "\n".join(seg["text"] for seg in self.segments)

    def test_removes_print_footers(self):
        self.assertNotIn("Service Cloud", self.full)
        self.assertNotIn("file:///", self.full)
        self.assertNotIn(".html", self.full)

    def test_removes_read_receipts(self):
        self.assertNotIn("Leitura", self.full)

    def test_dewraps_broken_words(self):
        # "ao n\nosso" -> "ao nosso"; "correspo\nndente" -> "correspondente"; etc.
        self.assertIn("nosso canal", self.full)
        self.assertIn("correspondente", self.full)
        self.assertIn("Agendado", self.full)
        self.assertIn("Atendimento", self.full)
        self.assertIn("favor", self.full)  # "Por f\navor"
        self.assertIn("mais", self.full)  # "mai\ns?"

    def test_no_midword_newline_artifacts(self):
        self.assertNotIn("ao n\nosso", self.full)
        self.assertNotIn("correspo\nndente", self.full)
        self.assertNotIn("embarqu\ne", self.full)


class ServiceCloudStructureTests(unittest.TestCase):
    def setUp(self):
        self.segments = parse_document(_raw(), operator_name="Atendente Exemplo")

    def test_has_multiple_segments(self):
        self.assertGreaterEqual(len(self.segments), 8)

    def test_canonical_roles_present(self):
        prefixes = {
            seg["text"].split(":", 1)[0] for seg in self.segments if ":" in seg["text"]
        }
        self.assertIn("Operador", prefixes)
        self.assertIn("Cliente", prefixes)
        self.assertIn("Bot", prefixes)

    def test_operator_line_attributed(self):
        operador = " ".join(
            seg["text"] for seg in self.segments if seg["text"].startswith("Operador:")
        )
        self.assertIn("Qual a AE", operador)

    def test_bot_greeting_attributed(self):
        bot = " ".join(
            seg["text"] for seg in self.segments if seg["text"].startswith("Bot:")
        )
        self.assertIn("Tati", bot)

    def test_chronological_order(self):
        starts = [seg["start"] for seg in self.segments]
        self.assertEqual(starts, sorted(starts))

    def test_segments_have_clock_time(self):
        for seg in self.segments:
            self.assertRegex(seg["start"], r"^\d{2}:\d{2}:\d{2}$")
            self.assertEqual(seg["start"], seg["end"])

    def test_no_empty_body(self):
        for seg in self.segments:
            body = seg["text"].split(":", 1)[-1].strip()
            self.assertTrue(body, f"segmento sem corpo: {seg!r}")


class WhatsAppRegressionTests(unittest.TestCase):
    def test_parses_whatsapp(self):
        text = (
            "[04/05/2026 06:41:51] Rafael: Bom dia\n"
            "[04/05/2026 06:42:00] Selma: Ola"
        )
        segs = parse_whatsapp_log(text)
        self.assertEqual(len(segs), 2)
        self.assertIn("Rafael", segs[0]["text"])
        self.assertEqual(segs[0]["start"], "06:41")

    def test_non_whatsapp_returns_empty(self):
        self.assertEqual(parse_whatsapp_log("texto sem timestamps"), [])


class GenericFallbackTests(unittest.TestCase):
    def test_generic_single_segment(self):
        segs = parse_document("texto solto sem formato de chat")
        self.assertEqual(len(segs), 1)
        self.assertIn("texto solto", segs[0]["text"])

    def test_generic_strips_footers(self):
        segs = parse_document("06/05/2026, 15:59 Service Cloud\nconteudo util")
        self.assertEqual(len(segs), 1)
        self.assertNotIn("Service Cloud", segs[0]["text"])
        self.assertIn("conteudo util", segs[0]["text"])


if __name__ == "__main__":
    unittest.main()
