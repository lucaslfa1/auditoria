"""Testes para a migracao BBM -> Distribuicao (v1.3.74)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.seeds._archived.bbm_snapshot import dump_bbm_snapshot, load_bbm_snapshot


class TestBBMSnapshotRoundtrip(unittest.TestCase):
    """Snapshot helper round-trips JSON sem perda."""

    def test_dump_and_load_preserves_structure(self):
        sample = {
            "snapshot_date": "2026-05-18",
            "reason": "test",
            "sector": {"id": "bbm", "label": "BBM"},
            "alerts": [{"id": "BBM-PARADA-MOT", "sector_id": "bbm", "label": "x"}],
            "criteria": [{"alert_id": "BBM-PARADA-MOT", "label": "y", "weight": 1.0}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snap.json"
            dump_bbm_snapshot(sample, path)
            self.assertTrue(path.exists())
            loaded = load_bbm_snapshot(path)
            self.assertEqual(loaded["sector"]["id"], "bbm")
            self.assertEqual(len(loaded["alerts"]), 1)


class TestMigrationModuleShape(unittest.TestCase):
    """Smoke test: migration tem MIGRATION_NAME e apply callable."""

    def test_module_has_name_and_apply(self):
        from db.migration_steps import (
            m20260518_004_migrate_bbm_to_distribuicao as mig,
        )

        self.assertEqual(
            mig.MIGRATION_NAME,
            "m20260518_004_migrate_bbm_to_distribuicao",
        )
        self.assertTrue(callable(mig.apply))

    def test_residual_alias_migration_has_name_and_apply(self):
        from db.migration_steps import (
            m20260518_005_fix_bbm_organization_alias as mig,
        )

        self.assertEqual(
            mig.MIGRATION_NAME,
            "m20260518_005_fix_bbm_organization_alias",
        )
        self.assertTrue(callable(mig.apply))


class TestSectorAliasBootstrap(unittest.TestCase):
    """BBM vindo da organizacao Huawei deve cair em Distribuicao."""

    def test_organizacao_bbm_bootstrap_routes_to_distribuicao(self):
        import db.database as database

        matches = [
            row
            for row in database._SECTOR_ALIASES_BOOTSTRAP
            if row[0] == "organizacao_contains" and row[1] == "bbm"
        ]

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][2], "distribuicao")


class TestAlertIdAliases(unittest.TestCase):
    """Cada um dos 10 alertas BBM-* canonicaliza para DISTRIBUICAO-*."""

    BBM_TO_DIST = [
        ("BBM-PARADA-MOT", "DISTRIBUICAO-PARADA-MOT"),
        ("BBM-PARADA-CLI", "DISTRIBUICAO-PARADA-CLI"),
        ("BBM-DESVIO-MOT", "DISTRIBUICAO-DESVIO-MOT"),
        ("BBM-DESVIO-CLI", "DISTRIBUICAO-DESVIO-CLI"),
        ("BBM-POSICAO-MOT", "DISTRIBUICAO-POSICAO-MOT"),
        ("BBM-POSICAO-CLI", "DISTRIBUICAO-POSICAO-CLI"),
        ("BBM-PRIORITARIO-MOT", "DISTRIBUICAO-PRIORITARIO-MOT"),
        ("BBM-PRIORITARIO-CLI", "DISTRIBUICAO-PRIORITARIO-CLI"),
        ("BBM-PRIORITARIO-POLICIA", "DISTRIBUICAO-PRIORITARIO-POLICIA"),
        ("BBM-PONTO-APOIO", "DISTRIBUICAO-PONTO-APOIO"),
    ]

    def test_all_bbm_alerts_canonicalize_to_distribuicao(self):
        from core.classification import canonicalize_alert_id

        for bbm_id, expected in self.BBM_TO_DIST:
            with self.subTest(bbm_id=bbm_id):
                self.assertEqual(canonicalize_alert_id(bbm_id), expected)

    def test_operational_structures_exclude_bbm(self):
        import core.classification as classification

        self.assertNotIn("bbm", classification._OPERATIONAL_SECTORS)
        self.assertNotIn("bbm", classification._OPERATIONAL_ALERT_PREFIXES)


class TestCatalogAndPromptHaveNoBBM(unittest.TestCase):
    """Pos-migracao: catalogo do DB e prompt da IA nao mencionam BBM."""

    def test_catalog_does_not_contain_bbm(self):
        from core.classification import load_audit_criteria_catalog

        load_audit_criteria_catalog.cache_clear()
        catalog = load_audit_criteria_catalog()
        self.assertNotIn("bbm", catalog)

    def test_prompt_does_not_contain_bbm_alerts(self):
        from core.classification import build_sectors_and_alerts_prompt

        build_sectors_and_alerts_prompt.cache_clear()
        prompt = build_sectors_and_alerts_prompt()
        self.assertNotIn("BBM-", prompt)


if __name__ == "__main__":
    unittest.main()
