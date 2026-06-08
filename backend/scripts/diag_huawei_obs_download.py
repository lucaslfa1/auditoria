from __future__ import annotations
"""Diagnostico isolado: baixar 1 objeto OBS via HMAC-SHA1 puro.

Objetivo: validar QUAL caminho de download OBS funciona em producao,
sem depender de:
  - HuaweiOBSClient (que tem retries opacos)
  - HuaweiHttpSession singleton (que tem follow_redirects=True)
  - tenacity
  - pool reusado entre clientes

Uso:
    cd backend && python -m scripts.diag_huawei_obs_download \\
        --call-id 1778081569-604381 \\
        --call-id 1778079327-79583 \\
        --keys-file "C:\\Users\\lucas.afonso\\projetos\\Novas Chaves OBS Huawei.txt"

O script imprime, para cada callId:
  1. Datas candidatas testadas (UTC + BRT)
  2. Se achou row no manifesto Contact_Record
  3. Quais prefixos foram tentados
  4. Quais keys .V3 foram encontradas
  5. Para a primeira key encontrada, o status de 3 variantes de download:
     - V1: quote(key, safe='/-_.') na URL + canonical sem encode (estado atual)
     - V2: key bruto na URL + canonical sem encode (sem quote)
     - V3: V1 + httpx sem follow_redirects (cliente isolado)

NAO faz upload, NAO altera nada. Read-only.
"""


import argparse
import asyncio
import base64
import csv
import hashlib
import hmac
import io
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

DEFAULT_KEYS_FILE = r"C:\Users\lucas.afonso\projetos\Novas Chaves OBS Huawei.txt"
DEFAULT_BUCKET = "obs-nstech-opentech"
DEFAULT_ENDPOINT = "obs.sa-brazil-1.myhuaweicloud.com"
LIST_TIMEOUT = 30.0
DOWNLOAD_TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# Credenciais
# ---------------------------------------------------------------------------

