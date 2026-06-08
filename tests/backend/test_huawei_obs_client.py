import os
import sys
import unittest
from unittest.mock import AsyncMock, call

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.huawei_obs_client import HuaweiOBSClient


class TestHuaweiOBSClient(unittest.IsolatedAsyncioTestCase):
    async def test_baixar_voice_por_callid_tenta_prefixos_na_ordem(self):
        client = HuaweiOBSClient("ak", "sk", "bucket")
        client._candidate_dates = lambda begin_time, end_time=None: ["20260425"]
        client._date_with_neighbors = lambda begin_time, end_time=None: ["20260425"]
        client.listar_v3_por_prefixo = AsyncMock(
            side_effect=[
                [],
                [
                    "Voice/20260425/0016996299520/20260425120000-other.V3",
                    "Voice/20260425/0016996299520/20260425120000-1762373580-26728.V3",
                ],
            ]
        )
        client._download_object = AsyncMock(return_value=b"RIFFdata")

        result = await client.baixar_voice_por_callid(
            call_id="1762373580-26728",
            prefixes=["011139033478", "0016996299520", "666"],
            begin_time=1762373580000,
        )

        self.assertEqual(result, b"RIFFdata")
        self.assertEqual(
            client.listar_v3_por_prefixo.await_args_list,
            [
                call("20260425", "011139033478"),
                call("20260425", "0016996299520"),
            ],
        )
        client._download_object.assert_awaited_once_with(
            "Voice/20260425/0016996299520/20260425120000-1762373580-26728.V3"
        )

    async def test_baixar_voice_por_callid_mantem_agent_id_legado(self):
        client = HuaweiOBSClient("ak", "sk", "bucket")
        client._candidate_dates = lambda begin_time, end_time=None: ["20260425"]
        client._date_with_neighbors = lambda begin_time, end_time=None: ["20260425"]
        client.listar_v3_por_prefixo = AsyncMock(
            return_value=["Voice/20260425/666/20260425120000-1762373580-26728.V3"]
        )
        client._download_object = AsyncMock(return_value=b"RIFFdata")

        result = await client.baixar_voice_por_callid(
            call_id="1762373580-26728",
            agent_id="666",
            begin_time=1762373580000,
        )

        self.assertEqual(result, b"RIFFdata")
        client.listar_v3_por_prefixo.assert_awaited_once_with("20260425", "666")

    def test_normalize_prefixes_preserves_raw_order_before_phone_variants(self):
        result = HuaweiOBSClient._normalize_prefixes(
            ["11139033478", "16996299520", "666"]
        )

        self.assertEqual(result[:3], ["11139033478", "16996299520", "666"])
        self.assertIn("011139033478", result)
        self.assertIn("0016996299520", result)

    def test_matches_any_call_id_accepts_call_id_suffix(self):
        result = HuaweiOBSClient._matches_any_call_id(
            "Voice/20260425/0016996299520/20260425120000-1777093663-792075.V3",
            ["792075"],
        )

        self.assertTrue(result)

    async def test_baixar_voice_por_callid_usa_contact_record_quando_busca_direta_falha(self):
        client = HuaweiOBSClient("ak", "sk", "bucket")
        client._candidate_dates = lambda begin_time, end_time=None: ["20260425"]
        client._date_with_neighbors = lambda begin_time, end_time=None: ["20260425"]
        client._baixar_por_prefixos_e_ids = AsyncMock(side_effect=[None, b"RIFFdata"])
        client.listar_contact_record_rows = AsyncMock(
            return_value=[
                {
                    "callId": "1777093663-792075",
                    "recordId": "792075",
                    "caller": "0016996299520",
                    "called": "61197",
                }
            ]
        )

        result = await client.baixar_voice_por_callid(
            call_id="1777093663-792075",
            prefixes=["16996299520", "666"],
            begin_time=1762373580000,
        )

        self.assertEqual(result, b"RIFFdata")
        self.assertEqual(client._baixar_por_prefixos_e_ids.await_count, 2)
        second_call = client._baixar_por_prefixos_e_ids.await_args_list[1].kwargs
        self.assertEqual(second_call["date_str"], "20260425")
        self.assertIn("0016996299520", second_call["prefixes"])
        self.assertIn("792075", second_call["match_ids"])

    async def test_baixar_voice_por_callid_usa_contact_record_sem_prefixo_inicial(self):
        client = HuaweiOBSClient("ak", "sk", "bucket")
        client._candidate_dates = lambda begin_time, end_time=None: ["20260425"]
        client._date_with_neighbors = lambda begin_time, end_time=None: ["20260425"]
        client._baixar_por_prefixos_e_ids = AsyncMock(return_value=b"RIFFdata")
        client.listar_contact_record_rows = AsyncMock(
            return_value=[
                {
                    "callId": "1777516248-17256970",
                    "recordId": "17256970",
                    "caller": "0016996299520",
                    "called": "61197",
                    "workNo": "189",
                }
            ]
        )

        result = await client.baixar_voice_por_callid(
            call_id="1777516248-17256970",
            prefixes=[],
            begin_time=1777516248000,
            extra_match_ids=["17256970"],
        )

        self.assertEqual(result, b"RIFFdata")
        client.listar_contact_record_rows.assert_awaited_once_with("20260425")
        client._baixar_por_prefixos_e_ids.assert_awaited_once()
        kwargs = client._baixar_por_prefixos_e_ids.await_args.kwargs
        self.assertIn("0016996299520", kwargs["prefixes"])
        self.assertIn("61197", kwargs["prefixes"])
        self.assertIn("17256970", kwargs["match_ids"])

    def test_coerce_to_epoch_ms_iso_string_assumes_utc(self):
        # Defesa em profundidade: se um huawei_begin_time string ISO chegar aqui
        # (fallback do path do CSV), `_candidate_dates` resolveria a pasta YYYYMMDD
        # errada. Mesmo bug semantico do `_coerce_huawei_time_ms` (v1.3.93).
        result = HuaweiOBSClient._coerce_to_epoch_ms("2026-05-26 12:23:47")
        self.assertEqual(result, 1779798227000)


if __name__ == "__main__":
    unittest.main()
