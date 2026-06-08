import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from db.connection import get_connection

    _pg_available = True
    try:
        _test_conn = get_connection()
        _test_conn.close()
    except Exception:
        _pg_available = False
except Exception:
    _pg_available = False

from repositories.admin_criteria import get_export_format


@unittest.skipUnless(_pg_available, "PostgreSQL not available")
class TestAdminCriteriaRepository(unittest.TestCase):
    def test_get_export_format_returns_sectors_with_alerts_and_criteria(self):
        payload = get_export_format(get_connection)

        self.assertIn("sectors", payload)
        self.assertIsInstance(payload["sectors"], list)
        if payload["sectors"]:
            sector = payload["sectors"][0]
            self.assertIn("id", sector)
            self.assertIn("alerts", sector)


if __name__ == "__main__":
    unittest.main()
