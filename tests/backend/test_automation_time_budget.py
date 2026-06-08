import os
import unittest
from unittest.mock import patch

from core.automation import _get_automation_audit_time_budget_seconds


class TestAutomationTimeBudgetCap(unittest.TestCase):
    """v1.3.100: cap subido de 540 para 1800 (30 min) pra permitir multiplos
    items grandes (audios Huawei tipicos transcrevem em ~470-520s cada)."""

    def test_env_set_wins(self):
        env = {"AUTOMATION_AUDIT_TIME_BUDGET_SECONDS": "1200"}
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "core.automation.database.get_config_value",
                return_value="9999",
            ) as mock_db:
                self.assertEqual(_get_automation_audit_time_budget_seconds(), 1200)
                mock_db.assert_not_called()

    def test_env_empty_falls_back_to_db(self):
        env = {"AUTOMATION_AUDIT_TIME_BUDGET_SECONDS": ""}
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "core.automation.database.get_config_value",
                return_value="1500",
            ):
                self.assertEqual(_get_automation_audit_time_budget_seconds(), 1500)

    def test_cap_max_1800(self):
        env = {"AUTOMATION_AUDIT_TIME_BUDGET_SECONDS": "9999"}
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(_get_automation_audit_time_budget_seconds(), 1800)

    def test_cap_min_60(self):
        env = {"AUTOMATION_AUDIT_TIME_BUDGET_SECONDS": "10"}
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(_get_automation_audit_time_budget_seconds(), 60)


if __name__ == "__main__":
    unittest.main()
