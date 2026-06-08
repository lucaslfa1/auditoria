import os
import sys
import json
import base64
import hmac
import hashlib
import requests
from datetime import datetime, timedelta
from email.utils import formatdate
import xml.etree.ElementTree as ET
import csv

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
    
    headers = {
        "Date": date_str,
        "Authorization": f"OBS {ak}:{signature}"
    }
    if is_csv:
        headers["Content-Type"] = content_type
        
    return headers

def probe_advanced():
    ak, sk, bucket = get_credentials()
    endpoint = "obs.sa-brazil-1.myhuaweicloud.com"
    base_url = f"https://{bucket}.{endpoint}"
    
    hoje = datetime.now().strftime("%Y%m%d")
    ontem = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    print(f"--- 1. Listar prefixes raiz do bucket ---")
    headers = get_obs_auth_header(ak, sk, "GET", bucket)
    resp = requests.get(f"{base_url}/?delimiter=/", headers=headers)
    if resp.status_code == 200:
        root = ET.fromstring(resp.text)
        prefixes = [elem.text for elem in root.findall(".//{*}Prefix")]
        print(f"Pastas na raiz: {prefixes}")
    else:
        print(f"Erro raiz: HTTP {resp.status_code} - {resp.text}")

    print("\n--- 2. Explorando subpastas (Voice, ccfs, Contact_Record) ---")
    for p in [f"Voice/{hoje}/", f"Voice/{ontem}/", f"ccfs/", f"Contact_Record/contact-record/10-minutes/{hoje}/"]:
        print(f"\n-> Prefix: {p}")
        headers = get_obs_auth_header(ak, sk, "GET", bucket)
        resp = requests.get(f"{base_url}/?prefix={p}&max-keys=5", headers=headers)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            keys = [elem.text for elem in root.findall(".//{*}Key")]
            for k in keys:
                print(f"   {k}")
        else:
            print(f"   Erro: HTTP {resp.status_code}")

    print("\n--- 3. Baixar manifest CSV mais recente (Buscando em dias recentes) ---")
    # Busca um CSV valido dos ultimos dias para podermos ver o formato real
    csv_linhas = []
    latest_csv = None
    
    for dias in range(15):
        data_busca = (datetime.now() - timedelta(days=dias)).strftime("%Y%m%d")
        prefix_csv = f"Contact_Record/contact-record/10-minutes/{data_busca}/"
        headers = get_obs_auth_header(ak, sk, "GET", bucket)
        resp = requests.get(f"{base_url}/?prefix={prefix_csv}&max-keys=100", headers=headers)
        
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            keys = [elem.text for elem in root.findall(".//{*}Key") if elem.text and elem.text.endswith('.csv')]
            if keys:
                latest_csv = sorted(keys)[-1]
                print(f"-> Encontrado CSV em {data_busca}: {latest_csv}")
                
                headers_csv = get_obs_auth_header(ak, sk, "GET", bucket, latest_csv, is_csv=True)
                resp_csv = requests.get(f"{base_url}/{latest_csv}", headers=headers_csv)
                
                if resp_csv.status_code == 200:
                    csv_linhas = resp_csv.text.splitlines()
                    break
                else:
                    # Fallback pra tentar sem content type se falhou
                    headers_csv2 = get_obs_auth_header(ak, sk, "GET", bucket, latest_csv, is_csv=False)
                    resp_csv2 = requests.get(f"{base_url}/{latest_csv}", headers=headers_csv2)
                    if resp_csv2.status_code == 200:
                        csv_linhas = resp_csv2.text.splitlines()
                        break
        
    if csv_linhas:
        print("\n--- 4. Cabeçalho e Linhas do CSV (Com duração > 0) ---")
        reader = csv.DictReader(csv_linhas)
        print(f"Cabeçalhos: {reader.fieldnames}")
        
        found_valid = 0
        valid_records = []
        for row in reader:
            dur = row.get('calllDuration') or row.get('callDuration') or row.get('duration') or '0'
            try:
                if int(dur) > 0:
                    valid_records.append(row)
                    if found_valid < 5:
                        print(f"  Valid Row: {row}")
                    found_valid += 1
            except:
                pass
        print(f"Total de linhas com duração > 0 neste CSV: {found_valid}")
        
        print("\n--- 5. Tentativa de localizar .V3 por callId/recordId (No dia do CSV) ---")
        if valid_records:
            for row in valid_records[:3]:
                call_id = row.get('callId', '')
                record_id = row.get('recordId', '')
                agent_id = row.get('agentId') or row.get('workNo') or ''
                # Extraindo a data do CSV para procurar na pasta Voice correspondente
                data_csv = latest_csv.split('/')[-2] if latest_csv else hoje
                
                print(f"Procurando áudio (Voice/{data_csv}) para CallID: {call_id} | RecordID: {record_id} | AgentID: {agent_id}")
                
                search_prefix = f"Voice/{data_csv}/"
                headers_search = get_obs_auth_header(ak, sk, "GET", bucket)
                resp_search = requests.get(f"{base_url}/?prefix={search_prefix}&max-keys=1000", headers=headers_search)
                
                if resp_search.status_code == 200:
                    root_s = ET.fromstring(resp_search.text)
                    all_keys = [elem.text for elem in root_s.findall(".//{*}Key")]
                    matched = [k for k in all_keys if (record_id and record_id in k) or (call_id and call_id in k)]
                    if matched:
                        print(f"   [SUCESSO] Áudio encontrado: {matched[0]}")
                    else:
                        print(f"   [FALHA] Nenhum arquivo encontrado contendo {record_id} ou {call_id} em {search_prefix}")
                else:
                    print("   Erro ao listar Voice/")
    else:
        print("Falha ao baixar ou encontrar qualquer CSV válido.")

if __name__ == '__main__':
    probe_advanced()