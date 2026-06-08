"""
Integration test: real audio upload -> transcription -> AI audit evaluation.

Requires Azure credentials configured in .env and a running backend.
Run with: python tests/test_integration_audio.py
"""
import os
import sys
import time
import json
import subprocess
import signal
import requests

# Paths
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
BASE_URL = "http://127.0.0.1:18999"

# Alert definitions matching criteria.json
ALERT_ATRASO_MOTORISTA = {
    "id": "atraso-mot",
    "label": "Alerta de Posição em Atraso no Contato com o Motorista",
    "context": "Transferência / Distribuição / Fênix / BBM / UTI / BAS",
    "criteria": [
        {"id": "c1_saudacao", "label": "O operador realizou a saudação?", "weight": 0.075},
        {"id": "c1_nome", "label": "O operador informou o próprio nome?", "weight": 0.075},
        {"id": "c1_setor", "label": "O operador informou o setor?", "weight": 0.075},
        {"id": "c1_empresa", "label": "O operador informou a empresa?", "weight": 0.075},
        {"id": "c2", "label": "O operador confirmou a senha de segurança antes de prosseguir?", "weight": 2.0},
        {"id": "c3", "label": "O operador informou claramente o motivo do contato?", "weight": 1.03},
        {"id": "c4", "label": "O operador confirmou a localização atual do motorista?", "weight": 1.22},
        {"id": "c5", "label": "Passou orientações para forçar posicionamento do rastreador?", "weight": 2.0},
        {"id": "c6", "label": "O operador procurou identificar o motivo da perda de sinal?", "weight": 1.05},
        {"id": "c7", "label": "O operador informou os riscos operacionais e de seguro caso o sinal não restabelecer?", "weight": 1.05},
    ],
}

ALERT_PRIORITARIO_MOTORISTA = {
    "id": "prio-mot",
    "label": "Alerta Prioritário no Contato com o Motorista",
    "context": "Transferência / Distribuição / Fênix / BBM / UTI / BAS",
    "criteria": [
        {"id": "c1_saudacao", "label": "O operador realizou a saudação?", "weight": 0.075},
        {"id": "c1_nome", "label": "O operador informou o próprio nome?", "weight": 0.075},
        {"id": "c1_setor", "label": "O operador informou o setor?", "weight": 0.075},
        {"id": "c1_empresa", "label": "O operador informou a empresa?", "weight": 0.075},
        {"id": "c2", "label": "O operador confirmou a senha de segurança antes de prosseguir?", "weight": 2.0},
        {"id": "c3", "label": "O operador informou claramente o motivo do contato?", "weight": 1.03},
        {"id": "c4", "label": "O operador confirmou a localização e a condição do motorista?", "weight": 1.7},
        {"id": "c5", "label": "O operador identificou o motivo do alerta?", "weight": 1.92},
        {"id": "c6", "label": "O operador solicitou vídeo do veículo nos casos necessários?", "weight": 1.7},
        {"id": "c7", "label": "Realizou a despedida padrão com cordialidade?", "weight": 0.3},
    ],
}

ALERT_PRIORITARIO_CLIENTE = {
    "id": "prio-cli",
    "label": "Alerta Prioritário contato com Cliente",
    "context": "Transferência / Distribuição / Fênix / BBM / UTI / BAS",
    "criteria": [
        {"id": "c1_saudacao", "label": "O operador realizou a saudação?", "weight": 0.075},
        {"id": "c1_nome", "label": "O operador informou o próprio nome?", "weight": 0.075},
        {"id": "c1_setor", "label": "O operador informou o setor?", "weight": 0.075},
        {"id": "c1_empresa", "label": "O operador informou a empresa?", "weight": 0.075},
        {"id": "c2", "label": "Confirmou com quem está falando?", "weight": 0.4},
        {"id": "c3", "label": "O operador informou claramente o motivo do contato?", "weight": 1.2},
        {"id": "c4", "label": "O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?", "weight": 2.0},
        {"id": "c5", "label": "O operador informou as ações adotadas até o momento?", "weight": 1.15},
        {"id": "c6", "label": "O operador informou corretamente o local onde gerou o alerta?", "weight": 1.8},
        {"id": "c7", "label": "O operador confirmou os contatos atuais do condutor?", "weight": 1.8},
        {"id": "c8", "label": "Realizou a despedida padrão com cordialidade?", "weight": 0.3},
    ],
}

