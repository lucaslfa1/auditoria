"""Reprocessa o backlog da esteira de automacao para o modelo de DOIS ESTADOS TERMINAIS.

Aplica a regra "o que presta segue, o que nao presta e descartado" aos itens ja presos.
PRESERVA triagem manual humana — a checagem de origem (automacao vs humano) vem ANTES de tudo:
  - itens SEM sinal de automacao (triagem manual humana) -> NAO mexe, qualquer que seja o alerta.
  - alerta 'desconhecido'/ausente (de automacao) -> DESCARTA PERMANENTE (lixo de classificacao;
    rebaixar so re-classificaria como desconhecido e descartaria de novo).
  - needs_manual_triage/blocked_operator/monthly_capped de automacao -> reativa
    (auto_resolved) para o proximo ciclo auditar ou descartar conforme a regra viva.
  - pending por timeout / "automacao zumbi" -> zera o contador e reativa (auto_resolved).

Idempotente: descarte de item ausente e no-op; reativacao so toca itens presos.

Uso:
  python scripts/reprocess_automation_backlog.py            # dry-run (so relatorio, read-only)
  python scripts/reprocess_automation_backlog.py --apply    # aplica as acoes
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import database  # noqa: E402
from db.domain_constants import (  # noqa: E402
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_PENDING,
)

# Status que podem conter itens presos pela automacao.
SCAN_STATUSES = (
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_PENDING,
)

# Sinais de que um item preso veio da esteira de automacao (e nao de triagem manual humana).
AUTOMATION_MOTIVO_SIGNALS = (
    "transcricao",
    "alerta_sem_criterios",
    "setor_ausente_com_alerta_valido",
    "alerta_desconhecido_ou_invalido",
    "setor_nao_telefonia_automacao",
    "direcao_invalida_automacao",
)
TIMEOUT_MARKERS = ("automation_timeout", "timeout ao auditar")


def _metadata(item: dict) -> dict:
    raw = item.get("metadata") or item.get("metadata_json") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    return raw if isinstance(raw, dict) else {}


def _motivos(item: dict) -> list[str]:
    raw = item.get("motivos") or item.get("motivos_json") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    return [str(m) for m in raw] if isinstance(raw, list) else []


def _alerta(item: dict) -> str:
    return str(item.get("alerta_previsto") or "").strip().lower()


def _is_automation_item(item: dict, motivos: list[str]) -> bool:
    meta = _metadata(item)
    # Origem Huawei/automacao: call_id de ligacao, marca do auto-audit ou pipeline de auditoria.
    if meta.get("huawei_call_id") or meta.get("automation_last_error_at") or meta.get("audit_pipeline"):
        return True
    origem = str(meta.get("origem") or item.get("origem") or "").strip().lower()
    if origem in {"huawei_sync", "huawei", "automacao", "automation"}:
        return True
    return any(
        any(motivo.startswith(sig) or sig in motivo for sig in AUTOMATION_MOTIVO_SIGNALS)
        for motivo in motivos
    )


def _classify(item: dict) -> tuple[str, str]:
    """(acao, motivo) para um item preso. acao in {reactivate, discard_permanent,
    reset_timeout, noop}."""
    status = str(item.get("status") or "").strip().lower()
    alerta = _alerta(item)
    motivos = _motivos(item)
    erro = str(item.get("erro") or "").lower()

    # Triagem MANUAL humana (nao-automacao): NUNCA tocar, independente de alerta/status.
    # A checagem de origem vem ANTES do descarte por alerta ausente.
    if not _is_automation_item(item, motivos):
        return ("noop", "triagem_manual_humana_preservada")

    # Daqui pra baixo o item e de automacao.
    # Lixo de classificacao -> descarte PERMANENTE (consistente com o backend DISCARD_IMPOSSIBLE);
    # rebaixar so re-classificaria como desconhecido e descartaria de novo.
    if not alerta or alerta == "desconhecido":
        return ("discard_permanent", "triagem_sem_alerta_confiavel")

    if status == REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE:
        return ("reactivate", "reprocessar_regra_nova")

    if status in (REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR, REVIEW_QUEUE_STATUS_MONTHLY_CAPPED):
        return ("reactivate", "reprocessar_regra_nova")

    if status == REVIEW_QUEUE_STATUS_PENDING:
        if any(marker in erro for marker in TIMEOUT_MARKERS):
            return ("reset_timeout", "automation_timeout")
        return ("noop", "pending_em_transito")

    return ("noop", "sem_acao")


def _collect() -> list[dict]:
    seen: set[str] = set()
    items: list[dict] = []
    for status in SCAN_STATUSES:
        for item in database.listar_fila_revisao_classificacao(limit=5000, status=status) or []:
            ih = item.get("input_hash")
            if ih and ih in seen:
                continue
            if ih:
                seen.add(ih)
            items.append(item)
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocessa o backlog da esteira de automacao.")
    parser.add_argument("--apply", action="store_true", help="Aplica as acoes (default: dry-run, read-only).")
    parser.add_argument("--dry-run", action="store_true", help="So relatorio, read-only (default).")
    parser.add_argument("--limit-sample", type=int, default=50, help="Quantos itens listar por categoria no dry-run.")
    args = parser.parse_args()
    dry_run = not args.apply

    items = _collect()
    buckets: dict[str, list[dict]] = {
        "reactivate": [],
        "discard_permanent": [],
        "reset_timeout": [],
        "noop": [],
    }
    for item in items:
        acao, motivo = _classify(item)
        buckets.setdefault(acao, []).append({"item": item, "motivo": motivo})

    print("=" * 78)
    print(f"Backlog da esteira de automacao — {'DRY-RUN (read-only)' if dry_run else 'APPLY'}")
    print("=" * 78)
    print(f"  itens coletados: {len(items)}")
    for acao in ("reactivate", "discard_permanent", "reset_timeout", "noop"):
        print(f"  {acao:20s}: {len(buckets.get(acao, []))}")
    print("-" * 78)

    if dry_run:
        for acao in ("reactivate", "discard_permanent", "reset_timeout"):
            for entry in buckets.get(acao, [])[: args.limit_sample]:
                it = entry["item"]
                ih = str(it.get("input_hash") or "?")
                print(
                    f"  [{acao}] hash={ih[:12]} status={it.get('status','?')} "
                    f"alerta={_alerta(it) or '-'} arquivo={it.get('nome_arquivo','?')} motivo={entry['motivo']}"
                )
        print()
        print("Dry-run: nada foi alterado. Rode com --apply para executar.")
        return

    applied = {"reactivate": 0, "discard_permanent": 0, "reset_timeout": 0, "errors": 0}
    for entry in buckets.get("reactivate", []):
        ih = entry["item"].get("input_hash")
        if not ih:
            continue
        try:
            database.atualizar_status_fila_revisao_classificacao(
                ih,
                status=REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
                erro=None,
                metadata_merge={"automation_transient_retries": 0, "backlog_reprocessed": True},
            )
            applied["reactivate"] += 1
        except Exception as exc:  # noqa: BLE001
            applied["errors"] += 1
            print(f"  ERRO reactivate hash={ih}: {exc}")

    for entry in buckets.get("discard_permanent", []):
        it = entry["item"]
        ih = it.get("input_hash")
        if not ih:
            continue
        meta = _metadata(it)
        try:
            database.descartar_item_automacao(
                ih,
                motivo=entry["motivo"],
                tombstone=True,
                log_fields={
                    "nome_arquivo": it.get("nome_arquivo"),
                    "setor_previsto": it.get("setor_previsto"),
                    "operador_previsto": it.get("operador_previsto"),
                    "huawei_call_id": meta.get("huawei_call_id"),
                },
            )
            applied["discard_permanent"] += 1
        except Exception as exc:  # noqa: BLE001
            applied["errors"] += 1
            print(f"  ERRO discard hash={ih}: {exc}")

    for entry in buckets.get("reset_timeout", []):
        ih = entry["item"].get("input_hash")
        if not ih:
            continue
        try:
            database.atualizar_status_fila_revisao_classificacao(
                ih,
                status=REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
                metadata_merge={"automation_transient_retries": 0, "backlog_reprocessed": True},
            )
            applied["reset_timeout"] += 1
        except Exception as exc:  # noqa: BLE001
            applied["errors"] += 1
            print(f"  ERRO reset_timeout hash={ih}: {exc}")

    print("Aplicado:")
    for acao, n in applied.items():
        print(f"  {acao:20s}: {n}")


if __name__ == "__main__":
    main()
