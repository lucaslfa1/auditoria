import os
import json
import base64
import hmac
import hashlib
import requests
import subprocess
from datetime import datetime, timedelta
from email.utils import formatdate
import xml.etree.ElementTree as ET
import csv

DOWNLOAD_CHUNK_SIZE = 1024 * 1024
FFMPEG_TIMEOUT_SECONDS = int(os.getenv("PROBE_FFMPEG_TIMEOUT_SECONDS", "60"))


def _get_default_http_timeout() -> float:
    raw = os.getenv("HTTP_TIMEOUT_SECONDS", "10")
    try:
        parsed = float(str(raw).strip().replace(",", "."))
    except (TypeError, ValueError):
        parsed = 10.0
    return max(1.0, parsed)


DEFAULT_HTTP_TIMEOUT = _get_default_http_timeout()


def _safe_get(session, url, headers, *, stream=False, timeout=DEFAULT_HTTP_TIMEOUT):
    return session.get(url, headers=headers, timeout=timeout, stream=stream)


def _safe_post(session, url, headers, *, data=None, json=None, timeout=DEFAULT_HTTP_TIMEOUT):
    return session.post(url, headers=headers, data=data, json=json, timeout=timeout)


def download_stream_to_file(response, output_path):
    total_bytes = 0
    head = bytearray()
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
            if not chunk:
                continue
            if len(head) < 32:
                head.extend(chunk[: 32 - len(head)])
            f.write(chunk)
            total_bytes += len(chunk)
    return total_bytes, bytes(head[:32])


def ffmpeg_commands(v3_path, out_dir):
    return [
        ("auto", ["ffmpeg", "-y", "-i", v3_path, os.path.join(out_dir, "auto.wav")]),
        ("mulaw", ["ffmpeg", "-y", "-f", "mulaw", "-ar", "8000", "-ac", "1", "-i", v3_path, os.path.join(out_dir, "mulaw.wav")]),
        ("alaw", ["ffmpeg", "-y", "-f", "alaw", "-ar", "8000", "-ac", "1", "-i", v3_path, os.path.join(out_dir, "alaw.wav")]),
        ("mulaw_skip44", ["ffmpeg", "-y", "-f", "mulaw", "-ar", "8000", "-ac", "1", "-skip_initial_bytes", "44", "-i", v3_path, os.path.join(out_dir, "mulaw_skip44.wav")]),
        ("alaw_skip44", ["ffmpeg", "-y", "-f", "alaw", "-ar", "8000", "-ac", "1", "-skip_initial_bytes", "44", "-i", v3_path, os.path.join(out_dir, "alaw_skip44.wav")]),
        ("mulaw_skip1024", ["ffmpeg", "-y", "-f", "mulaw", "-ar", "8000", "-ac", "1", "-skip_initial_bytes", "1024", "-i", v3_path, os.path.join(out_dir, "mulaw_skip1024.wav")]),
    ]

def get_credentials():
    ak = os.getenv("HUAWEI_OBS_AK")
    sk = os.getenv("HUAWEI_OBS_SK")
    bucket = os.getenv("HUAWEI_OBS_BUCKET", "obs-nstech-opentech")
    if not ak or not sk:
        creds_path = "obs_creds.json"
        if os.path.exists(creds_path):
            with open(creds_path, 'r') as f:
                creds = json.load(f)
                ak = creds.get("HUAWEI_OBS_AK")
                sk = creds.get("HUAWEI_OBS_SK")
                bucket = creds.get("HUAWEI_OBS_BUCKET", bucket)
    return ak, sk, bucket

def get_obs_auth_header(ak, sk, method, bucket, object_key="", is_csv=False):
    date_str = formatdate(timeval=None, localtime=False, usegmt=True)
    canonicalized_resource = f"/{bucket}/"
    if object_key:
        canonicalized_resource += object_key
    content_type = "application/json" if is_csv else ""
    if is_csv:
        string_to_sign = f"{method}\n\n{content_type}\n{date_str}\n{canonicalized_resource}"
    else:
        string_to_sign = f"{method}\n\n\n{date_str}\n{canonicalized_resource}"
    signature = base64.b64encode(hmac.new(sk.encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha1).digest()).decode('utf-8')
    headers = {"Date": date_str, "Authorization": f"OBS {ak}:{signature}"}
    if is_csv: headers["Content-Type"] = content_type
    return headers

