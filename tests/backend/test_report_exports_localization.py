import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.report_exports import _format_detail_status


class ReportExportsLocalizationTests(unittest.TestCase):
    def test_format_detail_status_uses_portuguese_business_labels(self):
        self.assertEqual(_format_detail_status('pass'), 'Atende')
        self.assertEqual(_format_detail_status('fail'), 'Não atende')
        self.assertEqual(_format_detail_status('na'), 'Atende')
        self.assertEqual(_format_detail_status('partial'), 'Não atende')


if __name__ == '__main__':
    unittest.main()