# 3 audio samples from different sectors (smallest files)
TEST_AUDIOS = [
    {
        "path": os.path.join(PROJECT_ROOT, "Ligações", "LOGÍSTICA", "BOAS",
                             "ATRASO-MOTORISTA-20251230173926115_Danilo_Alves_Logistica_Voz.wav"),
        "sector": "logistica",
        "alert": ALERT_ATRASO_MOTORISTA,
        "expect_operator": True,
    },
    {
        "path": os.path.join(PROJECT_ROOT, "Ligações", "RAST.-UTI-DIST-BAS", "ZERADAS",
                             "NÃO CONFIRMOU SNEHA-20260107164848396_Ruan_Richeli_da_Silva_Distribuição_Voz.wav"),
        "sector": "rastreamento/zerada",
        "alert": ALERT_PRIORITARIO_MOTORISTA,
        "expect_operator": True,
    },
    {
        "path": os.path.join(PROJECT_ROOT, "Ligações", "LOGÍSTICA", "RUINS",
                             "TEMPERATURA-CLIENTE-20251230105252398_David_João_Cardoso_Logistica_Voz.wav"),
        "sector": "logistica",
        "alert": ALERT_PRIORITARIO_CLIENTE,
        "expect_operator": True,
    },
]


def wait_for_server(url, timeout=15):
    """Wait for server to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{url}/docs", timeout=2)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            time.sleep(1)
    return False


def run_test():
    print("=" * 60)
    print("TESTE DE INTEGRAÇÃO - AUDIO + TRANSCRIÇÃO + AUDITORIA")
    print("=" * 60)

    # Check audio files exist
    for audio in TEST_AUDIOS:
        if not os.path.exists(audio["path"]):
            print(f"  SKIP: {os.path.basename(audio['path'])} não encontrado")
            audio["skip"] = True
        else:
            size_kb = os.path.getsize(audio["path"]) / 1024
            print(f"  OK: {os.path.basename(audio['path'])} ({size_kb:.0f} KB)")
            audio["skip"] = False

    # Start server
    print("\n[1] Iniciando servidor na porta 18999...")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "18999", "--log-level", "warning"],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )

    try:
        if not wait_for_server(BASE_URL):
            print("    FALHA: Servidor não iniciou em 15s")
            return False

        print("    Servidor pronto!")

        # Login
        print("\n[2] Login...")
        session = requests.Session()
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "admin"})
        if login_resp.status_code != 200:
            print(f"    FALHA login: {login_resp.status_code} - {login_resp.text[:200]}")
            return False
        print(f"    OK: {login_resp.json()}")

        # Run audits
        all_passed = True
        for i, audio in enumerate(TEST_AUDIOS):
            if audio.get("skip"):
                continue

            fname = os.path.basename(audio["path"])
            print(f"\n[{i+3}] Auditando: {fname} ({audio['sector']})")
            print(f"    Enviando...")

            start_time = time.time()
            with open(audio["path"], "rb") as f:
                mime = "audio/wav" if fname.endswith(".wav") else "audio/mpeg"
                resp = session.post(
                    f"{BASE_URL}/api/audit",
                    files={"file": (fname, f, mime)},
                    data={"alert_json": json.dumps(audio["alert"], ensure_ascii=False)},
                    timeout=300,
                )
            elapsed = time.time() - start_time

            if resp.status_code != 200:
                print(f"    FALHA: {resp.status_code} - {resp.text[:300]}")
                all_passed = False
                continue

            data = resp.json()
            trans = data.get("transcription", [])
            details = data.get("details", [])
            operator = data.get("operatorName", "?")
            score = data.get("score", "?")

            print(f"    Tempo: {elapsed:.1f}s")
            print(f"    Operador: {operator}")
            print(f"    Score: {score}")
            print(f"    Segmentos transcrição: {len(trans)}")
            if trans:
                print(f"    Primeiro: {trans[0].get('text', '')[:100]}")
            print(f"    Critérios avaliados: {len(details)}")
            for d in details[:3]:
                print(f"      - {d.get('criterion', '?')[:55]}: {d.get('status', '?')}")
            if len(details) > 3:
                print(f"      ... e mais {len(details) - 3} critérios")

            # Validations
            if len(trans) == 0:
                print(f"    ⚠ AVISO: Transcrição vazia!")
                all_passed = False
            if audio["expect_operator"] and (not operator or operator.lower() in ["none", "null", "desconhecido", ""]):
                print(f"    ⚠ AVISO: Operador não detectado")
            if len(details) == 0:
                print(f"    ⚠ AVISO: Nenhum critério avaliado!")
                all_passed = False

        print("\n" + "=" * 60)
        if all_passed:
            print("RESULTADO: TODOS OS TESTES PASSARAM")
        else:
            print("RESULTADO: ALGUNS TESTES FALHARAM (ver avisos acima)")
        print("=" * 60)
        return all_passed

    finally:
        # Cleanup server
        if sys.platform == "win32":
            server_proc.terminate()
        else:
            server_proc.send_signal(signal.SIGTERM)
        server_proc.wait(timeout=10)


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
