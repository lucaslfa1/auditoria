"""Cadeia de download de gravacoes Huawei (Chain of Responsibility).

Centraliza a estrategia de obter o audio de uma chamada da Huawei tentando
varias fontes em ordem, ate a primeira que devolver bytes:

- OBS direto (`OBSDirectHandler`): le o objeto `.V3`/WAV direto do bucket OBS.
- CC-FS (`CCFSDownloadRecordHandler`): baixa a gravacao via API de gravacoes
  da plataforma AICC (download por callId).
- URL pre-assinada (`PresignedUrlHandler`): obtem uma URL OBS assinada pela
  API e baixa o conteudo dela.

A ordem dos handlers depende do `mode` da `HuaweiDownloadChain`
('manual_interval' x 'retroactive'). Cada tentativa/sucesso/falha emite
eventos via `HuaweiEvents` (DOWNLOAD_RECOVERED/DOWNLOAD_FAILED/
DOWNLOAD_EXHAUSTED) para o Cloud Logging.

Custo de API: nao chama Azure (sem custo de IA). Faz chamadas de rede ao
gateway/OBS da Huawei (download de bytes) — custo de banda/infra, nao de IA.
"""

from typing import Protocol, Optional, Dict, Any, List
from dataclasses import dataclass, field
import logging

from core.huawei_client import HuaweiAICCClient
from core.huawei_obs_client import HuaweiOBSClient
from core.huawei_events import HuaweiEvents

logger = logging.getLogger(__name__)

@dataclass
class DownloadResult:
    """Resultado consolidado de uma tentativa de download via cadeia.

    Campos:
    - audio_bytes: bytes do audio baixado, ou None se nenhum metodo funcionou.
    - method_used: nome do handler que teve sucesso (ex.: "obs_primary").
    - methods_tried: nomes dos handlers efetivamente acionados.
    - attempts_per_method: quantos IDs foram tentados em cada metodo (FS/URL).
    - errors: mapa nome_do_metodo -> mensagem de erro, quando o handler lancou.
    """

    audio_bytes: Optional[bytes] = None
    method_used: Optional[str] = None
    methods_tried: List[str] = field(default_factory=list)
    # Rastreia quantos IDs foram tentados em cada metodo (FS/URL)
    attempts_per_method: Dict[str, int] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """True quando algum metodo devolveu bytes de audio."""
        return self.audio_bytes is not None

class DownloadHandler(Protocol):
    """Contrato (Protocol) de um handler da cadeia de download.

    Cada handler implementa `handle` e devolve `(audio_bytes | None,
    ids_tried)`: os bytes baixados (ou None) e quantos IDs foram efetivamente
    tentados (0 quando o handler nem se aplica ao caso).
    """

    async def handle(self, call_data: Dict[str, Any], client: HuaweiAICCClient, obs_client: Optional[HuaweiOBSClient]) -> tuple[Optional[bytes], int]:
        ...

class OBSDirectHandler:
    """Handler que baixa o `.V3`/WAV direto do bucket OBS (fonte primaria)."""

    async def handle(self, call_data: Dict[str, Any], client: HuaweiAICCClient, obs_client: Optional[HuaweiOBSClient]) -> tuple[Optional[bytes], int]:
        """Tenta resolver/baixar o audio via `HuaweiOBSClient`.

        Le de `call_data` o callId, recordId, source, prefixes, beginTime/
        endTime, agent_id e extra_match_ids. Pula (retorna (None, 0)) quando
        nao ha `obs_client` ou quando a chamada veio so do manifesto puro
        (source com "obs_contact_record" e sem "vdn") sem recordId.

        Retorna `(audio_bytes | None, ids_tried)` — `ids_tried` e 1 quando a
        busca OBS foi efetivamente acionada, 0 quando o handler foi pulado.
        Efeito colateral: faz listagens/downloads de rede no OBS.
        """
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
    """Handler que obtem uma URL OBS pre-assinada via API e baixa o audio."""

    async def handle(self, call_data: Dict[str, Any], client: HuaweiAICCClient, obs_client: Optional[HuaweiOBSClient]) -> tuple[Optional[bytes], int]:
        """Pede a URL OBS assinada para cada download_id e baixa a primeira valida.

        Exige `beginTime` e `endTime` em `call_data` (sem eles retorna
        (None, 0)). Itera os `download_ids` (ou o callId como unico candidato),
        chama `client.obter_url_audio_obs` e, se vier uma URL http, baixa via
        `client.baixar_audio_ram`. Retorna `(audio_bytes | None, ids_tried)`,
        onde `ids_tried` e quantos IDs foram percorridos. Faz chamadas de rede
        ao gateway Huawei.
        """
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
    """Handler que baixa a gravacao via API CC-FS (download por callId)."""

    async def handle(self, call_data: Dict[str, Any], client: HuaweiAICCClient, obs_client: Optional[HuaweiOBSClient]) -> tuple[Optional[bytes], int]:
        """Tenta `client.baixar_gravacao_por_callid` para cada download_id.

        Itera os `download_ids` (ou o callId) e retorna no primeiro que devolver
        bytes. Retorna `(audio_bytes | None, ids_tried)`. Faz chamadas de rede
        a API de gravacoes (CC-FS) da Huawei.
        """
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
        """Monta a lista de handlers conforme o modo de coleta.

        - mode="manual_interval": OBS direto -> CC-FS -> URL pre-assinada.
        - mode="retroactive": CC-FS -> URL pre-assinada (NUNCA usa OBS direto).
        - qualquer outro valor: nenhum handler (cadeia vazia).
        """
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
        """Executa os handlers em ordem e retorna no primeiro que baixar o audio.

        Params:
        - call_data: dict da chamada (callId, recordId, prefixes, beginTime/
          endTime, download_ids, etc.). Se `skip_obs_primary` for True, o
          handler "obs_primary" e pulado.
        - client: cliente AICC para as APIs CC-FS / URL assinada.
        - obs_client: cliente OBS direto (pode ser None; nesse caso o handler
          OBS apenas se auto-pula).

        Retorna um `DownloadResult` com bytes, metodo usado, metodos tentados,
        IDs por metodo e erros. Efeitos colaterais: chamadas de rede aos
        handlers e emissao de eventos via `HuaweiEvents` — DOWNLOAD_RECOVERED
        quando um fallback (nao-OBS) recupera o audio, DOWNLOAD_FAILED por
        handler que lanca excecao, e DOWNLOAD_EXHAUSTED quando nenhum metodo
        obtem o audio.
        """
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
