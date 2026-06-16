from __future__ import annotations
"""Cliente OBS direto para fallback de download de gravacoes Huawei.

Quando a CC-FS retorna `resultCode 0300012 ("No data found")` mesmo com a
chamada existindo na VDN, ainda assim o arquivo `.V3` (que e na verdade um
WAV G.711 A-law com header RIFF padrao) costuma estar disponivel no bucket
OBS:

    Voice/{YYYYMMDD}/{callerNo|calleeNo|agentId}/{YYYYMMDDHHMMSS}-{callIdPart1}-{callIdPart2}.V3

Este modulo expoe um cliente assincrono que:
  1. Assina requests OBS v2 (HMAC-SHA1 + Base64), igual o pre-request script
     da collection Postman da OPENTECH.
  2. Lista `.V3` por (data, prefixo de pasta) com cache em memoria por instancia.
  3. Localiza o arquivo correspondente a um `call_id` via sufixo `-{callId}.V3`.
  4. Devolve os bytes (que ja sao WAV A-law - nao precisa converter).

Importante:
  - Cache vive enquanto a instancia existe. O sync cria 1 instancia por ciclo
    de `executar_sync_huawei`, entao a cache nao vaza entre ciclos.
  - Tentamos a data em UTC primeiro e em America/Sao_Paulo como fallback,
    porque a Huawei pode rotacionar a pasta em qualquer um dos dois.
"""


import base64
import csv
import hashlib
import hmac
import io
import logging
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email.utils import formatdate
from typing import AsyncIterator, Optional, Tuple
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception_type, stop_after_delay

from core.huawei_http_session import HuaweiHttpSession
from core.huawei_events import HuaweiEvents

logger = logging.getLogger(__name__)

class WafRateLimitError(Exception):
    """Erro lançado quando o WAF da Huawei ou o gateway retorna 403, 429 ou 502."""
    pass

DEFAULT_OBS_ENDPOINT = "obs.sa-brazil-1.myhuaweicloud.com"
DEFAULT_BUCKET = "obs-nstech-opentech"
LIST_TIMEOUT = 30.0
DOWNLOAD_TIMEOUT = 120.0


