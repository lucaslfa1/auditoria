from __future__ import annotations
"""Smoke test do fallback OBS direto da Huawei.

Uso:
    # 1. listar .V3 de um agente em uma data
    python scripts/test_obs_fallback.py list --date 20260425 --agent 11214

    # 2. baixar 1 gravacao especifica por callId
    python scripts/test_obs_fallback.py fetch --call-id 1762373580-26728 \\
        --agent 11214 --begin 1762373580000

    # 3. baixar e salvar em arquivo .wav
    python scripts/test_obs_fallback.py fetch --call-id 1762373580-26728 \\
        --agent 11214 --begin 1762373580000 --out storage/probe/sample.wav

Credenciais sao lidas (em ordem):
  1. Env vars HUAWEI_OBS_AK / HUAWEI_OBS_SK / HUAWEI_OBS_BUCKET.
  2. Tabela `configuracoes` (chaves huawei_obs_ak/sk/bucket).
  3. Arquivo local backend/obs_creds.json (formato {AK,SK,BUCKET}).

Rode a partir de `backend/`:
    cd backend
    python scripts/test_obs_fallback.py list --date 20260425 --agent 11214
"""


import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

# Permite rodar a partir de qualquer cwd: garante que `backend/` esteja em sys.path.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from core.huawei_obs_client import HuaweiOBSClient  # noqa: E402

logger = logging.getLogger("test_obs_fallback")


def _load_credentials() -> Tuple[Optional[str], Optional[str], str, Optional[str]]:
    """Retorna (ak, sk, bucket, endpoint)."""
    ak = os.getenv("HUAWEI_OBS_AK")
    sk = os.getenv("HUAWEI_OBS_SK")
    bucket = os.getenv("HUAWEI_OBS_BUCKET", "")
    endpoint = os.getenv("HUAWEI_OBS_ENDPOINT")

    # 2. tabela configuracoes
    if not ak or not sk:
        try:
            import db.database as database  # noqa: WPS433

            ak = ak or str(database.get_config_value("huawei_obs_ak", "") or "").strip() or None
            sk = sk or str(database.get_config_value("huawei_obs_sk", "") or "").strip() or None
            bucket = bucket or str(database.get_config_value("huawei_obs_bucket", "") or "").strip()
            endpoint = endpoint or (
                str(database.get_config_value("huawei_obs_endpoint", "") or "").strip() or None
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Tabela configuracoes indisponivel: %s", exc)

    # 3. arquivo local
    if not ak or not sk:
        creds_path = _BACKEND_DIR / "obs_creds.json"
        if creds_path.exists():
            try:
                data = json.loads(creds_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                logger.error("obs_creds.json invalido: %s", exc)
                data = {}
            ak = ak or data.get("HUAWEI_OBS_AK")
            sk = sk or data.get("HUAWEI_OBS_SK")
            bucket = bucket or data.get("HUAWEI_OBS_BUCKET", "")
            endpoint = endpoint or data.get("HUAWEI_OBS_ENDPOINT")

    return ak, sk, bucket or "obs-nstech-opentech", endpoint


def _build_client() -> HuaweiOBSClient:
    ak, sk, bucket, endpoint = _load_credentials()
    if not ak or not sk:
        print("[ERRO] Credenciais OBS nao encontradas (env, configuracoes ou obs_creds.json).")
        sys.exit(2)
    kwargs = {"ak": ak, "sk": sk, "bucket": bucket}
    if endpoint:
        kwargs["endpoint"] = endpoint
    return HuaweiOBSClient(**kwargs)


async def _cmd_list(args: argparse.Namespace) -> int:
    cli = _build_client()
    keys = await cli.listar_v3_por_agente(args.date, str(args.agent))
    print(f"Total de .V3 em Voice/{args.date}/{args.agent}/: {len(keys)}")
    for key in keys[: args.limit]:
        print(f"  {key}")
    if len(keys) > args.limit:
        print(f"  ... (+{len(keys) - args.limit} ocultos; use --limit)")
    return 0 if keys else 1


async def _cmd_fetch(args: argparse.Namespace) -> int:
    cli = _build_client()
    data = await cli.baixar_voice_por_callid(
        call_id=args.call_id,
        agent_id=str(args.agent),
        begin_time=args.begin,
    )
    if data is None:
        print(f"[MISS] Nao encontrado callId={args.call_id} agent={args.agent}.")
        return 1
    print(f"[HIT] {len(data)} bytes baixados.")
    head = data[:32]
    print("  Header (hex):", " ".join(f"{b:02x}" for b in head))
    if data[:4] == b"RIFF":
        print("  Header reconhecido como RIFF/WAV (pronto para uso direto).")
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        print(f"  Salvo em: {out_path}")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Smoke test do fallback OBS direto.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="Lista os .V3 sob Voice/{date}/{agent}/")
    p_list.add_argument("--date", required=True, help="YYYYMMDD")
    p_list.add_argument("--agent", required=True, help="agentId (ex.: 11214)")
    p_list.add_argument("--limit", type=int, default=20, help="Quantos exibir (default 20)")

    p_fetch = sub.add_parser("fetch", help="Baixa 1 gravacao por callId")
    p_fetch.add_argument("--call-id", required=True, help="callId Huawei (ex.: 1762373580-26728)")
    p_fetch.add_argument("--agent", required=True, help="agentId")
    p_fetch.add_argument("--begin", required=True, help="beginTime em ms ou s ou ISO")
    p_fetch.add_argument("--out", help="Caminho para salvar o WAV (opcional)")

    args = parser.parse_args()
    if args.cmd == "list":
        return asyncio.run(_cmd_list(args))
    if args.cmd == "fetch":
        return asyncio.run(_cmd_fetch(args))
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
