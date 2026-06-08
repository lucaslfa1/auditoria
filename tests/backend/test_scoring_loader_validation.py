import os
import sys
import tempfile
import textwrap
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.scoring_loader import load_scoring_rules


class TestScoringLoaderValidation(unittest.TestCase):
    def test_invalid_weight_above_bound_raises(self):
        yaml_content = textwrap.dedent(
            """
            scoring_rules:
              pass: 1.0
              partial: 0.5
              fail: 0.0
              na: null
            sectors:
              - id: bas
                label: BAS
            alerts:
              - id: BAS-TESTE
                sector: bas
                label: Teste
                criteria:
                  - label: Critério 1
                    weight: 11
            """
        )

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
            handle.write(yaml_content)
            temp_path = handle.name

        with self.assertRaises(ValueError):
            load_scoring_rules(temp_path)


if __name__ == "__main__":
    unittest.main()
