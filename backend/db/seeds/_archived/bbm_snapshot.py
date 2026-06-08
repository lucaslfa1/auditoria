"""Helper para dump/load do snapshot BBM (sector + alertas + criterios).

Usado pela migration `m20260518_004_migrate_bbm_to_distribuicao` e pelo
`restore_bbm.py`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SNAPSHOT_FILENAME = "2026-05-18-bbm-sector.json"


def dump_bbm_snapshot(payload: dict[str, Any], path: Path) -> None:
    """Escreve o snapshot em `path` (UTF-8, indent=2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )


def load_bbm_snapshot(path: Path) -> dict[str, Any]:
    """Le snapshot do `path`. Levanta FileNotFoundError se nao existir."""
    return json.loads(path.read_text(encoding="utf-8"))


def default_snapshot_path() -> Path:
    """Path canonico do snapshot dentro do repo."""
    return Path(__file__).resolve().parent / SNAPSHOT_FILENAME


def build_snapshot_payload(
    sector: dict | None,
    alerts: list[dict],
    criteria: list[dict],
) -> dict[str, Any]:
    """Estrutura o payload com metadados de auditoria."""
    return {
        "snapshot_date": "2026-05-18",
        "reason": "BBM absorvido por Distribuicao. Snapshot para revert eventual.",
        "version_log": "logs/versions/1.3.74-migracao-bbm-distribuicao.md",
        "sector": sector,
        "alerts": list(alerts),
        "criteria": list(criteria),
    }
