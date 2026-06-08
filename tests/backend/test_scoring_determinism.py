"""
Test scoring determinism and calibration.
Sends the same audio twice and compares scores + details.
"""
import os
import sys
import time
import json
import subprocess
import requests

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
BASE_URL = "http://127.0.0.1:18999"

ALERT = {
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

AUDIO_PATH = os.path.join(
    PROJECT_ROOT, "Ligações", "LOGÍSTICA", "BOAS",
    "ATRASO-MOTORISTA-20251230173926115_Danilo_Alves_Logistica_Voz.wav",
)


def wait_for_server(url, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{url}/docs", timeout=2)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            time.sleep(1)
    return False


def audit_once(session, run_label):
    fname = os.path.basename(AUDIO_PATH)
    print(f"\n{'='*60}")
    print(f"  {run_label}")
    print(f"{'='*60}")

    start_time = time.time()
    with open(AUDIO_PATH, "rb") as f:
        resp = session.post(
            f"{BASE_URL}/api/audit",
            files={"file": (fname, f, "audio/wav")},
            data={"alert_json": json.dumps(ALERT, ensure_ascii=False)},
            timeout=300,
        )
    elapsed = time.time() - start_time

    if resp.status_code != 200:
        print(f"  ERRO: {resp.status_code} - {resp.text[:300]}")
        return None

    data = resp.json()
    score = data.get("score", 0)
    max_score = data.get("maxPossibleScore", 0)
    pct = (score / max_score * 100) if max_score > 0 else 0
    details = data.get("details", [])
    trans = data.get("transcription", [])

    print(f"  Tempo: {elapsed:.1f}s")
    print(f"  Score: {score} / {max_score} ({pct:.1f}%)")
    print(f"  Segmentos: {len(trans)}")
    print(f"  Operador: {data.get('operatorName', '?')}")
    print()

    # Detail breakdown
    print(f"  {'Critério':<70} {'Status':<10} {'Peso':<8} {'Obtido':<8}")
    print(f"  {'-'*70} {'-'*10} {'-'*8} {'-'*8}")

    computed_total = 0.0
    computed_max = 0.0
    for d in details:
        label = d.get("label", "?")[:68]
        st = d.get("status", "?")
        w = d.get("weight", 0)
        obtained = d.get("obtainedScore", 0)
        computed_total += obtained
        if st != "na":
            computed_max += w
        print(f"  {label:<70} {st:<10} {w:<8.2f} {obtained:<8.2f}")
        if d.get("comment"):
            comment_short = d["comment"][:100]
            print(f"    -> {comment_short}")

    print()
    print(f"  Soma calculada: {computed_total:.2f} / {computed_max:.2f}")
    print(f"  Score retornado: {score} / {max_score}")

    # Verify math
    if abs(computed_total - score) > 0.02 or abs(computed_max - max_score) > 0.02:
        print(f"  ALERTA: soma local != score retornado")
    else:
        print(f"  OK - Matematica consistente")

    return {
        "score": score,
        "max_score": max_score,
        "details": [(d.get("criterionId"), d.get("status"), d.get("obtainedScore")) for d in details],
        "num_segments": len(trans),
        "operator": data.get("operatorName"),
    }


def run_test():
    if not os.path.exists(AUDIO_PATH):
        print(f"Audio not found: {AUDIO_PATH}")
        return False

    print("TESTE DE DETERMINISMO E CALIBRAÇÃO DE SCORING")
    print(f"Audio: {os.path.basename(AUDIO_PATH)} ({os.path.getsize(AUDIO_PATH)/1024:.0f} KB)")
    print(f"Critérios: {len(ALERT['criteria'])}, Peso total: {sum(c['weight'] for c in ALERT['criteria']):.2f}")

    # Start server
    print("\nIniciando servidor...")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "18999", "--log-level", "warning"],
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )

    try:
        if not wait_for_server(BASE_URL):
            print("Servidor não iniciou")
            return False

        session = requests.Session()
        login = session.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "admin"})
        assert login.status_code == 200

        # Run 1
        r1 = audit_once(session, "EXECUÇÃO 1")
        # Run 2
        r2 = audit_once(session, "EXECUÇÃO 2")

        if not r1 or not r2:
            print("\nFalha em uma das execuções")
            return False

        # Compare
        print(f"\n{'='*60}")
        print("  COMPARAÇÃO DE DETERMINISMO")
        print(f"{'='*60}")

        score_match = r1["score"] == r2["score"]
        max_match = r1["max_score"] == r2["max_score"]
        details_match = r1["details"] == r2["details"]
        segments_match = r1["num_segments"] == r2["num_segments"]

        print(f"  Score idêntico:     {'SIM' if score_match else 'NÃO'} ({r1['score']} vs {r2['score']})")
        print(f"  Max score idêntico: {'SIM' if max_match else 'NÃO'} ({r1['max_score']} vs {r2['max_score']})")
        print(f"  Detalhes idênticos: {'SIM' if details_match else 'NÃO'}")
        print(f"  Segmentos iguais:   {'SIM' if segments_match else 'NÃO'} ({r1['num_segments']} vs {r2['num_segments']})")

        if not details_match:
            print("\n  Diferenças nos critérios:")
            for i, (d1, d2) in enumerate(zip(r1["details"], r2["details"])):
                if d1 != d2:
                    print(f"    Critério {d1[0]}: run1={d1[1]}({d1[2]}) vs run2={d2[1]}({d2[2]})")

        all_match = score_match and max_match and details_match
        print(f"\n  DETERMINISMO: {'CONFIRMADO' if all_match else 'FALHOU - RESULTADOS DIVERGEM'}")
        return all_match

    finally:
        server_proc.terminate()
        server_proc.wait(timeout=10)


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
