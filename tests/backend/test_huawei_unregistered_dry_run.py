import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import huawei_unregistered_dry_run as dry_run


class TestHuaweiUnregisteredDryRun(unittest.TestCase):
    def test_extract_candidate_huawei_ids_normalizes_and_deduplicates(self):
        result = dry_run.extract_candidate_huawei_ids(
            {
                "operator_id_huawei_real": "189.0",
                "huawei_work_no": "189",
                "operator_id": "99999",
                "agentId": "",
                "workNo": None,
            }
        )

        self.assertEqual(result, ["189", "99999"])

    def test_build_unregistered_items_accepts_registered_huawei_id(self):
        rows = [
            {
                "id": 1,
                "input_hash": "hash-1",
                "nome_arquivo": "call.wav",
                "status": "pending",
                "operador_previsto": "Amanda Muslera",
                "metadata_json": {
                    "origem": "huawei_sync",
                    "operator_id_huawei_real": "189",
                    "huawei_call_id": "call-1",
                },
            }
        ]
        official = [{"nome": "Amanda Muslera", "id_huawei": "189"}]

        self.assertEqual(dry_run.build_unregistered_items(rows, official), [])

    def test_build_unregistered_items_flags_name_only_match(self):
        rows = [
            {
                "id": 2,
                "input_hash": "hash-2",
                "nome_arquivo": "call.wav",
                "status": "pending",
                "operador_previsto": "Amanda Muslera",
                "metadata_json": {
                    "origem": "huawei_sync",
                    "operator_id_huawei_real": "99999",
                    "huawei_begin_time": "2026-04-29 23:30:00",
                    "huawei_call_id": "call-2",
                },
            }
        ]
        official = [{"nome": "Amanda Muslera", "id_huawei": "189"}]

        result = dry_run.build_unregistered_items(rows, official)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["candidate_huawei_ids"], ["99999"])
        self.assertTrue(result[0]["name_matches_official"])
        self.assertTrue(result[0]["reported_match"])
        self.assertEqual(result[0]["call_started_at_sp"], "29/04/2026 23:30:00")

    def test_build_unregistered_items_flags_missing_huawei_id(self):
        rows = [
            {
                "id": 3,
                "input_hash": "hash-3",
                "nome_arquivo": "call.wav",
                "status": "pending",
                "operador_previsto": "Operador sem cadastro",
                "metadata_json": {
                    "origem": "huawei_sync",
                    "huawei_call_id": "call-3",
                },
            }
        ]
        official = [{"nome": "Amanda Muslera", "id_huawei": "189"}]

        result = dry_run.build_unregistered_items(rows, official)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["candidate_huawei_ids"], [])
        self.assertFalse(result[0]["name_matches_official"])


if __name__ == "__main__":
    unittest.main()
