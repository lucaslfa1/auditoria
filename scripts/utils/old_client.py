"""Cliente HTTP para a plataforma Huawei AICC (CC-CMS + CC-FS).

Tres modos de autenticacao, selecionados por HUAWEI_AUTH_MODE:

1. 'proxy' (PADRAO) - Uso obrigatorio quando o ambiente nao esta em IP
   whitelisted pela Huawei. A assinatura SDK-HMAC-SHA256 eh delegada ao
   endpoint `c2Authorization.php` hospedado pela Teledata Brasil, que
   retorna somente o cabecalho `Authorization` ja pronto. A requisicao final
   continua saindo daqui, entao este host ainda precisa estar whitelisted.

2. 'oauth_direct' (alias: 'token') - Obtem AccessToken da propria Huawei via
   POST {auth_base}/apigovernance/api/oauth/tokenByAkSk com app_key/app_secret
   e usa em Authorization: Bearer <token>. Usa o UUID app_key + app_secret
   diretos da Huawei (NAO o AK/SK do proxy Teledata). Cache do token vive
   ate sua expiracao (campo `expiresIn`, default 3300s = 55min).
   Use HUAWEI_DIRECT_APP_KEY / HUAWEI_DIRECT_APP_SECRET para isolar das
   credenciais do proxy. Necessita IP whitelisted no WAF da Huawei.

3. 'direct' - Assina localmente via HMAC-SHA256 (stdlib hmac+hashlib)
   seguindo https://support.huaweicloud.com/intl/en-us/api-cec/cec_07_0003.html
   Uso apenas em ambientes com AK/SK diretos e IP liberado.

Referencia do fluxo C2 (Postman collection oficial OPENTECH/Teledata):
    POST https://opentech.teledatabrasil.com.br/aicc/auth/c2Authorization.php
    body: {
        "ak": "<app_key_c2>",
        "sk": "<app_secret_c2>",
        "url": "<target huawei url completa>",
        "method": "POST",
        "requestHeader": "Content-Type:application/json; charset=UTF-8",
        "requestBody": { ... objeto inline ... },
        "replaceNewLine": "true"
    }
    resp: { "Authorization": "<token assinado>" }

Depois usa-se esse valor em Authorization: <...> na chamada final ao
`brazilsaas.aicccloud.com:28443`.

Endpoints suportados:
    CMS: /rest/cmsapp/v2/openapi/vdn/querycalls
    FS:  /CCFS/resource/ccfs/getRecordFileUrlFromObs (async OBS pre-signed)
    FS:  /CCFS/resource/ccfs/downloadRecord         (binario direto, mais simples)
    FS:  /CCFS/resource/ccfs/downloadRecordFile     (binario por fileName)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, quote
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

ALGORITHM = "SDK-HMAC-SHA256"
DEFAULT_SIGNED_HEADERS = ("host", "x-sdk-date")

# URLs e modos configuraveis via env
DEFAULT_CMS_URL = "https://brazilsaas.aicccloud.com:28443"
DEFAULT_FS_URL = "https://brazilsaas.aicccloud.com:28443"
DEFAULT_PROXY_URL = "https://lab.teledatabrasil.com.br/aicc/auth/c2Authorization.php"
DEFAULT_AUTH_MODE = "proxy"
# Modos que disparam o fluxo OAuth tokenByAkSk (Bearer token).
OAUTH_DIRECT_MODES = {"oauth_direct", "token"}
# Renovamos o token 60s antes da expiracao informada para evitar race com a Huawei.
TOKEN_REFRESH_BUFFER_SECONDS = 60
DEFAULT_TOKEN_TTL_SECONDS = 3300  # ~55min, mesmo default usado pelo Postman collection.


class HuaweiAICCClient:
    def __init__(
        self,
        cms_url: str,
        fs_url: str,
        cc_id: int,
        vdn: int,
        ak: str,
        sk: str,
        app_key: str,
        app_secret: str = "",
        timeout_seconds: float = 20.0,
        auth_mode: Optional[str] = None,
        proxy_url: Optional[str] = None,
        auth_base_url: Optional[str] = None,
        tenant_space_id: Optional[str] = None,
        direct_app_key: Optional[str] = None,
        direct_app_secret: Optional[str] = None,
    ) -> None:
        self.cms_url = (cms_url or DEFAULT_CMS_URL).rstrip("/")
        self.fs_url = (fs_url or DEFAULT_FS_URL).rstrip("/")
        self.cc_id = cc_id
        self.vdn = vdn
        self.ak = ak
        self.sk = sk
        self.app_key = app_key
        self.app_secret = app_secret
        self.timeout_seconds = timeout_seconds
        self.auth_mode = (auth_mode or os.environ.get("HUAWEI_AUTH_MODE") or DEFAULT_AUTH_MODE).lower()
        self.proxy_url = proxy_url or os.environ.get("HUAWEI_PROXY_URL") or DEFAULT_PROXY_URL

        # OAuth direct: credenciais separadas (UUID + secret) e tenant header
        # opcional. Quando ausentes, caem no app_key/app_secret padrao.
        self.direct_app_key = (
            direct_app_key
            or os.environ.get("HUAWEI_DIRECT_APP_KEY")
            or self.app_key
        )
        self.direct_app_secret = (
            direct_app_secret
            or os.environ.get("HUAWEI_DIRECT_APP_SECRET")
            or self.app_secret
        )
        self.tenant_space_id = (
            tenant_space_id
            or os.environ.get("HUAWEI_TENANT_SPACE_ID")
            or ""
        ).strip()
        self.auth_base_url = self._resolve_auth_base_url(auth_base_url)

        # Cache do AccessToken para o modo oauth_direct.
        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _resolve_auth_base_url(self, override: Optional[str]) -> str:
        """Determina a URL base do servico de OAuth (sem porta 28443).

        Ordem de precedencia:
        1. override explicito (parametro do construtor ou config dict)
        2. env HUAWEI_AUTH_BASE_URL / HUAWEI_PORTAL_URL
        3. derivado do cms_url removendo a porta 28443 (CMS escuta em 28443,
           mas o `apigovernance` responde na porta padrao 443).
        """
        candidate = (
            override
            or os.environ.get("HUAWEI_AUTH_BASE_URL")
            or os.environ.get("HUAWEI_PORTAL_URL")
            or ""
        ).strip()
        if candidate:
            return candidate.rstrip("/")

        parsed = urlparse(self.cms_url)
        scheme = parsed.scheme or "https"
        host = parsed.hostname or "brazilsaas.aicccloud.com"
        return f"{scheme}://{host}"

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "HuaweiAICCClient":
        """Constroi o cliente a partir de um dict (tabela configuracoes)."""
        return cls(
            cms_url=str(cfg.get("cms_url") or DEFAULT_CMS_URL),
            fs_url=str(cfg.get("fs_url") or DEFAULT_FS_URL),
            cc_id=int(cfg.get("cc_id") or 0),
            vdn=int(cfg.get("vdn") or 0),
            ak=str(cfg.get("ak", "")),
            sk=str(cfg.get("sk", "")),
            app_key=str(cfg.get("app_key", "")),
            app_secret=str(cfg.get("app_secret", "")),
            auth_mode=cfg.get("auth_mode"),
            proxy_url=cfg.get("proxy_url"),
            auth_base_url=cfg.get("auth_base_url"),
            tenant_space_id=cfg.get("tenant_space_id"),
            direct_app_key=cfg.get("direct_app_key"),
            direct_app_secret=cfg.get("direct_app_secret"),
        )

    # ------------------------------------------------------------------
    # Autenticacao (direct ou proxy)
    # ------------------------------------------------------------------

    async def _build_auth_headers(
        self,
        method: str,
        url: str,
        body_obj: Any,
    ) -> Dict[str, str]:
        """Retorna os headers com Authorization preenchido para a chamada final.

        - Em modo 'proxy': chama c2Authorization.php e reaproveita o token.
        - Em modo 'direct': calcula HMAC-SHA256 localmente.
        """
        if self.auth_mode in OAUTH_DIRECT_MODES:
            auth_token = await self._get_token_by_aksk()
            if not auth_token:
                return {}
            headers: Dict[str, str] = {
                "Authorization": f"Bearer {auth_token}",
                "X-APP-Key": self.direct_app_key,
                "Content-Type": "application/json; charset=UTF-8",
            }
            if self.tenant_space_id:
                headers["X-TenantSpaceID"] = self.tenant_space_id
            return headers

        if self.auth_mode == "proxy":
            auth_token = await self._assinar_via_proxy(method, url, body_obj)
            if not auth_token:
                return {}
            return {
                "Authorization": auth_token,
                "Content-Type": "application/json; charset=UTF-8",
            }
        # direct
        payload = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":"))
        return self._sign_request(method, url, payload)


    async def _get_token_by_aksk(self) -> Optional[str]:
        """Obtem o AccessToken via OAuth tokenByAkSk com cache em memoria.

        Pre-requisitos:
        - direct_app_key (UUID Huawei) e direct_app_secret nao vazios.
        - auth_base_url apontando para o host sem a porta 28443.
        Cache: token reaproveitado ate `expiresIn - TOKEN_REFRESH_BUFFER_SECONDS`.
        """
        if not self.direct_app_key or not self.direct_app_secret:
            logger.error(
                "Huawei tokenByAkSk: direct_app_key ou direct_app_secret ausentes "
                "(defina HUAWEI_DIRECT_APP_KEY/HUAWEI_DIRECT_APP_SECRET no .env)"
            )
            return None

        now = time.monotonic()
        if self._cached_token and now < self._token_expires_at:
            return self._cached_token

        url = f"{self.auth_base_url}/apigovernance/api/oauth/tokenByAkSk"
        payload = {
            "app_key": self.direct_app_key,
            "app_secret": self.direct_app_secret,
        }
        verify_ssl = os.getenv("HUAWEI_SSL_VERIFY", "true").lower() == "true"

        try:
            async with httpx.AsyncClient(verify=verify_ssl, timeout=self.timeout_seconds) as cli:
                resp = await cli.post(url, json=payload)
        except httpx.HTTPError as exc:
            logger.error("Huawei tokenByAkSk erro de conexao: %s", exc)
            return None

        if resp.status_code != 200:
            logger.error(
                "Huawei tokenByAkSk falhou HTTP %s: %s",
                resp.status_code,
                resp.text[:200],
            )
            return None

        try:
            data = resp.json()
        except ValueError:
            logger.error("Huawei tokenByAkSk devolveu corpo nao-JSON: %s", resp.text[:200])
            return None

        token = data.get("AccessToken") or data.get("accessToken")
        if not token:
            logger.error("Huawei tokenByAkSk sem campo AccessToken: %s", data)
            return None

        ttl_raw = data.get("expiresIn") or data.get("expires_in") or DEFAULT_TOKEN_TTL_SECONDS
        try:
            ttl_seconds = max(int(ttl_raw), TOKEN_REFRESH_BUFFER_SECONDS + 1)
        except (TypeError, ValueError):
            ttl_seconds = DEFAULT_TOKEN_TTL_SECONDS

        self._cached_token = token
        self._token_expires_at = now + ttl_seconds - TOKEN_REFRESH_BUFFER_SECONDS
        logger.info(
            "Huawei tokenByAkSk OK; cache valido por ~%ss",
            ttl_seconds - TOKEN_REFRESH_BUFFER_SECONDS,
        )
        return token

    async def _assinar_via_proxy(
        self,
        method: str,
        url: str,
        body_obj: Any,
    ) -> Optional[str]:
        """Delega assinatura ao c2Authorization.php. Retorna so o Authorization."""
        if not self.ak or not self.sk:
            logger.error("Huawei proxy: AK/SK ausentes nas configuracoes")
            return None

        proxy_body = {
            "ak": self.ak,
            "sk": self.sk,
            "url": url,
            "method": method.upper(),
            "requestHeader": "Content-Type:application/json; charset=UTF-8",
            "requestBody": body_obj if body_obj is not None else {},
            "replaceNewLine": "true",
        }

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            logger.info("Hitting proxy URL: %s", self.proxy_url)
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as cli:
                resp = await cli.post(self.proxy_url, json=proxy_body, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("Huawei proxy HTTP erro: %s", exc)
            return None

        if resp.status_code != 200:
            logger.error(
                "Huawei proxy retornou HTTP %s para %s: %s",
                resp.status_code,
                url,
                resp.text[:500],
            )
            return None
        try:
            data = resp.json()
        except ValueError:
            logger.error("Huawei proxy devolveu corpo nao-JSON: %s", resp.text[:200])
            return None
        token = data.get("Authorization") or data.get("authorization")
        if not token:
            logger.error("Huawei proxy sem campo Authorization: %s", data)
            return None
        return token

    # ------------------------------------------------------------------
    # Assinatura SDK-HMAC-SHA256 (modo direct)
    # ------------------------------------------------------------------

    def _sign_request(
        self,
        method: str,
        url: str,
        payload: str,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Retorna os cabecalhos assinados localmente (modo direct)."""
        parsed = urlparse(url)
        host = parsed.netloc
        canonical_uri = parsed.path or "/"
        canonical_uri_encoded = quote(canonical_uri, safe="/-_.~")
        canonical_query = self._canonicalize_query(parsed.query)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        headers: Dict[str, str] = {
            "Host": host,
            "X-Sdk-Date": timestamp,
            "Content-Type": "application/json;charset=UTF-8",
        }
        if self.app_key:
            headers["X-APP-Key"] = self.app_key
        if extra_headers:
            headers.update(extra_headers)

        signed_headers = ";".join(DEFAULT_SIGNED_HEADERS)
        canonical_headers = "".join(
            f"{name}:{headers[self._header_key(name, headers)].strip()}\n"
            for name in DEFAULT_SIGNED_HEADERS
        )

        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = "\n".join(
            [
                method.upper(),
                canonical_uri_encoded,
                canonical_query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        string_to_sign = "\n".join(
            [
                ALGORITHM,
                timestamp,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signature = hmac.new(
            self.sk.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        headers["Authorization"] = (
            f"{ALGORITHM} Access={self.ak}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return headers

    @staticmethod
    def _header_key(name: str, headers: Dict[str, str]) -> str:
        lower = name.lower()
        for key in headers:
            if key.lower() == lower:
                return key
        return name

    @staticmethod
    def _canonicalize_query(query: str) -> str:
        if not query:
            return ""
        pairs = []
        for part in query.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
            else:
                k, v = part, ""
            pairs.append((quote(k, safe="-_.~"), quote(v, safe="-_.~")))
        pairs.sort()
        return "&".join(f"{k}={v}" for k, v in pairs)

    @staticmethod
    def _coerce_epoch_millis(value: Any) -> Optional[int]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            numeric = int(float(text))
        except (TypeError, ValueError):
            return None
        if numeric <= 0:
            return None
        if abs(numeric) < 10_000_000_000:
            numeric *= 1000
        return numeric

    @classmethod
    def _normalize_querycalls_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row or {})
        start_ms = (
            cls._coerce_epoch_millis(normalized.get("callBegin"))
            or cls._coerce_epoch_millis(normalized.get("beginTime"))
            or cls._coerce_epoch_millis(normalized.get("ackBegin"))
            or cls._coerce_epoch_millis(normalized.get("waitBegin"))
        )
        end_ms = (
            cls._coerce_epoch_millis(normalized.get("callEnd"))
            or cls._coerce_epoch_millis(normalized.get("endTime"))
            or cls._coerce_epoch_millis(normalized.get("logDate"))
        )
        explicit_duration = None
        for key in (
            "duration",
            "duracao",
            "callDuration",
            "calllDuration",
            "talkDuration",
            "talkTime",
            "durationSeconds",
            "durationSec",
            "recordDuration",
            "recordTime",
        ):
            try:
                value = normalized.get(key)
                if value not in (None, ""):
                    explicit_duration = int(float(str(value).strip()))
                    break
            except (TypeError, ValueError):
                continue

        if normalized.get("beginTime") in (None, "") and start_ms is not None:
            normalized["beginTime"] = start_ms
        if normalized.get("endTime") in (None, "") and end_ms is not None:
            normalized["endTime"] = end_ms

        if normalized.get("duration") in (None, "") or normalized.get("duracao") in (None, ""):
            if explicit_duration is not None and explicit_duration >= 0:
                normalized.setdefault("duration", explicit_duration)
                normalized.setdefault("duracao", explicit_duration)
            elif start_ms is not None and end_ms is not None and end_ms >= start_ms:
                duration_seconds = int((end_ms - start_ms) / 1000)
                normalized.setdefault("duration", duration_seconds)
                normalized.setdefault("duracao", duration_seconds)

        reason_code = str(
            normalized.get("callReasonCode")
            or normalized.get("leaveReason")
            or ""
        ).strip()
        if reason_code:
            normalized.setdefault("callReasonCode", reason_code)

        return normalized

    @staticmethod
    def _coerce_huawei_datetime_string(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if any(char in text for char in ("-", "/", ":")) and not text.isdigit():
            return text

        millis = HuaweiAICCClient._coerce_epoch_millis(text)
        if millis is None:
            return text

        timezone_name = (os.getenv("HUAWEI_TIMEZONE") or "America/Sao_Paulo").strip() or "America/Sao_Paulo"
        try:
            target_tz = ZoneInfo(timezone_name)
        except Exception:
            target_tz = timezone.utc

        return datetime.fromtimestamp(millis / 1000, tz=target_tz).strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # Helpers HTTP
    # ------------------------------------------------------------------

    async def _post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Optional[httpx.Response]:
        """Envia POST assinado e devolve o Response bruto (para JSON ou binario)."""
        headers = await self._build_auth_headers("POST", url, payload)
        if not headers:
            return None

        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        to = timeout or self.timeout_seconds

        request_url = url
        # O redirecionamento de IP agora ├® feito via core.network_utils.apply_dns_overrides()
        # para preservar o SNI e evitar erro 418 (CloudWAF).
        default_verify = "true" 
        verify_ssl = os.getenv("HUAWEI_SSL_VERIFY", default_verify).lower() == "true"

        try:
            async with httpx.AsyncClient(timeout=to, verify=verify_ssl) as cli:
                return await cli.post(request_url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.error(
                "Huawei POST %s erro [%s]: %s",
                request_url,
                type(exc).__name__,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Endpoints CMS (CC-CMS)
    # ------------------------------------------------------------------

    async def buscar_historico_chamadas(
        self,
        begin_ms: int,
        end_ms: int,
        *,
        agent_id: Optional[str] = None,
        media_type: Optional[str] = None,
        call_direction: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Consulta /rest/cmsapp/v2/openapi/vdn/querycalls.

        Atencao: conforme a collection Postman, `beginDate`/`endDate` devem
        ser enviados como STRINGS de epoch em ms, e `isCallIn` tambem como
        string "true"/"false".

        O endpoint `querycalls` nao aceita filtro por operador, tipo de midia
        ou paginacao via `limit`/`offset`. Esses parametros ficam na assinatura
        do metodo por compatibilidade com chamadas antigas, mas nao entram no
        payload enviado a Huawei para evitar filtros silenciosamente ignorados
        ou rejeitados pelo gateway.
        """
        url = f"{self.cms_url}/rest/cmsapp/v2/openapi/vdn/querycalls"
        payload: Dict[str, Any] = {
            "ccId": self.cc_id,
            "vdn": self.vdn,
            "beginDate": str(begin_ms),
            "endDate": str(end_ms),
        }

        # A Huawei exige o parametro `isCallIn`; quem precisa de ambos os
        # sentidos deve chamar este metodo uma vez por direcao.
        payload["isCallIn"] = "false" if str(call_direction).upper() == "INBOUND" else "true"

        resp = await self._post_json(url, payload)
        if resp is None:
            return []
        if resp.status_code != 200:
            logger.error("Huawei CMS /querycalls HTTP %s: %s", resp.status_code, resp.text[:500])
            return []
        try:
            data = resp.json()
        except ValueError:
            logger.error("Huawei CMS /querycalls devolveu nao-JSON: %s", resp.text[:200])
            return []
        if str(data.get("resultCode")) != "0100000":
            logger.error(
                "Huawei CMS retornou codigo %s: %s",
                data.get("resultCode"),
                data.get("resultDesc"),
            )
            return []
        rd = data.get("resultDesc")
        if isinstance(rd, dict):
            return [
                self._normalize_querycalls_row(item)
                for item in (rd.get("data", []) or [])
            ]
        return []

    async def consultar_detalhe_chamada(self, call_id: str) -> Optional[Dict[str, Any]]:
        """GET /rest/cmsapp/v1/openapi/calldata/querybasiccallinfo."""
        url = f"{self.cms_url}/rest/cmsapp/v1/openapi/calldata/querybasiccallinfo"
        payload = {"ccId": self.cc_id, "vdn": self.vdn, "callId": call_id}
        resp = await self._post_json(url, payload)
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Endpoints FS (CC-FS)
    # ------------------------------------------------------------------

    async def obter_url_audio_obs(
        self,
        call_id: str,
        begin_time: str,
        end_time: str,
    ) -> Optional[str]:
        """POST /CCFS/resource/ccfs/getRecordFileUrlFromObs.

        `begin_time`/`end_time` no formato "YYYY-MM-DD HH:MM:SS".
        """
        url = f"{self.fs_url}/CCFS/resource/ccfs/getRecordFileUrlFromObs"
        
        async def _tentar(cid: str) -> Optional[str]:
            payload = {
                "callId": cid,
                "beginTime": self._coerce_huawei_datetime_string(begin_time),
                "endTime": self._coerce_huawei_datetime_string(end_time),
                "version": "2.0",
            }
            resp = await self._post_json(url, payload)
            if resp is None or resp.status_code != 200:
                return None
            try:
                data = resp.json()
            except ValueError:
                return None
            
            result_code = str(data.get("resultCode") or "")
            if result_code == "0100000":
                return (
                    (data.get("resultData") or {}).get("url")
                    or (data.get("resultData") or {}).get("obsFileUrl")
                    or data.get("url")
                )
            return result_code

        # Tentativa 1: CallId completo
        resultado = await _tentar(call_id)
        if isinstance(resultado, str) and (resultado.startswith("http") or resultado.startswith("https")):
            return resultado

        # Tentativa 2: Se falhou com 0300028 (param error) e tem hifen, tenta a parte 2 (RecordId)
        if "-" in call_id and (resultado == "0300028" or not resultado):
            short_id = call_id.split("-")[-1]
            logger.info("Huawei FS: callId longo falhou (0300028), tentando ID curto: %s", short_id)
            resultado_curto = await _tentar(short_id)
            if isinstance(resultado_curto, str) and (resultado_curto.startswith("http") or resultado_curto.startswith("https")):
                return resultado_curto
        
        if resultado and resultado != "0300012": # 0300012 e normal "nao encontrado"
             logger.error("Huawei FS getRecordFileUrlFromObs falhou para call %s: resultCode=%s", call_id, resultado)

        return None

    async def baixar_audio_ram(self, obs_url: str) -> Optional[bytes]:
        """GET direto na URL pre-assinada do OBS."""
        headers = {}
        request_url = obs_url

        # O redirecionamento de IP agora ├® feito via core.network_utils.apply_dns_overrides()
        default_verify = "true"
        verify_ssl = os.getenv("HUAWEI_SSL_VERIFY", default_verify).lower() == "true"

        try:
            async with httpx.AsyncClient(timeout=120.0, verify=verify_ssl) as cli:
                resp = await cli.get(request_url, headers=headers)
        except httpx.HTTPError as exc:
            logger.error(
                "Download OBS pre-assinada erro [%s]: %s",
                type(exc).__name__,
                exc,
            )
            return None
        if resp.status_code != 200:
            logger.error(
                "Download OBS pre-assinada HTTP %s (body: %s)",
                resp.status_code,
                resp.text[:200],
            )
            return None
        return resp.content

    async def baixar_gravacao_por_callid(self, call_id: str) -> Optional[bytes]:
        """POST /CCFS/resource/ccfs/downloadRecord.

        Fluxo de 1 etapa: manda callId, recebe o binario (ou URL). Mais simples
        que OBS para audios unicos. Se a Huawei retornar JSON com fileName,
        delegamos para downloadRecordFile.
        """
        url = f"{self.fs_url}/CCFS/resource/ccfs/downloadRecord"

        async def _tentar(cid: str) -> Optional[bytes]:
            payload = {
                "request": {"version": "2.0"},
                "msgBody": {"callId": cid, "ccId": self.cc_id},
            }
            resp = await self._post_json(url, payload, timeout=120.0)
            if resp is None:
                return None
            if resp.status_code != 200:
                return None
            
            ctype = resp.headers.get("content-type", "").lower()
            if "application/json" in ctype:
                try:
                    data = resp.json()
                except ValueError:
                    return None
                
                result_code = str(data.get("resultCode") or "")
                if result_code and result_code != "0100000":
                    return result_code.encode("utf-8") # Retorna o codigo como bytes para sinalizar erro
                
                file_name = (data.get("msgBody") or data.get("resultData") or {}).get("fileName")
                if file_name:
                    return await self.baixar_gravacao_por_filename(file_name)
                return None
            
            return resp.content

        # Tentativa 1: CallId completo
        resultado = await _tentar(call_id)
        if isinstance(resultado, bytes) and len(resultado) > 100: # Sucesso (binario WAV)
            return resultado
        
        # Tentativa 2: Se falhou e tem hifen, tenta a parte 2 (RecordId)
        # 0300028 e param error, mas tentamos para qualquer erro se houver hifen.
        if "-" in call_id:
            short_id = call_id.split("-")[-1]
            logger.info("Huawei FS downloadRecord: callId longo falhou, tentando ID curto: %s", short_id)
            resultado_curto = await _tentar(short_id)
            if isinstance(resultado_curto, bytes) and len(resultado_curto) > 100:
                return resultado_curto

        return None

    async def baixar_gravacao_por_filename(self, file_name: str) -> Optional[bytes]:
        """POST /CCFS/resource/ccfs/downloadRecordFile."""
        url = f"{self.fs_url}/CCFS/resource/ccfs/downloadRecordFile"
        payload = {
            "request": {"version": "2.0"},
            "msgBody": {"fileName": file_name},
        }
        resp = await self._post_json(url, payload, timeout=120.0)
        if resp is None or resp.status_code != 200:
            logger.error("Huawei FS downloadRecordFile falhou para %s", file_name)
            return None
        return resp.content

    async def baixar_chat_json(self, call_id: str) -> List[Dict[str, Any]]:
        """Obtem o transcript JSON de uma interacao multimidia (WhatsApp).

        Endpoint sujeito a confirmacao. A collection oficial cobre apenas
        CC-Messaging para envio; para leitura de historico multimidia, o
        proprio queryCalls retorna mensagens no campo `messageList` em alguns
        contextos. Mantemos este metodo como best-effort.
        """
        url = f"{self.cms_url}/rest/cmsapp/v1/openapi/multimedia/querycontent"
        payload = {"callId": call_id, "ccId": self.cc_id, "vdn": self.vdn}
        resp = await self._post_json(url, payload)
        if resp is None or resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except ValueError:
            return []
        rd = data.get("resultDesc")
        if isinstance(rd, dict):
            return rd.get("messages", []) or []
        return []
