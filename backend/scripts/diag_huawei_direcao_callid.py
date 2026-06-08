from __future__ import annotations
"""Diagnostico READ-ONLY: a API de detalhe da Huawei devolve a DIRECAO da chamada?

Objetivo: validar se da para corrigir o vazamento de receptivas em setores de
risco consultando a direcao REAL na Huawei por callId (querybasiccallinfo /
querydetailcallinfo), em vez de inferir pelos telefones (que erra em
transferencias internas).

O script consulta os DOIS endpoints de detalhe por callId, varre a resposta
atras de campos de direcao (isCallIn / callType / callDirection) e imprime o
JSON cru (resumido) para inspecao manual.

Uso (Windows, a partir da raiz do projeto auditoria):
    backend\\.venv\\Scripts\\python -m scripts.diag_huawei_direcao_callid ^
        --call-id 1762523104-538062 ^
        --call-id 1762523458-538100
  (rode com o diretorio de trabalho em backend\\, ou ajuste o -m conforme seu shell)

Para o teste mais util, passe callIds de RECEPTIVAS que foram baixadas
indevidamente em setor de risco (de preferencia incluindo transferidas).

NAO altera nada — somente consulta (GET/POST de leitura). ATENCAO: a resposta
pode conter numeros de telefone (PII); nao compartilhe a saida crua publicamente.
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Carrega o .env (backend/.env e .env da raiz) para popular DATABASE_URL e
# credenciais antes de _load_config tocar o banco/tabela configuracoes.
try:
    from dotenv import load_dotenv

    _here = os.path.dirname(os.path.abspath(__file__))
    for _cand in (
        os.path.join(_here, "..", ".env"),
        os.path.join(_here, "..", "..", ".env"),
    ):
        if os.path.exists(_cand):
            load_dotenv(_cand, override=False)
except Exception:
    pass

from core.huawei_client import HuaweiAICCClient  # noqa: E402
from core.huawei_sync import _load_config  # noqa: E402


# Endpoints de detalhe da chamada por callId (CC-CMS).
_DETAIL_ENDPOINTS = (
    ("querybasiccallinfo", "/rest/cmsapp/v1/openapi/calldata/querybasiccallinfo"),
    ("querydetailcallinfo", "/rest/cmsapp/v1/openapi/calldata/querydetailcallinfo"),
)

# Pistas de chave que indicam direcao da chamada na resposta.
_DIRECTION_KEY_HINTS = ("iscallin", "calltype", "calldirection", "callin", "inout", "direction")


def _scan_direction_fields(obj, path: str = ""):
    """Varre o JSON recursivamente; retorna [(caminho, valor)] de chaves que
    parecem indicar a direcao da chamada (isCallIn/callType/...)."""
    found: list[tuple[str, object]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_norm = str(key).lower().replace("_", "")
            full = f"{path}.{key}" if path else str(key)
            if any(hint in key_norm for hint in _DIRECTION_KEY_HINTS) and not isinstance(value, (dict, list)):
                found.append((full, value))
            found.extend(_scan_direction_fields(value, full))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            found.extend(_scan_direction_fields(item, f"{path}[{idx}]"))
    return found


async def _consultar(client: HuaweiAICCClient, endpoint_path: str, call_id: str):
    """POST autenticado num endpoint de detalhe; retorna (json, erro_str)."""
    url = f"{client.cms_url}{endpoint_path}"
    payload = {"ccId": client.cc_id, "vdn": client.vdn, "callId": call_id}
    resp = await client._post_json(url, payload)
    if resp is None:
        return None, "sem resposta (None)"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
    try:
        return resp.json(), None
    except ValueError:
        return None, f"resposta nao-JSON: {resp.text[:300]}"


async def diagnosticar_callid(client: HuaweiAICCClient, call_id: str) -> None:
    print(f"\n{'=' * 80}\ncallId = {call_id}\n{'=' * 80}")
    for nome, path in _DETAIL_ENDPOINTS:
        print(f"\n--- {nome} ---")
        data, err = await _consultar(client, path, call_id)
        if err:
            print(f"  ERRO: {err}")
            continue
        campos = _scan_direction_fields(data)
        if campos:
            print("  >> Campos de DIRECAO encontrados:")
            for caminho, valor in campos:
                print(f"       {caminho} = {valor!r}")
        else:
            print("  >> NENHUM campo de direcao (isCallIn/callType/...) na resposta.")
        print("  Resposta (JSON, ate 3000 chars):")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnostico read-only: a Huawei devolve a direcao da chamada por callId?",
    )
    parser.add_argument(
        "--call-id",
        action="append",
        required=True,
        help="callId Huawei (pode repetir). Use receptivas que vazaram em setor de risco.",
    )
    args = parser.parse_args()

    cfg = _load_config()
    client = HuaweiAICCClient.from_config(cfg)
    print(
        f"Huawei client: cms_url={client.cms_url} cc_id={client.cc_id} "
        f"vdn={client.vdn} auth_mode={client.auth_mode}"
    )
    print("AVISO: a saida pode conter numeros de telefone (PII). Nao compartilhe crua publicamente.")

    for call_id in args.call_id:
        try:
            await diagnosticar_callid(client, call_id)
        except Exception as exc:  # diagnostico nao deve abortar no meio
            print(f"  EXCECAO no callId {call_id}: {type(exc).__name__}: {exc}")

    print(f"\n{'=' * 80}")
    print("Leitura: se 'isCallIn'/'callType' vier com valor confiavel (inclusive em transferidas),")
    print("o filtro pela Huawei e viavel (Camada 1). Senao, mantemos as frases de atendimento como rede.")
    print(f"{'=' * 80}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
