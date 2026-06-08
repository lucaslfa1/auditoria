import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

LOG_FILE = Path("logs/watchdog_report.log")
RAW_LOGS = Path("logs/watchdog_raw.json")

def get_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def run_monitor():
    print(f"[{get_now()}] Iniciando ciclo de monitoramento...")
    
    try:
        # Busca logs dos últimos 5 minutos
        cmd = 'gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=auditoria" --limit 50 --format=json'
        result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, encoding="utf-8")
        
        if result.returncode != 0:
            with open(LOG_FILE, "a") as f:
                f.write(f"[{get_now()}] ERRO ao buscar logs do gcloud: {result.stderr}\n")
            return

        logs = json.loads(result.stdout)
        errors = []
        logins = []
        
        for entry in logs:
            http_req = entry.get("httpRequest", {})
            status = http_req.get("status")
            path = http_req.get("requestUrl", "")
            ip = http_req.get("remoteIp", "unknown")
            method = http_req.get("requestMethod", "")

            if status and int(status) >= 400:
                errors.append(f"HTTP {status} em {path} (IP: {ip})")
            
            if "/api/auth/login" in path and method == "POST":
                logins.append(f"LOGIN detectado de {ip}")

        with open(LOG_FILE, "a") as f:
            f.write(f"--- Ciclo {get_now()} ---\n")
            if errors:
                f.write(f"ALERTAS: {len(errors)} erros detectados.\n")
                for e in set(errors): f.write(f"  > {e}\n")
            else:
                f.write("STATUS: Saudavel (Sem erros 4xx/5xx).\n")
            
            if logins:
                f.write(f"ACESSOS: {len(logins)} tentativas de login.\n")
                for l in set(logins): f.write(f"  > {l}\n")
            f.write("-" * 30 + "\n")

    except Exception as e:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{get_now()}] CRITICAL: Falha no script de monitoramento: {e}\n")

if __name__ == "__main__":
    # Garantir que a pasta logs exista
    Path("logs").mkdir(exist_ok=True)
    
    with open(LOG_FILE, "w") as f:
        f.write(f"=== MONITORAMENTO INICIADO EM {get_now()} ===\n")
        f.write("Modo: Permissivo (Acesso Garantido)\n\n")

    while True:
        run_monitor()
        time.sleep(120) # 2 minutos
