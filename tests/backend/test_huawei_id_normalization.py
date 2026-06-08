import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.common import normalize_huawei_agent_id
from repositories import operators


class TestHuaweiIdNormalization(unittest.TestCase):
    def test_normalize_huawei_agent_id_removes_spurious_decimal_zero(self):
        self.assertEqual(normalize_huawei_agent_id("182.0"), "182")
        self.assertEqual(normalize_huawei_agent_id("00182.000"), "00182")
        self.assertEqual(normalize_huawei_agent_id(182.0), "182")

    def test_normalize_huawei_agent_id_preserves_non_numeric_ids(self):
        self.assertEqual(normalize_huawei_agent_id("AGENT.0"), "AGENT.0")
        self.assertEqual(normalize_huawei_agent_id("182.5"), "182.5")

    def test_coerce_huawei_and_telefonia_ids_normalizes_both_fields(self):
        self.assertEqual(
            operators._coerce_huawei_and_telefonia_ids("2447.0", ""),
            ("2447", "2447"),
        )
        self.assertEqual(
            operators._coerce_huawei_and_telefonia_ids("", "3001.0"),
            ("3001", "3001"),
        )


if __name__ == "__main__":
    unittest.main()
