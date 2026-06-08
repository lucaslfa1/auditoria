"""Regenerate criterios_auditoria.md from scoring_rules.yaml."""
import sys
import os
from collections import OrderedDict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.scoring_loader import load_scoring_rules


def main():
    rules = load_scoring_rules()
    alerts = rules["alerts"]

    lines = []
    lines.append("# Criterios de Auditoria")
    lines.append("")
    lines.append("> Documento gerado automaticamente a partir de scoring_rules.yaml.")
    lines.append("> Fonte unica de verdade: backend/db/scoring_rules.yaml")
    lines.append("")
    lines.append("")
    lines.append(f"Total de alertas definidos: {len(alerts)}.")
    lines.append("")

    by_sector = OrderedDict()
    for a in alerts:
        by_sector.setdefault(a["sector"], []).append(a)

    for sector_id, sector_alerts in by_sector.items():
        lines.append("")
        lines.append(f"## Setor: {sector_id}")
        lines.append("")
        for a in sector_alerts:
            lines.append(f"### {a['label']} (`{a['id']}`)")
            lines.append("")
            pop = a.get("pop_ref", "")
            if pop:
                lines.append(f"- Referencia POP: {pop}")
            ctx = a.get("context", "")
            if ctx:
                lines.append(f"- Contexto: {ctx}")
            lines.append("")
            for c in a.get("criteria", []):
                w = c["weight"]
                pct = int(w * 100)
                lines.append(f"  - [{pct}%] {c['label']}")
            lines.append("")

    out_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "rag_training", "criterios_auditoria.md"
    )
    out_path = os.path.abspath(out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {len(alerts)} alerts to {out_path}")


if __name__ == "__main__":
    main()
