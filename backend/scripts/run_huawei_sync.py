from __future__ import annotations
"""Runner standalone do sync Huawei AICC para execucao por Task Scheduler.

Uso:
    # De dentro de backend/:
    python scripts/run_huawei_sync.py
    python scripts/run_huawei_sync.py --horas 2
    python scripts/run_huawei_sync.py --horas 24 --log-level DEBUG

O script:
1. Carrega `.env` do diretorio backend/ (mesmas variaveis do servidor).
2. Chama `core.huawei_sync.executar_sync_huawei(horas)` de forma assincrona.
3. Imprime o relatorio final em JSON (stdout) e grava log em
   `backend/logs/huawei_sync/<YYYYMMDD_HHMMSS>.log`.
4. Sai com exit code 0 se tudo correu (inclusive stub), 1 em caso de
   excecao nao tratada. Exit code eh usado pelo Task Scheduler para
   decidir se reenvia notificacao de falha.

Pre-requisitos:
- A maquina precisa estar em IP whitelisted pela Teledata (qualquer PC da
  rede NSTECH ou VPN corporativa).
- `.env` deve conter: DATABASE_URL, HUAWEI_AK, HUAWEI_SK, HUAWEI_CC_ID,
  HUAWEI_VDN, HUAWEI_AUTH_MODE (proxy ou direct), ENABLE_HUAWEI_SYNC=true.
- Venv do backend ativado OU usar o wrapper .bat `scripts/huawei_sync.bat`.
"""


import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path


def _setup_logging(log_level: str) -> Path:
    backend_dir = Path(__file__).resolve().parent.parent
    log_dir = backend_dir / "logs" / "huawei_sync"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{stamp}.log"

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    # Limpa handlers pre-existentes para nao duplicar linhas quando rodado
    # sequencialmente (ex: agendador disparando varias vezes no mesmo processo).
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)
    return log_path


def _load_env() -> None:
    """Carrega `.env` de backend/ se python-dotenv estiver disponivel."""
    backend_dir = Path(__file__).resolve().parent.parent
    env_path = backend_dir / ".env"
    try:
        from dotenv import load_dotenv
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except ImportError:
        # python-dotenv nao instalado: assume que a shell ja exportou as vars.
        pass


async def _main(horas: int) -> dict:
    # Import tardio para garantir que .env ja foi carregado antes.
    from core.huawei_sync import executar_sync_huawei  # noqa: E402
    return await executar_sync_huawei(horas_retroativas=horas)


def cli() -> int:
    parser = argparse.ArgumentParser(description="Sync Huawei AICC (standalone)")
    parser.add_argument(
        "--horas",
        type=int,
        default=int(os.getenv("HUAWEI_SYNC_HORAS_RETROATIVAS", "1")),
        help="Janela retroativa de busca em horas (default: 1 ou env)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("HUAWEI_SYNC_LOG_LEVEL", "INFO"),
        help="DEBUG | INFO | WARNING | ERROR",
    )
    args = parser.parse_args()

    _load_env()

    # Garantir que o import resolve modulos de backend/ (igual o uvicorn faz).
    backend_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend_dir))

    log_path = _setup_logging(args.log_level)
    logger = logging.getLogger("huawei_sync.runner")

    logger.info("=== Inicio do sync Huawei | janela=%sh | log=%s ===", args.horas, log_path)

    if (os.getenv("ENABLE_HUAWEI_SYNC", "false") or "").strip().lower() != "true":
        logger.warning(
            "ENABLE_HUAWEI_SYNC != true. O orquestrador vai retornar stub."
            " Ajuste o .env de backend/ para efetivar o sync."
        )

    try:
        resultado = asyncio.run(_main(args.horas))
    except KeyboardInterrupt:
        logger.error("Interrompido pelo usuario.")
        return 130
    except Exception:
        logger.exception("Erro fatal no sync Huawei.")
        return 1

    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    logger.info(
        "=== Fim do sync | status=%s | baixadas=%s | enfileiradas=%s | duplicadas=%s | erros=%s ===",
        resultado.get("status"),
        resultado.get("baixadas"),
        resultado.get("enfileiradas"),
        resultado.get("duplicadas"),
        len(resultado.get("erros") or []),
    )
    return 0


if __name__ == "__main__":
    sys.exit(cli())