class HuaweiOBSClient:
    """Cliente leve para o bucket OBS de gravacoes."""

    def __init__(
        self,
        ak: str,
        sk: str,
        bucket: str,
        endpoint: str = DEFAULT_OBS_ENDPOINT,
        *,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        """Configura o cliente OBS com credenciais, bucket e endpoint.

        Params:
        - ak / sk: Access Key e Secret Key OBS (usadas na assinatura HMAC-SHA1).
        - bucket: nome do bucket (cai em DEFAULT_BUCKET se vazio).
        - endpoint: host OBS (default sa-brazil-1).
        - http_client: `httpx.AsyncClient` compartilhado do ciclo (reaproveita
          Keep-Alive/TLS). Se None, cada operacao cria o seu proprio cliente
          (modo usado em testes).

        Inicializa caches em memoria por instancia (listagens .V3, manifests
        CSV/linhas e presenca de objetos em Voice/{date}/) — vivem apenas
        enquanto a instancia existir, ou seja, por ciclo de sync.
        """
        self.ak = ak
        self.sk = sk
        self.bucket = bucket or DEFAULT_BUCKET
        self.endpoint = endpoint
        self._base_url = f"https://{self.bucket}.{self.endpoint}"
        # Cliente HTTP compartilhado entre as chamadas do ciclo. Quando informado,
        # reutiliza Keep-Alive/TLS handshake (economiza ~100ms por listagem). Se
        # None, cada operacao instancia seu proprio cliente (compat. com testes).
        self._http_client = http_client
        # cache: chave (date_str, folder_prefix) -> lista de keys .V3
        self._list_cache: dict[Tuple[str, str], list[str]] = {}
        self._manifest_csv_cache: dict[str, list[str]] = {}
        self._manifest_rows_cache: dict[str, list[dict[str, str]]] = {}
        # cache: date_str -> True se Voice/{date}/ tem ao menos 1 objeto.
        # Usado pelo sync como early-return quando a Huawei nao depositou os
        # .V3 do dia ainda (incidente upstream observado em 2026-05-06).
        self._voice_dir_cache: dict[str, bool] = {}

    @asynccontextmanager
    async def _client(self, timeout: float) -> AsyncIterator[httpx.AsyncClient]:
        if self._http_client is not None:
            yield self._http_client
            return
        async with httpx.AsyncClient(timeout=timeout) as cli:
            yield cli

    # ------------------------------------------------------------------
    # Assinatura OBS v2
    # ------------------------------------------------------------------

    def _sign(self, method: str, object_key: str = "") -> dict[str, str]:
        date_str = formatdate(timeval=None, localtime=False, usegmt=True)
        canonicalized = f"/{self.bucket}/"
        if object_key:
            canonicalized += object_key
        string_to_sign = f"{method}\n\n\n{date_str}\n{canonicalized}"
        signature = base64.b64encode(
            hmac.new(
                self.sk.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        return {
            "Date": date_str,
            "Authorization": f"OBS {self.ak}:{signature}",
        }

    # ------------------------------------------------------------------
    # Conversao de data
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_to_epoch_ms(value) -> Optional[int]:
        """Aceita ms (int/str), s (int/str < 1e10) ou string ISO-ish."""
        if value is None or value == "":
            return None
        try:
            numeric = int(float(value))
            if numeric <= 0:
                return None
            if numeric < 10_000_000_000:  # parece estar em segundos
                numeric *= 1000
            return numeric
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                # CSV manifesto da Huawei envia datetimes ISO em UTC; assumir
                # BRT desalinhava `_candidate_dates` em chamadas perto da meia-noite.
                dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1000)
            except ValueError:
                continue
        return None

    @classmethod
    def _candidate_dates(cls, begin_time) -> list[str]:
        """Retorna ate 2 strings YYYYMMDD candidatas (UTC e BRT)."""
        ms = cls._coerce_to_epoch_ms(begin_time)
        if ms is None:
            return []
        seconds = ms / 1000
        utc = datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y%m%d")
        try:
            brt = datetime.fromtimestamp(seconds, tz=ZoneInfo("America/Sao_Paulo")).strftime(
                "%Y%m%d"
            )
        except Exception:
            brt = utc
        if brt == utc:
            return [utc]
        return [utc, brt]

    @classmethod
    def _date_with_neighbors(cls, begin_time, end_time=None) -> list[str]:
        """Datas YYYYMMDD candidatas para localizar o `.V3` no OBS.

        Estrategia (encolhida em 2026-05 apos perfilamento):
        - Inclui o dia do beginTime em UTC e BRT — cobre 100% das chamadas
          comuns (Huawei pode usar qualquer dos dois para nomear a pasta).
        - Inclui o dia do endTime em UTC e BRT QUANDO end_time foi informado e
          cai em outro dia. Cobre chamadas que cruzam meia-noite — a Huawei
          nomeia a pasta do `.V3` pelo timestamp do arquivo, que é >= endTime.
        - Nunca inclui D-1: na pratica nao ha `.V3` armazenado no dia anterior
          ao beginTime, e expandir D-1 dobrava o custo de listagens cegas.
        """
        expanded: list[str] = []
        seen: set[str] = set()

        def add(candidate: str) -> None:
            if candidate and candidate not in seen:
                seen.add(candidate)
                expanded.append(candidate)

        for date_str in cls._candidate_dates(begin_time):
            add(date_str)

        if end_time is not None:
            begin_ms = cls._coerce_to_epoch_ms(begin_time)
            end_ms = cls._coerce_to_epoch_ms(end_time)
            if end_ms is not None and (begin_ms is None or end_ms > begin_ms):
                # Iterar TODOS os dias entre begin e end (UTC e BRT) — cobre
                # janelas manuais que atravessam multiplos dias. Sem este loop,
                # janelas >2 dias perdiam os dias intermediarios.
                if begin_ms is not None:
                    begin_seconds = int(begin_ms) // 1000
                    end_seconds = int(end_ms) // 1000
                    cursor = datetime.fromtimestamp(begin_seconds, tz=timezone.utc).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    end_dt = datetime.fromtimestamp(end_seconds, tz=timezone.utc)
                    while cursor <= end_dt:
                        add(cursor.strftime("%Y%m%d"))
                        cursor = cursor + timedelta(days=1)
                # Garante que o dia exato do endTime tambem entre (UTC + BRT)
                for date_str in cls._candidate_dates(end_time):
                    add(date_str)

        return expanded

    @staticmethod
    def _shift_date(date_str: str, days: int) -> str:
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
        except (TypeError, ValueError):
            return ""
        return (dt + timedelta(days=days)).strftime("%Y%m%d")

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _list_keys(self, prefix: str, max_keys: int = 1000) -> list[str]:
        """Faz GET ?prefix=...&max-keys=... e retorna lista de Key.

        Pagina 1 unica (max-keys=1000). Para uma janela de 1 hora por agente,
        e mais que suficiente.
        """
        url = f"{self._base_url}/?prefix={quote(prefix, safe='/-_.')}&max-keys={max_keys}"
        headers = self._sign("GET")
        try:
            async with self._client(LIST_TIMEOUT) as cli:
                resp = await cli.get(url, headers=headers, timeout=LIST_TIMEOUT)
        except httpx.HTTPError as exc:
            logger.error("OBS LIST %s erro de rede: %s", prefix, exc)
            return []
        if resp.status_code != 200:
            logger.error(
                "OBS LIST %s HTTP %s: %s", prefix, resp.status_code, resp.text[:300]
            )
            return []
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as exc:
            logger.error("OBS LIST %s XML invalido: %s", prefix, exc)
            return []
        keys = [
            elem.text
            for elem in root.findall(".//{*}Key")
            if elem.text
        ]
        return keys

    async def _download_object(self, object_key: str) -> Optional[bytes]:
        """GET assinado direto no objeto OBS.

        Sem tenacity, sem pool singleton: usa o mesmo `_client()` da listagem
        (que e provadamente correto — diag_huawei_obs_download.py confirmou
        em 2026-05-06 que as 3 variantes baixam com sucesso quando o objeto
        existe). Erros sobem com status real, sem retry mascarando a causa.
        """
        url = f"{self._base_url}/{quote(object_key, safe='/-_.')}"
        headers = self._sign("GET", object_key=object_key)
        try:
            async with self._client(DOWNLOAD_TIMEOUT) as cli:
                resp = await cli.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT)
        except httpx.HTTPError as exc:
            logger.error("OBS GET %s erro de rede: %s", object_key, exc)
            return None
        if resp.status_code != 200:
            logger.error(
                "OBS GET %s HTTP %s: %s",
                object_key,
                resp.status_code,
                resp.text[:200] if resp.text else "(binario)",
            )
            return None
        return resp.content

    async def _download_text_object(self, object_key: str) -> Optional[str]:
        data = await self._download_object(object_key)
        if data is None:
            return None
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    @staticmethod
    def _prefix_values(prefixes) -> list[object]:
        if prefixes is None:
            return []
        if isinstance(prefixes, (str, int, float)):
            return [prefixes]
        try:
            return list(prefixes)
        except TypeError:
            return [prefixes]

    @staticmethod
    def _digits_only(value: object) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @classmethod
    def _phone_folder_variants(cls, value: object) -> list[str]:
        text = str(value or "").strip()
        digits = cls._digits_only(text)
        variants: list[str] = []

        def add(candidate: str) -> None:
            candidate = str(candidate or "").strip()
            if candidate and candidate not in variants:
                variants.append(candidate)

        add(text)
        if digits and digits != text:
            add(digits)

        if len(digits) < 8:
            return variants

        if digits.startswith("55") and len(digits) in {12, 13}:
            local = digits[2:]
            add(local)
            add(f"0{local}")
            add(f"00{local}")
        elif digits.startswith("0"):
            add(digits.lstrip("0"))
            if digits.startswith("0") and not digits.startswith("00"):
                add(f"0{digits}")
        else:
            add(f"0{digits}")
            add(f"00{digits}")

        return variants

    @classmethod
    def _normalize_prefixes(cls, prefixes, *, expand_phone_variants: bool = True) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        def add(candidate: object) -> None:
            text = str(candidate or "").strip()
            if not text or text.lower() in {"none", "null"}:
                return
            if text in seen:
                return
            seen.add(text)
            normalized.append(text)

        raw_values = cls._prefix_values(prefixes)
        for raw in raw_values:
            if raw is None:
                continue
            add(str(raw).strip())
            digits = cls._digits_only(raw)
            if digits:
                add(digits)

        if not expand_phone_variants:
            return normalized

        for raw in raw_values:
            if raw is None:
                continue
            for candidate in cls._phone_folder_variants(raw):
                add(candidate)
        return normalized

    @classmethod
    def _normalize_match_ids(cls, values) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in cls._prefix_values(values):
            text = str(raw or "").strip()
            if not text or text.lower() in {"none", "null"}:
                continue
            if text in seen:
                continue
            seen.add(text)
            normalized.append(text)
            
            # Auto-add the short callId (seq part) if it has a hyphen
            if "-" in text:
                short = text.split("-")[-1]
                if short and short not in seen:
                    seen.add(short)
                    normalized.append(short)
        return normalized

    async def voice_dir_has_objects(self, date_str: str) -> bool:
        """Retorna True se Voice/{date}/ contem ao menos 1 objeto no bucket.

        Defesa contra incidente upstream: quando a Huawei atrasa a deposicao
        dos .V3 do dia (cenario observado em 2026-05-06), o sync deve
        detectar antes de gastar 3 fallbacks por candidato. Resultado e
        cacheado por data por instancia (1 chamada por data por ciclo).
        """
        if not date_str:
            return True
        if date_str in self._voice_dir_cache:
            return self._voice_dir_cache[date_str]
        keys = await self._list_keys(f"Voice/{date_str}/", max_keys=1)
        has = bool(keys)
        self._voice_dir_cache[date_str] = has
        if not has:
            logger.warning(
                "OBS Voice/%s/ vazio: Huawei ainda nao depositou audios do dia.",
                date_str,
            )
            # Evento JSON dedicado: permite filtrar no Cloud Logging
            # como categoria distinta de DOWNLOAD_FAILED (que indica falha
            # de auth/rede). Aqui o problema e' upstream — nao adianta retry.
            HuaweiEvents.log_event(
                "OBS_VOICE_DIR_EMPTY",
                call_id=None,
                context={"date": date_str, "bucket": self.bucket},
                severity="WARNING",
            )
        return has

    async def listar_v3_por_prefixo(
        self,
        date_str: str,
        folder_prefix: str,
    ) -> list[str]:
        """Lista as keys .V3 sob Voice/{date}/{folder_prefix}/ com cache."""
        if not date_str or not folder_prefix:
            return []
        folder_prefix = str(folder_prefix).strip()
        if not folder_prefix:
            return []
        cache_key = (date_str, folder_prefix)
        if cache_key in self._list_cache:
            return self._list_cache[cache_key]
        prefix = f"Voice/{date_str}/{folder_prefix}/"
        keys = [k for k in await self._list_keys(prefix) if k.lower().endswith(".v3")]
        self._list_cache[cache_key] = keys
        if not keys:
            logger.info(
                "OBS Voice/%s/%s/ vazio (prefixo sem objetos .V3).",
                date_str,
                folder_prefix,
            )
        return keys

    async def listar_v3_por_agente(
        self,
        date_str: str,
        agent_id: str,
    ) -> list[str]:
        """Compatibilidade: lista usando agentId como prefixo de pasta."""
        return await self.listar_v3_por_prefixo(date_str, agent_id)

    @staticmethod
    def _matches_call(key: str, call_id: str) -> bool:
        # callId pode vir como "1777173597-800148" (com hifen) ou puro.
        # O nome do arquivo termina sempre em "-{callId}.V3".
        match_id = str(call_id or "").strip()
        if not match_id:
            return False
        return str(key or "").lower().endswith(f"-{match_id}.v3".lower())

    @classmethod
    def _matches_any_call_id(cls, key: str, match_ids: list[str]) -> bool:
        return any(cls._matches_call(key, match_id) for match_id in match_ids)

    async def listar_contact_record_csvs(self, date_str: str) -> list[str]:
        """Lista manifests CSV da Huawei em Contact_Record para uma data."""
        if not date_str:
            return []
        if date_str in self._manifest_csv_cache:
            return self._manifest_csv_cache[date_str]
        prefix = f"Contact_Record/contact-record/10-minutes/{date_str}/"
        keys = [k for k in await self._list_keys(prefix) if k.lower().endswith(".csv")]
        keys = sorted(keys)
        self._manifest_csv_cache[date_str] = keys
        if not keys:
            logger.info("OBS Contact_Record/%s vazio.", date_str)
        return keys

    async def listar_contact_record_rows(self, date_str: str) -> list[dict[str, str]]:
        """Carrega e cacheia as linhas dos manifests CSV de uma data."""
        if not date_str:
            return []
        if date_str in self._manifest_rows_cache:
            return self._manifest_rows_cache[date_str]
        rows: list[dict[str, str]] = []
        for key in await self.listar_contact_record_csvs(date_str):
            text = await self._download_text_object(key)
            if not text:
                continue
            try:
                reader = csv.DictReader(io.StringIO(text))
                for row in reader:
                    rows.append({str(k or ""): str(v or "") for k, v in (row or {}).items()})
            except csv.Error as exc:
                logger.warning("OBS Contact_Record CSV invalido %s: %s", key, exc)
        self._manifest_rows_cache[date_str] = rows
        logger.info("OBS Contact_Record/%s carregado: %d linha(s).", date_str, len(rows))
        return rows

    @staticmethod
    def _manifest_row_values(row: dict[str, str], *keys: str) -> list[str]:
        values: list[str] = []
        for key in keys:
            value = str(row.get(key) or "").strip()
            if value:
                values.append(value)
        return values

    @classmethod
    def _manifest_row_matches(cls, row: dict[str, str], match_ids: list[str]) -> bool:
        row_ids = cls._manifest_row_values(
            row,
            "callId",
            "recordId",
            "contactId",
            "callSerialno",
            "associateCall",
            "IVRCALLID",
        )
        return bool(set(row_ids).intersection(match_ids))

    @classmethod
    def _manifest_prefixes(cls, row: dict[str, str]) -> list[str]:
        return cls._manifest_row_values(
            row,
            "caller",
            "called",
            "oriCallednum",
            "callNo",
            "workNo",
        )

    @classmethod
    def _manifest_match_ids(cls, row: dict[str, str], call_id: str) -> list[str]:
        return cls._normalize_match_ids(
            [
                call_id,
                *cls._manifest_row_values(row, "callId", "recordId", "contactId", "callSerialno"),
            ]
        )

    async def _baixar_por_prefixos_e_ids(
        self,
        *,
        date_str: str,
        prefixes: list[str],
        match_ids: list[str],
    ) -> Optional[bytes]:
        for folder_prefix in prefixes:
            keys = await self.listar_v3_por_prefixo(date_str, folder_prefix)
            if not keys:
                continue
            matches = [k for k in keys if self._matches_any_call_id(k, match_ids)]
            if not matches:
                continue
            # Em caso de duplicatas (transferencia/conferencia gravam 2 lados),
            # pegamos a chave lexicograficamente maior (timestamp mais alto).
            chosen = sorted(matches)[-1]
            data = await self._download_object(chosen)
            if data:
                logger.info(
                    "OBS hit: ids=%s prefix=%s date=%s key=%s bytes=%d",
                    ",".join(match_ids),
                    folder_prefix,
                    date_str,
                    chosen,
                    len(data),
                )
                return data
        return None

    async def baixar_voice_por_callid(
        self,
        call_id: str,
        prefixes=None,
        begin_time=None,
        *,
        agent_id: Optional[str] = None,
        extra_match_ids=None,
        end_time=None,
    ) -> Optional[bytes]:
        """Resolve `Voice/{date}/{prefix}/<...>-{callId}.V3` e baixa.

        Retorna `None` quando nao encontra. Tenta UTC e BRT como datas
        candidatas e todos os prefixos informados, na ordem recebida. Se a
        busca direta falhar, consulta o manifest `Contact_Record` para achar
        `caller/called/recordId` oficiais da Huawei. O conteudo retornado e
        WAV A-law puro - basta salvar com extensao .wav.
        """
        raw_prefixes = self._prefix_values(prefixes)
        if agent_id:
            raw_prefixes.append(agent_id)
        folder_prefixes = self._normalize_prefixes(raw_prefixes)
        match_ids = self._normalize_match_ids([call_id, *self._prefix_values(extra_match_ids)])
        if not call_id or not match_ids:
            return None
        manifest_dates = set(self._candidate_dates(begin_time))
        if end_time is not None:
            manifest_dates.update(self._candidate_dates(end_time))
        for date_str in self._date_with_neighbors(begin_time, end_time):
            if folder_prefixes:
                data = await self._baixar_por_prefixos_e_ids(
                    date_str=date_str,
                    prefixes=folder_prefixes,
                    match_ids=match_ids,
                )
                if data:
                    return data

            if date_str not in manifest_dates:
                continue
            manifest_rows = await self.listar_contact_record_rows(date_str)
            for row in manifest_rows:
                if not self._manifest_row_matches(row, match_ids):
                    continue
                manifest_prefixes = self._normalize_prefixes(
                    [*self._manifest_prefixes(row), *folder_prefixes]
                )
                if not manifest_prefixes:
                    continue
                manifest_match_ids = self._manifest_match_ids(row, call_id)
                logger.info(
                    "OBS Contact_Record match: callId=%s date=%s recordId=%s prefixes=%s",
                    call_id,
                    date_str,
                    row.get("recordId") or "",
                    manifest_prefixes[:5],
                )
                data = await self._baixar_por_prefixos_e_ids(
                    date_str=date_str,
                    prefixes=manifest_prefixes,
                    match_ids=manifest_match_ids,
                )
                if data:
                    return data
                    
        # Log diagnostico ao final de todos os misses
        sample_keys = []
        try:
            for date_str in self._date_with_neighbors(begin_time, end_time):
                keys = await self._list_keys(f"Voice/{date_str}/", max_keys=5)
                if keys:
                    sample_keys.extend(keys)
                    break
        except Exception:
            pass
            
        logger.warning(
            "OBS miss callId=%s prefixes_tried=%s match_ids=%s dates_tried=%s sample_keys=%s",
            call_id,
            folder_prefixes,
            match_ids,
            list(self._date_with_neighbors(begin_time, end_time)),
            sample_keys[:5]
        )

        return None

    # Util para smoke test / debugging --------------------------------

    async def listar_v3_do_dia(self, date_str: str) -> list[str]:
        """Lista TUDO de Voice/{date}/ - so usar em debug; pode ser caro."""
        prefix = f"Voice/{date_str}/"
        return [k for k in await self._list_keys(prefix) if k.lower().endswith(".v3")]
