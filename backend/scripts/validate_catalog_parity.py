"""Valida paridade entre o catalogo lido do YAML e o catalogo lido do DB.

Uso:
    python -m scripts.validate_catalog_parity

Sai com codigo 0 se zero diferencas, 1 se houver diferenca. Critico para o switch
DB-first da Fase 1.2 (docs/database/dynamic-config-migration.md): so liberar a
inversao de `load_audit_criteria_catalog` quando este script reportar zero diff.
"""
import os
import sys
from pathlib import Path

# Permite rodar do diretorio backend/ ou da raiz
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
sys.path.insert(0, str(BACKEND))


def _normalize_alerts(alerts: list[dict]) -> list[dict]:
    """Remove campos volateis e ordena pra diff estavel."""
    out = []
    for a in alerts:
        out.append({
            "id": a.get("id"),
            "label": a.get("label"),
            "pop_ref": (a.get("pop_ref") or "") or "",
        })
    return sorted(out, key=lambda x: x["id"] or "")


def _diff_catalog(yaml_cat: dict, db_cat: dict) -> list[str]:
    """Retorna lista de mensagens de diff. Lista vazia = paridade total."""
    diffs: list[str] = []
    yaml_sectors = set(yaml_cat.keys())
    db_sectors = set(db_cat.keys())

    only_yaml = yaml_sectors - db_sectors
    only_db = db_sectors - yaml_sectors
    if only_yaml:
        diffs.append(f"Setores SO no YAML: {sorted(only_yaml)}")
    if only_db:
        diffs.append(f"Setores SO no DB: {sorted(only_db)}")

    for sid in sorted(yaml_sectors & db_sectors):
        ylabel = yaml_cat[sid].get("label")
        dlabel = db_cat[sid].get("label")
        if ylabel != dlabel:
            diffs.append(f"[{sid}] label divergente: yaml='{ylabel}' db='{dlabel}'")

        yalerts = _normalize_alerts(yaml_cat[sid].get("alerts", []))
        dalerts = _normalize_alerts(db_cat[sid].get("alerts", []))

        yids = {a["id"] for a in yalerts}
        dids = {a["id"] for a in dalerts}
        only_yaml_alerts = yids - dids
        only_db_alerts = dids - yids
        if only_yaml_alerts:
            diffs.append(f"[{sid}] alertas SO no YAML: {sorted(only_yaml_alerts)}")
        if only_db_alerts:
            diffs.append(f"[{sid}] alertas SO no DB: {sorted(only_db_alerts)}")

        ymap = {a["id"]: a for a in yalerts}
        dmap = {a["id"]: a for a in dalerts}
        for aid in sorted(yids & dids):
            y = ymap[aid]
            d = dmap[aid]
            if y["label"] != d["label"]:
                diffs.append(f"[{sid}/{aid}] label: yaml='{y['label']}' db='{d['label']}'")
            if y["pop_ref"] != d["pop_ref"]:
                diffs.append(f"[{sid}/{aid}] pop_ref: yaml='{y['pop_ref']}' db='{d['pop_ref']}'")

    return diffs


def main() -> int:
    # Garante leitura YAML em uma chamada e DB em outra (sem cache cruzado)
    from core.classification import _load_catalog_from_yaml, _load_catalog_from_db, load_audit_criteria_catalog

    print("== Validacao de paridade: catalogo YAML vs DB ==")

    try:
        yaml_cat = _load_catalog_from_yaml()
    except Exception as exc:
        print(f"ERRO ao carregar YAML: {exc}")
        return 1

    try:
        db_cat = _load_catalog_from_db()
    except Exception as exc:
        print(f"ERRO ao carregar DB: {exc}")
        return 1

    print(f"  YAML: {len(yaml_cat)} setores, {sum(len(s.get('alerts', [])) for s in yaml_cat.values())} alertas")
    print(f"  DB  : {len(db_cat)} setores, {sum(len(s.get('alerts', [])) for s in db_cat.values())} alertas")

    diffs = _diff_catalog(yaml_cat, db_cat)
    if not diffs:
        print("OK: zero diferencas — switch DB-first liberado.")
        return 0

    print(f"FAIL: {len(diffs)} diferenca(s) encontrada(s):")
    for d in diffs:
        print(f"  - {d}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