def main():
    ak, sk, bucket = get_credentials()
    if not ak or not sk:
        print("Credenciais nao encontradas.")
        return
    base_url = f"https://{bucket}.obs.sa-brazil-1.myhuaweicloud.com"

    print("--- 1. Listar raiz do bucket ---")
    resp = _safe_get(requests, f"{base_url}/?delimiter=/", headers=get_obs_auth_header(ak, sk, "GET", bucket))
    if resp.status_code == 200:
        print([e.text for e in ET.fromstring(resp.text).findall(".//{*}Prefix")])
    else:
        print(f"Erro: {resp.status_code}")

    print("\n--- 2. Varredura Voice/ (ultimos 7 dias) ---")
    v3_files = []
    for d in range(7):
        date_str = (datetime.now() - timedelta(days=d)).strftime("%Y%m%d")
        p = f"Voice/{date_str}/"
        resp = _safe_get(requests, f"{base_url}/?prefix={p}&max-keys=1000", headers=get_obs_auth_header(ak, sk, "GET", bucket))
        if resp.status_code == 200:
            keys = [e.text for e in ET.fromstring(resp.text).findall(".//{*}Key") if e.text and e.text.endswith('.V3')]
            v3_files.extend(keys)
    print(f"Total de .V3 encontrados nos ultimos 7 dias: {len(v3_files)}")
    if v3_files: 
        print(f"Amostra do V3 mais antigo: {v3_files[0]}")
        print(f"Amostra do V3 mais novo: {v3_files[-1]}")

    print("\n--- 3 e 4. Varredura CSV (ultimos 3 dias) ---")
    csv_file = None
    for d in range(3):
        date_str = (datetime.now() - timedelta(days=d)).strftime("%Y%m%d")
        p = f"Contact_Record/contact-record/10-minutes/{date_str}/"
        resp = _safe_get(requests, f"{base_url}/?prefix={p}&max-keys=1000", headers=get_obs_auth_header(ak, sk, "GET", bucket))
        if resp.status_code == 200:
            keys = [e.text for e in ET.fromstring(resp.text).findall(".//{*}Key") if e.text and e.text.endswith('.csv')]
            if keys:
                csv_file = sorted(keys)[-1]
                break
    if csv_file:
        print(f"CSV selecionado: {csv_file}")
        resp_csv = _safe_get(requests, f"{base_url}/{csv_file}", headers=get_obs_auth_header(ak, sk, "GET", bucket, csv_file, True))
        if resp_csv.status_code != 200:
            resp_csv = _safe_get(requests, f"{base_url}/{csv_file}", headers=get_obs_auth_header(ak, sk, "GET", bucket, csv_file, False))
        
        if resp_csv.status_code == 200:
            lines = resp_csv.text.splitlines()
            reader = csv.DictReader(lines)
            print(f"Headers: {reader.fieldnames}")
            valids = 0
            for r in reader:
                dur = r.get('callDuration') or r.get('duration') or r.get('calllDuration') or '0'
                if str(dur).isdigit() and int(dur) > 0:
                    if valids < 3: print(f"Row: {r}")
                    valids += 1
            print(f"Rows com duracao > 0 neste CSV: {valids}")
        else:
            print("Failed to download CSV")

    print("\n--- 5. Escolhe um .V3 real e Baixa ---")
    if not v3_files:
        print("Nenhum V3 para baixar.")
        return

    target_v3 = v3_files[-1] # Pega o mais recente
    out_dir = os.path.join("storage", "probe")
    os.makedirs(out_dir, exist_ok=True)
    v3_path = os.path.join(out_dir, "sample.V3")
    
    print(f"Baixando: {target_v3}")
    resp_v3 = _safe_get(requests, f"{base_url}/{target_v3}", headers=get_obs_auth_header(ak, sk, "GET", bucket, target_v3), stream=True)
    if resp_v3.status_code == 200:
        try:
            total_bytes, head = download_stream_to_file(resp_v3, v3_path)
        finally:
            resp_v3.close()
        print(f"Salvo em: {v3_path} ({total_bytes} bytes)")
        
        print("\n--- 6. Primeiros bytes (Hex) ---")
        print("Hex:", " ".join(f"{b:02x}" for b in head))
        try:
            print("ASCII:", head.decode('ascii', errors='replace'))
        except:
            pass

        print("\n--- 7. Conversoes com FFmpeg ---")
        for name, cmd in ffmpeg_commands(v3_path, out_dir):
            print(f"Tentando {name}...")
            try:
                res = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS)
                if res.returncode == 0:
                    print(f"  [OK] -> {name}.wav criado")
                else:
                    err_msg = res.stderr.splitlines()[-1] if res.stderr else ''
                    print(f"  [--] Falhou. Erro: {err_msg}")
            except Exception as e:
                print(f"  [--] Exception: {e}")
    else:
        print(f"Erro ao baixar V3: {resp_v3.status_code}")

if __name__ == '__main__':
    main()
