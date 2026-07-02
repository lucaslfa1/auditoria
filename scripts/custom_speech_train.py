"""Treina e valida um modelo Custom Speech pt-BR no recurso Azure Speech existente.

Contexto: o engine primário de transcrição (`fast`) usa o modelo base pt-BR, que
erra nomes do domínio ("Opentech" → "pintech"). O caminho definitivo é treinar um
modelo Custom Speech com texto do domínio + pronúncias e apontar
AZURE_SPEECH_CUSTOM_MODEL_URI para ele (v1.3.213+ envia `models` na definition —
aceitação do campo validada empiricamente no endpoint em 02/07/2026).

NÃO precisa de serviço Azure novo: usa o MESMO recurso Speech (AZURE_SPEECH_KEY/
AZURE_SPEECH_REGION do backend/.env). eastus suporta treino Custom Speech e
pt-BR suporta dados de texto simples + pronúncia.

Limitação da API: os arquivos de treino precisam estar em uma URL que o serviço
consiga baixar com GET anônimo (ex.: SAS de Azure Blob). A REST API NÃO aceita
upload direto de bytes. Alternativa sem URL: fazer upload manual dos dois
arquivos de backend/config/custom_speech/ no Speech Studio
(https://speech.microsoft.com > Custom speech) e treinar por lá; depois validar o
modelo aqui com --validar-modelo.

Uso:
  # 1) Treino completo (arquivos já publicados em URLs com GET anônimo):
  python scripts/custom_speech_train.py --corpus-url "<SAS/URL>" [--pronuncia-url "<SAS/URL>"]

  # 2) Validar um modelo já treinado (ex.: pelo Speech Studio) no fast transcription:
  python scripts/custom_speech_train.py --validar-modelo "<self URI do modelo>"

CUSTO: o treino com texto é COBRADO por hora de computação nos modelos base
atuais (chargeForAdaptation) — treino de texto termina em minutos, custo pequeno
e pontual. A validação usa 1s de silêncio (custo desprezível).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import struct
import sys
import time
import wave
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / "backend" / ".env"
LOCALE = "pt-BR"
POLL_INTERVAL_SECONDS = 20
POLL_TIMEOUT_SECONDS = 60 * 60


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


def api_base(region: str) -> str:
    return f"https://{region}.api.cognitive.microsoft.com/speechtotext/v3.2"


def request_json(method: str, url: str, key: str, payload: dict | None = None) -> dict:
    response = requests.request(
        method,
        url,
        headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"{method} {url} -> {response.status_code}: {response.text[:500]}")
    return response.json() if response.text else {}


def poll_until_done(self_uri: str, key: str, label: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while True:
        entity = request_json("GET", self_uri, key)
        status = entity.get("status")
        print(f"  [{label}] status={status}")
        if status == "Succeeded":
            return entity
        if status == "Failed":
            raise RuntimeError(f"{label} falhou: {json.dumps(entity.get('properties', {}), ensure_ascii=False)[:500]}")
        if time.time() > deadline:
            raise TimeoutError(f"{label} nao concluiu em {POLL_TIMEOUT_SECONDS // 60} min: {self_uri}")
        time.sleep(POLL_INTERVAL_SECONDS)


def silence_wav_bytes(seconds: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(struct.pack("<h", 0) * 16000 * seconds)
    return buffer.getvalue()


def model_uri_variants(model_self: str) -> list[str]:
    """Gera as formas de URI do modelo aceitas pelas APIs (v3.2 e 2025-10-15)."""
    variants = [model_self]
    match = re.search(r"/models/([0-9a-fA-F-]{36})", model_self)
    if match:
        base = model_self.split("/speechtotext/")[0]
        model_id = match.group(1)
        variants.append(f"{base}/speechtotext/models/{model_id}?api-version=2025-10-15")
        variants.append(f"{base}/speechtotext/v3.2/models/{model_id}")
    seen: set[str] = set()
    return [v for v in variants if not (v in seen or seen.add(v))]


def validate_model_on_fast(model_self: str, key: str, region: str) -> str | None:
    """Confirma no endpoint real qual forma de URI o fast transcription aceita em `models`."""
    url = f"https://{region}.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe?api-version=2025-10-15"
    audio = silence_wav_bytes()
    for candidate in model_uri_variants(model_self):
        definition = {"locales": [LOCALE], "models": {LOCALE: candidate}}
        response = requests.post(
            url,
            headers={"Ocp-Apim-Subscription-Key": key},
            files={
                "audio": ("silence.wav", audio, "audio/wav"),
                "definition": (None, json.dumps(definition), "application/json"),
            },
            timeout=120,
        )
        print(f"  [validacao fast] {response.status_code} para models={candidate}")
        if response.ok:
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus-url", help="URL (GET anonimo/SAS) do corpus_ptbr.txt")
    parser.add_argument("--pronuncia-url", help="URL (GET anonimo/SAS) do pronuncia_ptbr.txt")
    parser.add_argument("--validar-modelo", help="Apenas valida um modelo ja treinado no fast transcription")
    parser.add_argument("--nome", default="auditoria-opentech-ptbr", help="Prefixo de displayName no Speech Studio")
    args = parser.parse_args()

    env = load_env(ENV_PATH)
    key = env.get("AZURE_SPEECH_KEY", "")
    region = env.get("AZURE_SPEECH_REGION", "eastus")
    if not key:
        print("ERRO: AZURE_SPEECH_KEY nao encontrado em backend/.env", file=sys.stderr)
        return 2

    if args.validar_modelo:
        accepted = validate_model_on_fast(args.validar_modelo, key, region)
        if accepted:
            print(f"\nOK: o fast transcription aceitou o modelo.\nDefina no backend/.env:\n  AZURE_SPEECH_CUSTOM_MODEL_URI={accepted}")
            return 0
        print("\nFALHOU: nenhuma forma de URI foi aceita pelo fast transcription.", file=sys.stderr)
        return 1

    if not args.corpus_url:
        parser.error("--corpus-url e obrigatorio (ou use --validar-modelo). Sem URL? Use o Speech Studio: ver docstring.")

    base = api_base(region)

    print("1/4 Criando projeto...")
    project = request_json(
        "POST",
        f"{base}/projects",
        key,
        {"displayName": args.nome, "locale": LOCALE, "description": "Vocabulario de dominio Opentech (auditoria de ligacoes)"},
    )
    project_self = project["self"]
    print(f"  projeto: {project_self}")

    print("2/4 Criando datasets...")
    dataset_selfs: list[dict[str, str]] = []
    datasets_config = [("Language", args.corpus_url, "corpus texto")]
    if args.pronuncia_url:
        datasets_config.append(("Pronunciation", args.pronuncia_url, "pronuncias"))
    for kind, content_url, label in datasets_config:
        dataset = request_json(
            "POST",
            f"{base}/datasets",
            key,
            {
                "kind": kind,
                "contentUrl": content_url,
                "locale": LOCALE,
                "displayName": f"{args.nome}-{kind.lower()}",
                "project": {"self": project_self},
            },
        )
        poll_until_done(dataset["self"], key, f"dataset {label}")
        dataset_selfs.append({"self": dataset["self"]})

    print("3/4 Treinando modelo (texto: minutos; cobranca por hora de computacao)...")
    model = request_json(
        "POST",
        f"{base}/models",
        key,
        {
            "displayName": args.nome,
            "locale": LOCALE,
            "datasets": dataset_selfs,
            "project": {"self": project_self},
        },
    )
    model = poll_until_done(model["self"], key, "modelo")
    model_self = model["self"]
    expiration = (model.get("properties") or {}).get("deprecationDates", {})
    print(f"  modelo treinado: {model_self}")
    if expiration:
        print(f"  atencao aos prazos de expiracao: {json.dumps(expiration)}")

    print("4/4 Validando no fast transcription...")
    accepted = validate_model_on_fast(model_self, key, region)
    if accepted:
        print(f"\nSUCESSO. Defina no backend/.env e reinicie o backend:\n  AZURE_SPEECH_CUSTOM_MODEL_URI={accepted}")
        return 0

    print(
        "\nModelo treinado, mas o fast transcription nao aceitou nenhuma forma de URI em `models`.\n"
        f"Alternativas: usar batch transcription (suporte documentado a custom model) ou\n"
        f"implantar um endpoint (custo de hosting/hora) para o engine `sdk`. Modelo: {model_self}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
