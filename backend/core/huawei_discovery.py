import os
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

from core.huawei_client import HuaweiAICCClient
from core.huawei_direction import format_huawei_is_call_in, resolve_huawei_is_call_in
from core.huawei_obs_client import HuaweiOBSClient

logger = logging.getLogger(__name__)

class HuaweiDiscoveryService:
    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_huawei_time_ms(value: Any) -> Optional[int]:
        numeric = HuaweiAICCClient._coerce_epoch_millis(value)
        if numeric is not None:
            return numeric
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                # CSV manifesto da Huawei envia beginTime/endTime como ISO em UTC
                # (sem fuso explicito). Assumir BRT aqui adicionava +3h ao epoch.
                dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1000)
            except ValueError:
                continue
        return None

    @staticmethod
    def _window_date_strings(begin_ms: int, end_ms: int) -> list[str]:
        dates: list[str] = []
        seen: set[str] = set()
        for ms in (begin_ms, end_ms):
            for tz in (timezone.utc, ZoneInfo("America/Sao_Paulo")):
                date_str = datetime.fromtimestamp(ms / 1000, tz=tz).strftime("%Y%m%d")
                if date_str not in seen:
                    seen.add(date_str)
                    dates.append(date_str)
        return dates

    @classmethod
    def _query_time_windows(cls, begin_ms: int, end_ms: int) -> list[tuple[int, int]]:
        if end_ms < begin_ms:
            return []

        window_minutes = max(
            1,
            cls._coerce_int(os.getenv("HUAWEI_QUERYCALLS_WINDOW_MINUTES"), 60),
        )
        window_ms = window_minutes * 60 * 1000
        windows: list[tuple[int, int]] = []
        current = begin_ms
        while current <= end_ms:
            chunk_end = min(current + window_ms, end_ms)
            if chunk_end <= current:
                break
            windows.append((current, chunk_end))
            current = chunk_end + 1
        return windows

    @classmethod
    def _manifest_row_to_interacao(cls, row: dict[str, str]) -> dict:
        begin_ms = cls._coerce_huawei_time_ms(row.get("beginTime"))
        end_ms = cls._coerce_huawei_time_ms(row.get("endTime"))
        duration = cls._coerce_int(
            row.get("calllDuration")
            or row.get("callDuration")
            or row.get("duration"),
            0,
        )
        if duration <= 0 and begin_ms is not None and end_ms is not None and end_ms >= begin_ms:
            duration = int((end_ms - begin_ms) / 1000)

        caller_no = str(row.get("caller") or "").strip()
        callee_no = str(row.get("called") or "").strip()
        work_no = str(row.get("workNo") or "").strip()
        direction_payload = {
            **row,
            "callerNo": caller_no,
            "calleeNo": callee_no,
            "workNo": work_no,
        }
        is_call_in = format_huawei_is_call_in(resolve_huawei_is_call_in(direction_payload))

        return {
            "callId": str(row.get("callId") or row.get("recordId") or "").strip(),
            "recordId": str(row.get("recordId") or "").strip(),
            "contactId": str(row.get("contactId") or "").strip(),
            "callSerialno": str(row.get("callSerialno") or "").strip(),
            "callerNo": caller_no,
            "calleeNo": callee_no,
            "isCallIn": is_call_in,
            "beginTime": begin_ms if begin_ms is not None else row.get("beginTime"),
            "endTime": end_ms if end_ms is not None else row.get("endTime"),
            "duration": duration,
            "duracao": duration,
            "callReason": str(row.get("callReason") or row.get("talkReason") or row.get("talkRemark") or "").strip(),
            "talkReason": str(row.get("talkReason") or "").strip(),
            "talkRemark": str(row.get("talkRemark") or "").strip(),
            "callReasonCode": str(row.get("callReasonCode") or row.get("leaveReason") or "").strip(),
            "workNo": work_no,
            "operatorName": str(row.get("countName") or "").strip(),
            "skillId": str(row.get("skillId") or "").strip(),
            "callSkill": str(row.get("callSkill") or "").strip(),
            "mediaTypeId": str(row.get("mediaTypeId") or "").strip(),
            "source": "obs_contact_record",
        }

    @staticmethod
    def resolve_call_key(chamada: dict) -> str:
        return str(
            chamada.get("callId")
            or chamada.get("callid")
            or chamada.get("id")
            or ""
        ).strip()

    @classmethod
    def merge_interacoes(cls, *collections: list[dict]) -> list[dict]:
        merged: dict[str, dict] = {}
        sem_id: list[dict] = []
        for collection in collections:
            for interacao in collection:
                call_id = cls.resolve_call_key(interacao)
                if not call_id:
                    sem_id.append(interacao)
                    continue
                current = merged.setdefault(call_id, {})
                sources = set(str(current.get("source") or "").split("+")) if current.get("source") else set()
                if interacao.get("source"):
                    sources.add(str(interacao["source"]))
                for key, value in interacao.items():
                    if value in (None, ""):
                        continue
                    if not current.get(key):
                        current[key] = value
                if sources:
                    current["source"] = "+".join(sorted(s for s in sources if s))
        return list(merged.values()) + sem_id

    @classmethod
    async def buscar_chamadas_globais(
        cls,
        client: HuaweiAICCClient,
        begin_ms: int,
        end_ms: int,
        *,
        limit_per_page: int = 100,
        max_rows: int = 500,
        call_directions: Optional[list[str]] = None,
    ) -> list[dict]:
        chamadas_por_id: dict[str, dict] = {}
        chamadas_sem_id: list[dict] = []
        requested_directions = [
            direction
            for direction in (call_directions or ["INBOUND", "OUTBOUND"])
            if str(direction or "").upper() in {"INBOUND", "OUTBOUND"}
        ]

        for window_begin_ms, window_end_ms in cls._query_time_windows(begin_ms, end_ms):
            for direction in requested_directions:
                direction = str(direction).upper()
                chamadas = await client.buscar_historico_chamadas(
                    window_begin_ms,
                    window_end_ms,
                    call_direction=direction,
                )
                if not chamadas:
                    continue
                for chamada in chamadas:
                    chamada = dict(chamada)
                    chamada.setdefault("isCallIn", "true" if direction == "INBOUND" else "false")
                    chamada["source"] = "vdn"
                    call_key = cls.resolve_call_key(chamada)
                    if not call_key:
                        chamadas_sem_id.append(chamada)
                        continue
                    chamadas_por_id.setdefault(call_key, chamada)

        return list(chamadas_por_id.values()) + chamadas_sem_id

    @classmethod
    async def buscar_chamadas_obs_manifest(
        cls,
        obs_client: Optional[HuaweiOBSClient],
        begin_ms: int,
        end_ms: int,
    ) -> list[dict]:
        if obs_client is None:
            return []

        interacoes: list[dict] = []
        for date_str in cls._window_date_strings(begin_ms, end_ms):
            for row in await obs_client.listar_contact_record_rows(date_str):
                interacao = cls._manifest_row_to_interacao(row)
                begin_time = cls._coerce_huawei_time_ms(interacao.get("beginTime"))
                if begin_time is not None and (begin_time < begin_ms or begin_time > end_ms):
                    continue
                interacoes.append(interacao)
        return interacoes

    @classmethod
    async def fetch_all(
        cls,
        client: HuaweiAICCClient,
        obs_client: Optional[HuaweiOBSClient],
        begin_ms: int,
        end_ms: int,
        *,
        obs_only: bool = False,
        call_directions: Optional[list[str]] = None,
    ) -> tuple[list[dict], set[str], set[str], set[str]]:
        """
        Descobre chamadas da VDN e do Manifesto OBS e as intercala.
        Retorna:
            - interacoes (lista de ditos da chamada interalados)
            - call_ids_vdn_unicos (set de call IDs da VDN)
            - call_ids_manifest_unicos (set de call IDs do OBS)
            - call_ids_descobertos_unicos (set de todos os call IDs descobertos)
        """
        if not obs_only:
            vdn_interacoes = await cls.buscar_chamadas_globais(
                client,
                begin_ms,
                end_ms,
                call_directions=call_directions,
            )
        else:
            vdn_interacoes = []
            
        obs_manifest_interacoes = await cls.buscar_chamadas_obs_manifest(obs_client, begin_ms, end_ms)
        
        call_ids_vdn_unicos: set[str] = set()
        call_ids_manifest_unicos: set[str] = set()
        call_ids_descobertos_unicos: set[str] = set()

        for chamada in vdn_interacoes:
            chamada_call_id = cls.resolve_call_key(chamada)
            if chamada_call_id:
                call_ids_vdn_unicos.add(chamada_call_id)
                
        for chamada in obs_manifest_interacoes:
            chamada_call_id = cls.resolve_call_key(chamada)
            if chamada_call_id:
                call_ids_manifest_unicos.add(chamada_call_id)
                
        interacoes = cls.merge_interacoes(vdn_interacoes, obs_manifest_interacoes)
        
        for chamada in interacoes:
            chamada_call_id = cls.resolve_call_key(chamada)
            if chamada_call_id:
                call_ids_descobertos_unicos.add(chamada_call_id)
                
        return interacoes, call_ids_vdn_unicos, call_ids_manifest_unicos, call_ids_descobertos_unicos
