import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.export_gestores import load_pesos
from core.gestores_mapping import get_gestores_alert_catalog, resolve_gestores_alert
from db.scoring_loader import load_scoring_rules


class TestGestoresExportConfig(unittest.TestCase):
    def test_yaml_alert_catalog_has_full_coverage(self):
        rules = load_scoring_rules()
        catalog = get_gestores_alert_catalog()

        self.assertEqual(len(catalog), len(rules["alerts"]))
        self.assertTrue(all(item["gestores_label"] for item in catalog.values()))
        self.assertTrue(all(item["contact_type"] for item in catalog.values()))

    def test_resolve_by_label_uses_yaml_catalog(self):
        gestores_label, contact_type, resolved_id = resolve_gestores_alert(
            alert_id=None,
            alert_label="Monitoramento I - Receptivo",
        )

        self.assertEqual(resolved_id, "MONDELEZ-MONITORAMENTO-I")
        self.assertEqual(gestores_label, "MONITORAMENTO I")
        self.assertEqual(contact_type, "Receptiva")

    def test_load_pesos_fails_fast_when_file_is_missing(self):
        missing_path = Path("C:/missing/pesos_gestores.json")
        with patch("core.export_gestores.PESOS_JSON_PATH", missing_path):
            with self.assertRaises(FileNotFoundError):
                load_pesos()


if __name__ == "__main__":
    unittest.main()