def parse_keys_file(path: str) -> tuple[str, str]:
    """Le AK e SK de um arquivo texto livre. Aceita formatos:
        AK: <valor>
        SK: <valor>
        AK = <valor>
        access_key_id: <valor>
        secret_access_key: <valor>
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    ak: Optional[str] = None
    sk: Optional[str] = None
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_\- ]*)\s*[:=]\s*(.+?)\s*$", line)
        if not m:
            continue
        key = m.group(1).strip().lower().replace(" ", "_").replace("-", "_")
        val = m.group(2).strip().strip('"').strip("'")
        if key in {"ak", "access_key", "access_key_id", "huawei_obs_ak"}:
            ak = val
        elif key in {"sk", "secret_key", "secret_access_key", "huawei_obs_sk"}:
            sk = val
    if not ak or not sk:
        raise SystemExit(
            f"AK/SK nao encontrados em {path}. Formato esperado: 'AK: ...' e 'SK: ...' (uma por linha)."
        )
    return ak, sk


# ---------------------------------------------------------------------------
# Assinatura OBS V2 (HMAC-SHA1)
# ---------------------------------------------------------------------------

def obs_sign(
    method: str,
    *,
    ak: str,
    sk: str,
    bucket: str,
    object_key: str = "",
) -> dict[str, str]:
    """Retorna {'Date': ..., 'Authorization': 'OBS ak:sig'}.

    Spec OBS V2: string_to_sign = METHOD\\n\\n\\n{Date}\\n/{bucket}/{key}
    Para listagem (?prefix=...&max-keys=...), a query string NAO entra no
    canonical (diferente de S3 V4).
    """
    date_str = formatdate(timeval=None, localtime=False, usegmt=True)
    canonicalized = f"/{bucket}/"
    if object_key:
        canonicalized += object_key
    string_to_sign = f"{method}\n\n\n{date_str}\n{canonicalized}"
    signature = base64.b64encode(
        hmac.new(sk.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    return {
        "Date": date_str,
        "Authorization": f"OBS {ak}:{signature}",
    }


# ---------------------------------------------------------------------------
# Helpers HTTP (sem pool, sem retry, sem follow_redirects por padrao)
# ---------------------------------------------------------------------------

async def list_keys(
    client: httpx.AsyncClient,
    base_url: str,
    ak: str,
    sk: str,
    bucket: str,
    prefix: str,
    max_keys: int = 1000,
) -> tuple[int, list[str], str]:
    url = f"{base_url}/?prefix={quote(prefix, safe='/-_.')}&max-keys={max_keys}"
    headers = obs_sign("GET", ak=ak, sk=sk, bucket=bucket)
    resp = await client.get(url, headers=headers, timeout=LIST_TIMEOUT)
    if resp.status_code != 200:
        return resp.status_code, [], resp.text[:500]
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        return resp.status_code, [], f"XML parse error: {exc}"
    keys = [el.text for el in root.findall(".//{*}Key") if el.text]
    return resp.status_code, keys, ""


async def download_text(
    client: httpx.AsyncClient,
    base_url: str,
    ak: str,
    sk: str,
    bucket: str,
    object_key: str,
) -> tuple[int, str]:
    url = f"{base_url}/{quote(object_key, safe='/-_.')}"
    headers = obs_sign("GET", ak=ak, sk=sk, bucket=bucket, object_key=object_key)
    resp = await client.get(url, headers=headers, timeout=LIST_TIMEOUT)
    if resp.status_code != 200:
        return resp.status_code, resp.text[:500]
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return 200, resp.content.decode(enc)
        except UnicodeDecodeError:
            continue
    return 200, resp.content.decode("utf-8", errors="replace")


async def download_variant(
    variant: str,
    *,
    base_url: str,
    ak: str,
    sk: str,
    bucket: str,
    object_key: str,
) -> dict[str, object]:
    """Tenta baixar 1 objeto em 3 variantes para isolar a causa do 403/falha."""
    if variant == "V1":  # Estado atual: quote na URL + canonical sem encode
        url = f"{base_url}/{quote(object_key, safe='/-_.')}"
        headers = obs_sign("GET", ak=ak, sk=sk, bucket=bucket, object_key=object_key)
        client_kwargs = {"timeout": DOWNLOAD_TIMEOUT, "follow_redirects": False}
    elif variant == "V2":  # Sem quote: URL crua + canonical idem
        url = f"{base_url}/{object_key}"
        headers = obs_sign("GET", ak=ak, sk=sk, bucket=bucket, object_key=object_key)
        client_kwargs = {"timeout": DOWNLOAD_TIMEOUT, "follow_redirects": False}
    elif variant == "V3":  # Estado atual MAS com follow_redirects=True (replica pool)
        url = f"{base_url}/{quote(object_key, safe='/-_.')}"
        headers = obs_sign("GET", ak=ak, sk=sk, bucket=bucket, object_key=object_key)
        client_kwargs = {"timeout": DOWNLOAD_TIMEOUT, "follow_redirects": True}
    else:
        raise ValueError(f"Variante desconhecida: {variant}")

    info: dict[str, object] = {"variant": variant, "url": url}
    try:
        async with httpx.AsyncClient(**client_kwargs) as cli:
            resp = await cli.get(url, headers=headers)
        info["status_code"] = resp.status_code
        info["content_length"] = len(resp.content) if resp.content else 0
        info["x_obs_error_code"] = resp.headers.get("x-obs-error-code", "")
        info["x_obs_request_id"] = resp.headers.get("x-obs-request-id", "")
        info["content_type"] = resp.headers.get("content-type", "")
        if resp.status_code == 200:
            head_bytes = resp.content[:4]
            info["is_riff"] = head_bytes == b"RIFF"
        else:
            info["body_preview"] = resp.text[:300] if resp.text else ""
    except Exception as exc:
        info["status_code"] = -1
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


# ---------------------------------------------------------------------------
# Logica de descoberta (sem depender de HuaweiOBSClient)
# ---------------------------------------------------------------------------

def candidate_dates_for_call_id(call_id: str) -> list[str]:
    """callId formato '<epoch_seconds>-<seq>'. Retorna [UTC_date, BRT_date]."""
    head = call_id.split("-", 1)[0]
    try:
        seconds = int(head)
    except ValueError:
        return []
    if seconds < 10_000_000_000:
        secs = seconds
    else:
        secs = seconds // 1000  # talvez veio em ms
    utc = datetime.fromtimestamp(secs, tz=timezone.utc).strftime("%Y%m%d")
    try:
        brt = datetime.fromtimestamp(secs, tz=ZoneInfo("America/Sao_Paulo")).strftime("%Y%m%d")
    except Exception:
        brt = utc
    return [utc] + ([brt] if brt != utc else [])


def find_row_by_call_id(rows: list[dict[str, str]], call_id: str) -> Optional[dict[str, str]]:
    short = call_id.split("-")[-1]
    for row in rows:
        for col in ("callId", "recordId", "contactId", "callSerialno", "associateCall", "IVRCALLID"):
            v = (row.get(col) or "").strip()
            if v == call_id or v == short:
                return row
    return None


def prefix_candidates_from_row(row: dict[str, str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for col in ("caller", "called", "oriCallednum", "callNo", "workNo"):
        v = (row.get(col) or "").strip()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
            digits = re.sub(r"\D", "", v)
            if digits and digits != v and digits not in seen:
                seen.add(digits)
                out.append(digits)
    return out


def matches_call_id(key: str, call_id: str) -> bool:
    short = call_id.split("-")[-1]
    low = key.lower()
    return low.endswith(f"-{call_id.lower()}.v3") or low.endswith(f"-{short.lower()}.v3")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def diagnose_call_id(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    ak: str,
    sk: str,
    bucket: str,
    call_id: str,
) -> None:
    print(f"\n{'='*80}\nDIAG callId={call_id}\n{'='*80}")

    dates = candidate_dates_for_call_id(call_id)
    print(f"  datas candidatas: {dates}")
    if not dates:
        print("  ERRO: nao foi possivel derivar data do callId")
        return

    # Passo A+B: encontrar row no manifesto
    found_row: Optional[dict[str, str]] = None
    found_date: Optional[str] = None
    for date_str in dates:
        manifest_prefix = f"Contact_Record/contact-record/10-minutes/{date_str}/"
        status, csv_keys, err = await list_keys(client, base_url, ak, sk, bucket, manifest_prefix)
        print(f"  manifesto {date_str}: status={status} csvs={len(csv_keys)} {('err='+err) if err else ''}")
        for csv_key in csv_keys:
            if not csv_key.lower().endswith(".csv"):
                continue
            s, text = await download_text(client, base_url, ak, sk, bucket, csv_key)
            if s != 200:
                print(f"    skip csv {csv_key}: status={s} preview={text[:100]}")
                continue
            try:
                rows = list(csv.DictReader(io.StringIO(text)))
            except csv.Error as exc:
                print(f"    csv parse error {csv_key}: {exc}")
                continue
            row = find_row_by_call_id(rows, call_id)
            if row is not None:
                found_row = row
                found_date = date_str
                print(f"    HIT em {csv_key}: caller={row.get('caller')} called={row.get('called')} "
                      f"recordId={row.get('recordId')} workNo={row.get('workNo')}")
                break
        if found_row:
            break

    if not found_row or not found_date:
        print(f"  RESULTADO: callId nao encontrado em nenhum manifesto das datas {dates}")
        return

    # Passo C: listar Voice/{date}/{prefix}/ e localizar .V3
    prefixes = prefix_candidates_from_row(found_row)
    print(f"  prefixos candidatos: {prefixes}")
    target_key: Optional[str] = None
    for prefix in prefixes:
        voice_prefix = f"Voice/{found_date}/{prefix}/"
        status, keys, err = await list_keys(client, base_url, ak, sk, bucket, voice_prefix)
        v3_keys = [k for k in keys if k.lower().endswith(".v3")]
        match = next((k for k in v3_keys if matches_call_id(k, call_id)), None)
        marker = "HIT" if match else "miss"
        print(f"    Voice/{found_date}/{prefix}/: status={status} v3s={len(v3_keys)} {marker} "
              f"{('err='+err) if err else ''}")
        if match:
            target_key = match
            break

    if not target_key:
        # Tenta tambem prefixo agentId / extras
        extras = [(found_row.get("agentId") or "").strip(), (found_row.get("workNo") or "").strip()]
        for extra in extras:
            if not extra:
                continue
            voice_prefix = f"Voice/{found_date}/{extra}/"
            status, keys, err = await list_keys(client, base_url, ak, sk, bucket, voice_prefix)
            v3_keys = [k for k in keys if k.lower().endswith(".v3")]
            match = next((k for k in v3_keys if matches_call_id(k, call_id)), None)
            print(f"    [extra] Voice/{found_date}/{extra}/: status={status} v3s={len(v3_keys)} "
                  f"{'HIT' if match else 'miss'}")
            if match:
                target_key = match
                break

    if not target_key:
        print(f"  RESULTADO: callId achado no manifesto mas .V3 nao localizado em prefixos {prefixes}")
        return

    print(f"\n  KEY ALVO: {target_key}")

    # Passo D: tentar 3 variantes
    print(f"  --- Variantes de download ---")
    for variant in ("V1", "V2", "V3"):
        info = await download_variant(
            variant,
            base_url=base_url,
            ak=ak,
            sk=sk,
            bucket=bucket,
            object_key=target_key,
        )
        status = info["status_code"]
        content_len = info.get("content_length", 0)
        is_riff = info.get("is_riff", False)
        marker = "OK" if status == 200 and is_riff else ("OK?" if status == 200 else "FAIL")
        line = (
            f"    [{variant}] {marker} status={status} bytes={content_len} riff={is_riff} "
            f"obs_err={info.get('x_obs_error_code') or '-'}"
        )
        print(line)
        if status != 200:
            preview = info.get("body_preview") or info.get("error") or ""
            if preview:
                print(f"        body/err: {preview[:200]}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnostico de download OBS Huawei (HMAC-SHA1 puro).")
    parser.add_argument("--call-id", action="append", required=True, help="callId Huawei (pode repetir)")
    parser.add_argument("--keys-file", default=DEFAULT_KEYS_FILE, help="Arquivo texto com 'AK: ...' e 'SK: ...'")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    args = parser.parse_args()

    ak, sk = parse_keys_file(args.keys_file)
    base_url = f"https://{args.bucket}.{args.endpoint}"

    print(f"DIAG OBS Huawei")
    print(f"  bucket={args.bucket}")
    print(f"  endpoint={args.endpoint}")
    print(f"  AK={ak[:6]}...{ak[-4:]} (len={len(ak)})")
    print(f"  call_ids={args.call_id}")

    # Cliente "limpo": sem follow_redirects, sem retries, criado uma vez por run.
    async with httpx.AsyncClient(timeout=LIST_TIMEOUT, follow_redirects=False) as client:
        for cid in args.call_id:
            try:
                await diagnose_call_id(
                    client,
                    base_url=base_url,
                    ak=ak,
                    sk=sk,
                    bucket=args.bucket,
                    call_id=cid,
                )
            except Exception as exc:  # diagnostico nao deve abortar
                print(f"  EXCECAO no callId {cid}: {type(exc).__name__}: {exc}")

    print(f"\n{'='*80}\nFim do diagnostico.\n{'='*80}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
