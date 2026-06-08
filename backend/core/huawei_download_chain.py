from typing import Protocol, Optional, Dict, Any, List
from dataclasses import dataclass, field
import logging

from core.huawei_client import HuaweiAICCClient
from core.huawei_obs_client import HuaweiOBSClient
from core.huawei_events import HuaweiEvents

logger = logging.getLogger(__name__)

@dataclass
class DownloadResult:
    audio_bytes: Optional[bytes] = None
    method_used: Optional[str] = None
    methods_tried: List[str] = field(default_factory=list)
    # Rastreia quantos IDs foram tentados em cada metodo (FS/URL)
    attempts_per_method: Dict[str, int] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    
    @property
    def success(self) -> bool:
        return self.audio_bytes is not None

class DownloadHandler(Protocol):
    async def handle(self, call_data: Dict[str, Any], client: HuaweiAICCClient, obs_client: Optional[HuaweiOBSClient]) -> tuple[Optional[bytes], int]:
        ...

class OBSDirectHandler:
    async def handle(self, call_data: Dict[str, Any], client: HuaweiAICCClient, obs_client: Optional[HuaweiOBSClient]) -> tuple[Optional[bytes], int]:
        if not obs_client:
            return None, 0
            
        call_id = call_data.get("callId")
        record_id = str(call_data.get("recordId") or "").strip()
        source = str(call_data.get("source") or "")
        
        is_from_manifest = "obs_contact_record" in source
        is_from_vdn = "vdn" in source
        
        # Pula se for manifesto puro sem recordId
        if not record_id and is_from_manifest and not is_from_vdn:
            return None, 0
            
        audio = await obs_client.baixar_voice_por_callid(
            call_id=call_id,
            prefixes=call_data.get("prefixes"),
            begin_time=call_data.get("beginTime"),
            end_time=call_data.get("endTime"),
            agent_id=call_data.get("agent_id"),
            extra_match_ids=call_data.get("extra_match_ids")
        )
        return audio, 1

class PresignedUrlHandler:
    async def handle(self, call_data: Dict[str, Any], client: HuaweiAICCClient, obs_client: Optional[HuaweiOBSClient]) -> tuple[Optional[bytes], int]:
        download_ids = call_data.get("download_ids") or [call_data.get("callId")]
        begin_time = call_data.get("beginTime")
        end_time = call_data.get("endTime")
        
        if not all([begin_time, end_time]):
            return None, 0
            
        ids_tried = 0
        for download_id in download_ids:
            ids_tried += 1
            obs_url = await client.obter_url_audio_obs(
                download_id,
                begin_time=str(begin_time),
                end_time=str(end_time)
            )
            
            if obs_url and obs_url.startswith("http"):
                audio = await client.baixar_audio_ram(obs_url)
                if audio:
                    return audio, ids_tried
        return None, ids_tried

class CCFSDownloadRecordHandler:
    async def handle(self, call_data: Dict[str, Any], client: HuaweiAICCClient, obs_client: Optional[HuaweiOBSClient]) -> tuple[Optional[bytes], int]:
        download_ids = call_data.get("download_ids") or [call_data.get("callId")]
        ids_tried = 0
        for download_id in download_ids:
            ids_tried += 1
            audio = await client.baixar_gravacao_por_callid(download_id)
            if audio:
                return audio, ids_tried
        return None, ids_tried

class HuaweiDownloadChain:
    """
    Orquestra o download. Modos:
    - 'manual_interval': OBS Direct (Primario), CC-FS (Fallback 1), URL Pre-assinada (Fallback 2).
    - 'retroactive': CC-FS (Primario), URL Pre-assinada (Fallback 1). NUNCA usa OBS.
    """
    def __init__(self, mode: str = "manual_interval"):
        if mode == "manual_interval":
            self.handlers = [
                ("obs_primary", OBSDirectHandler()),
                ("fs_fallback", CCFSDownloadRecordHandler()),
                ("url_fallback", PresignedUrlHandler())
            ]
        elif mode == "retroactive":
            self.handlers = [
                ("fs_fallback", CCFSDownloadRecordHandler()),
                ("url_fallback", PresignedUrlHandler())
            ]
        else:
            self.handlers = []

    async def download(self, call_data: Dict[str, Any], client: HuaweiAICCClient, obs_client: Optional[HuaweiOBSClient]) -> DownloadResult:
        result = DownloadResult()
        call_id = call_data.get("callId", "unknown")
        skip_obs_primary = call_data.get("skip_obs_primary", False)

        for name, handler in self.handlers:
            if name == "obs_primary" and skip_obs_primary:
                continue

            try:
                audio, ids_tried = await handler.handle(call_data, client, obs_client)                
                if ids_tried > 0:
                    result.methods_tried.append(name)
                    result.attempts_per_method[name] = ids_tried

                if audio:
                    result.audio_bytes = audio
                    result.method_used = name
                    
                    if name != "obs_primary":
                        HuaweiEvents.log_event(
                            "DOWNLOAD_RECOVERED",
                            call_id=call_id,
                            context={"method": name},
                            severity="INFO"
                        )
                    return result
            except Exception as e:
                err_msg = str(e)
                result.errors[name] = err_msg
                HuaweiEvents.log_event(
                    "DOWNLOAD_FAILED",
                    call_id=call_id,
                    context={"method": name, "error": err_msg},
                    severity="WARNING"
                )
                
        HuaweiEvents.log_event(
            "DOWNLOAD_EXHAUSTED",
            call_id=call_id,
            context={"errors": result.errors},
            severity="ERROR"
        )
        return result
