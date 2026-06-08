import json
from pathlib import Path
from collections import Counter

def analyze_logs():
    log_file = Path("logs/production_raw_logs.json")
    if not log_file.exists():
        print("Arquivo de logs nao encontrado.")
        return

    try:
        data = json.loads(log_file.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"Erro ao ler JSON: {e}")
        return

    ips = Counter()
    paths = Counter()
    errors = []
    logins = []

    for entry in data:
        http_req = entry.get("httpRequest", {})
        remote_ip = http_req.get("remoteIp", "unknown")
        user_agent = http_req.get("userAgent", "unknown")
        path = http_req.get("requestUrl", "").split("?")[0]
        status = str(http_req.get("status", ""))
        method = http_req.get("requestMethod", "")

        if remote_ip != "unknown":
            ips[f"{remote_ip} ({user_agent[:40]})"] += 1
            
            if "/api/auth/login" in path and method == "POST":
                logins.append(f"LOGIN POST de {remote_ip}: {path}")
            
            if status.startswith(("4", "5")):
                errors.append(f"STATUS {status} em {path} (IP: {remote_ip})")

        if entry.get("severity") in ("ERROR", "CRITICAL"):
            errors.append(f"SEVERITY {entry['severity']}: {entry.get('textPayload', '')}")

    print("--- RESUMO DE ACESSOS ---")
    print(f"Total de IPs únicos detectados: {len(ips)}")
    for ip, count in ips.most_common(5):
        print(f"IP: {ip} - Requisições: {count}")
    
    print("\n--- TENTATIVAS DE LOGIN / SESSÕES ---")
    if logins:
        for login in logins[:5]:
            print(login)
    else:
        print("Nenhuma tentativa de login recente detectada nos logs (pode ser sessao ativa).")

    print("\n--- ERROS DETECTADOS (4xx, 5xx ou Exception) ---")
    if errors:
        for err in set(errors[:10]): # Usar set para remover duplicados de probes
            print(err)
    else:
        print("Nenhum erro crítico detectado nos logs recentes.")

if __name__ == "__main__":
    analyze_logs()
