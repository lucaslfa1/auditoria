import os
import unittest
from unittest.mock import patch

from core.automation import _get_automation_item_timeout_seconds


class TestAutomationItemTimeoutDbFallback(unittest.TestCase):
    """v1.3.99: _get_automation_item_timeout_seconds deve cair pro DB quando
    env vazio, pra ficar consistente com batch_size e time_budget.
    """

    def test_env_set_wins(self):
        env = {"AUTOMATION_ITEM_TIMEOUT_SECONDS": "300"}
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "core.automation.database.get_config_value",
                return_value="999",
            ) as mock_db:
                self.assertEqual(_get_automation_item_timeout_seconds(), 300)
                mock_db.assert_not_called()

    def test_env_empty_falls_back_to_db(self):
        env = {"AUTOMATION_ITEM_TIMEOUT_SECONDS": ""}
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "core.automation.database.get_config_value",
                return_value="540",
            ):
                self.assertEqual(_get_automation_item_timeout_seconds(), 540)

    def test_env_missing_falls_back_to_db(self):
        env = dict(os.environ)
        env.pop("AUTOMATION_ITEM_TIMEOUT_SECONDS", None)
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "core.automation.database.get_config_value",
                return_value="540",
            ):
                self.assertEqual(_get_automation_item_timeout_seconds(), 540)

    def test_env_missing_and_db_empty_uses_default_480(self):
        env = dict(os.environ)
        env.pop("AUTOMATION_ITEM_TIMEOUT_SECONDS", None)
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "core.automation.database.get_config_value",
                return_value="480",
            ):
                self.assertEqual(_get_automation_item_timeout_seconds(), 480)

    def test_cap_max_900(self):
        """v1.3.100: cap subido de 540 para 900 (15 min) pra acomodar
        audios Huawei tipicos que levam 8-9 min de transcricao."""
        env = {"AUTOMATION_ITEM_TIMEOUT_SECONDS": "9999"}
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(_get_automation_item_timeout_seconds(), 900)

    def test_cap_min_60(self):
        env = {"AUTOMATION_ITEM_TIMEOUT_SECONDS": "10"}
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(_get_automation_item_timeout_seconds(), 60)


if __name__ == "__main__":
    unittest.main()
