import glob
import json
import os
import time

import requests


url = "http://localhost:8080/api/audit"

login_url = "http://localhost:8080/api/auth/login"
session = requests.Session()
username = (os.getenv("BACKEND_TEST_USERNAME") or "").strip()
password = (os.getenv("BACKEND_TEST_PASSWORD") or "").strip()
if not username or not password:
    print("Configure BACKEND_TEST_USERNAME e BACKEND_TEST_PASSWORD antes de rodar o teste manual.")
    raise SystemExit(1)

login_data = {"username": username, "password": password}
response = session.post(login_url, json=login_data)

if response.status_code != 200:
    print(f"Erro no login: {response.status_code} - {response.text}")
    raise SystemExit(1)

audio_path = r"C:\Users\lucas.afonso\projetos\auditoria\LigaÃ§Ãµes\CADASTRO\ANTECEDENTES-agent-11214-5_11_2025_17_13_3-node01-1762373580-26728.wav"

if not os.path.exists(audio_path):
    files = glob.glob(r"C:\Users\lucas.afonso\projetos\auditoria\LigaÃ§Ãµes\**\*.wav", recursive=True)
    if files:
        audio_path = files[0]
        print(f"Usando arquivo de Ã¡udio: {audio_path}")
    else:
        print("Nenhum arquivo de Ã¡udio (.wav) encontrado para o teste.")
        raise SystemExit(1)

alert_config = {
    "id": "4.2.1",
    "label": "CADASTRO",
    "description": "Verificar procedimento de antecedentes",
    "promptText": "VocÃª Ã© um auditor de qualidade. O operador deve se identificar, ser cordial e resolver o problema de antecedentes criminais do motorista.",
    "criteria": [
        {"id": "c1", "text": "Operador se identificou?", "type": "boolean", "weight": 1.0, "deflator": -0.5},
        {"id": "c2", "text": "Tratou o problema de antecedentes?", "type": "boolean", "weight": 2.0, "deflator": -1.0},
    ],
}

data = {
    "alert_json": json.dumps(alert_config),
    "operator_id": "11214",
    "operator_name": "Agente Desconhecido",
    "sector_id": "CADASTRO",
}

print("Enviando audio para a IA configurada... Aguarde...")
start_time = time.time()

with open(audio_path, "rb") as file_handle:
    files = {"file": ("audio.wav", file_handle, "audio/wav")}
    res = session.post(url, data=data, files=files)

end_time = time.time()

if res.status_code == 200:
    result = res.json()
    print("==================================================")
    print("AUDITORIA CONCLUIDA EM " + str(round(end_time - start_time, 1)) + " SEGUNDOS")
    print("==================================================")
    print("NOTA FINAL: " + str(result.get("score")) + " / 100")
    print("RESUMO: " + str(result.get("summary")))
    print("\nCRITERIOS:")
    for criterion in result.get("results", []):
        status = "PASSE" if criterion.get("passed") else "FALHA"
        print("[" + status + "] " + str(criterion.get("criteria")) + " (Motivo: " + str(criterion.get("reasoning")) + ")")
else:
    print("Erro na auditoria: " + str(res.status_code))
    print(res.text)
