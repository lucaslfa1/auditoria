"""Tests to prevent drift between YAML source of truth, code, and documentation.

These tests ensure that changes to scoring_rules.yaml are reflected in:
- RAG training documents
- gestores_mapping.py catalog
- export_gestores.py (no hardcoded maps)
"""

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.scoring_loader import load_scoring_rules
from core.gestores_mapping import get_gestores_alert_catalog

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
_RAG_CRITERIOS = _BACKEND_DIR / "data" / "rag_training" / "criterios_auditoria.md"
_EXPORT_GESTORES = _BACKEND_DIR / "core" / "export_gestores.py"


class TestYamlDocDrift(unittest.TestCase):
    """Prevent silent divergence between YAML and documentation."""

    def test_yaml_alert_count_matches_rag_doc(self):
        """The RAG criterios doc must declare the same number of alerts as the YAML."""
        rules = load_scoring_rules()
        yaml_count = len(rules["alerts"])

        self.assertTrue(_RAG_CRITERIOS.exists(), f"RAG doc not found: {_RAG_CRITERIOS}")
        content = _RAG_CRITERIOS.read_text(encoding="utf-8")

        match = re.search(r"Total de alertas definidos:\s*(\d+)", content)
        self.assertIsNotNone(match, "RAG doc does not contain 'Total de alertas definidos: N'")
        rag_count = int(match.group(1))

        self.assertEqual(
            yaml_count,
            rag_count,
            f"YAML has {yaml_count} alerts but RAG doc declares {rag_count}. "
            "Regenerate criterios_auditoria.md from the YAML.",
        )

    def test_yaml_alert_ids_present_in_rag_doc(self):
        """Every alert ID from the YAML must appear in the RAG criterios doc."""
        rules = load_scoring_rules()
        content = _RAG_CRITERIOS.read_text(encoding="utf-8")

        missing = []
        for alert in rules["alerts"]:
            alert_id = alert["id"]
            if alert_id not in content:
                missing.append(alert_id)

        self.assertEqual(
            missing,
            [],
            f"Alert IDs missing from RAG doc: {missing}. "
            "Regenerate criterios_auditoria.md.",
        )

    def test_export_gestores_has_no_hardcoded_alert_map(self):
        """export_gestores.py must NOT contain a hardcoded ALERT_MAP constant."""
        source = _EXPORT_GESTORES.read_text(encoding="utf-8")

        self.assertNotIn(
            "ALERT_MAP",
            source,
            "export_gestores.py still contains ALERT_MAP. "
            "The alert catalog must come from gestores_mapping.py.",
        )

    def test_gestores_mapping_covers_all_yaml_alerts(self):
        """The gestores mapping catalog must cover every YAML alert 1:1."""
        rules = load_scoring_rules()
        catalog = get_gestores_alert_catalog()

        yaml_ids = {a["id"] for a in rules["alerts"]}
        catalog_ids = set(catalog.keys())

        self.assertEqual(
            yaml_ids,
            catalog_ids,
            f"YAML IDs not in catalog: {yaml_ids - catalog_ids}. "
            f"Catalog IDs not in YAML: {catalog_ids - yaml_ids}.",
        )

        # Also check that every entry has required metadata
        for alert_id, meta in catalog.items():
            self.assertTrue(
                meta.get("gestores_label"),
                f"Catalog entry {alert_id} has empty gestores_label",
            )
            self.assertTrue(
                meta.get("contact_type"),
                f"Catalog entry {alert_id} has empty contact_type",
            )

    def test_sector_map_not_duplicated_in_export(self):
        """export_gestores.py must not redefine SECTOR_MAP (it imports from gestores_mapping)."""
        source = _EXPORT_GESTORES.read_text(encoding="utf-8")

        # A local SECTOR_MAP = { ... } assignment means duplication
        # The import `from core.gestores_mapping import SECTOR_MAP` is fine
        assignments = re.findall(r"^SECTOR_MAP\s*=\s*\{", source, re.MULTILINE)
        self.assertEqual(
            len(assignments),
            0,
            "export_gestores.py defines its own SECTOR_MAP. "
            "It should import from gestores_mapping.py only.",
        )


if __name__ == "__main__":
    unittest.main()
