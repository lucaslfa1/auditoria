import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from core.automation_engine import _build_cycle_volume_plan
from core.huawei.automation_config import DEFAULT_HUAWEI_SYNC_MIN_DURATION_SECONDS


class TestAutomationVolumePlan(unittest.TestCase):
    def test_volume_plan_separa_meta_solicitada_possivel_e_executada(self):
        sync_result = {
            "status": "partial",
            "executados": [
                {
                    "date_str": "20260628",
                    "result": {
                        "chamadas_validas_pos_filtro": 52,
                        "candidatos_download": 52,
                        "baixadas": 34,
                        "enfileiradas": 34,
                        "ignoradas_cota_mensal_pre_download": 1109,
                        "ignoradas_duracao_minima": 663,
                    },
                }
            ],
        }
        audit_result = {
            "requested_audits": 200,
            "target_count": 200,
            "completed": 34,
        }

        plan = _build_cycle_volume_plan(
            sync_result,
            audit_result,
            baixadas=34,
            auditadas=34,
            descartados=0,
        )

        self.assertEqual(plan["requested_audits"], 200)
        self.assertEqual(plan["eligible_after_filters"], 52)
        self.assertEqual(plan["possible_audits"], 52)
        self.assertEqual(plan["completed_audits"], 34)
        self.assertEqual(plan["gap_reason"], "volume_elegivel_insuficiente")
        self.assertEqual(plan["filter_losses"][0]["key"], "ignoradas_cota_mensal_pre_download")

    def test_duration_filter_default_reduced_by_ten_seconds(self):
        self.assertEqual(DEFAULT_HUAWEI_SYNC_MIN_DURATION_SECONDS, 110)


if __name__ == "__main__":
    unittest.main()
