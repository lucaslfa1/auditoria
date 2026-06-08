"""Gera pesos_gestores.json a partir de scoring_rules.yaml.

A escala da planilha dos gestores e 0-10.
- SIM (pass): o criterio recebe um peso positivo proporcional ao seu weight no YAML
- NAO (fail): o criterio recebe um deflator negativo proporcional

A soma dos pesos positivos = 10.0 (escala da planilha).
O deflator = -(peso * fator de penalidade), onde o fator e 1.0 para criterios
de alto peso (>= 1.0) e 0.5 para criterios de baixo peso (< 1.0).
"""

import json
import sys
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from core.gestores_mapping import resolve_alert_export_metadata
from db.scoring_loader import load_scoring_rules


def generate_pesos() -> dict:
    """Generate pesos_gestores.json from scoring_rules.yaml."""
    rules = load_scoring_rules()
    pesos = {}

    for alert in rules.get("alerts", []):
        alert_id = alert["id"]
        criteria = alert.get("criteria", [])

        if not criteria:
            continue

        alert_label, contact_type = resolve_alert_export_metadata(alert_id, alert.get("label", ""))

        total_weight = sum(c["weight"] for c in criteria)
        if total_weight == 0:
            continue

        scale = 10.0 / total_weight

        criterios = []
        for index, criterion in enumerate(criteria, 1):
            raw_weight = criterion["weight"]
            peso_normalizado = round(raw_weight * scale, 6)

            if raw_weight >= 1.0:
                deflator = round(-peso_normalizado, 6)
            else:
                deflator = round(-peso_normalizado * 0.5, 6)

            criterios.append(
                {
                    "num": index,
                    "label": criterion["label"],
                    "peso": peso_normalizado,
                    "deflator": deflator,
                    "weight_original": raw_weight,
                }
            )

        key = f"{alert_label}|{contact_type}"
        pesos[key] = {
            "alert_id": alert_id,
            "sector": alert["sector"],
            "total_weight_yaml": round(total_weight, 2),
            "scale_factor": round(scale, 6),
            "criterios": criterios,
        }

    return pesos


def main():
    pesos = generate_pesos()
    output_path = BACKEND_DIR / "core" / "pesos_gestores.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(pesos, handle, ensure_ascii=False, indent=2)

    print(f"Gerado: {output_path}")
    print(f"  {len(pesos)} combinacoes alerta|contato")
    for key in sorted(pesos.keys()):
        count = len(pesos[key]["criterios"])
        print(f"  {key:50s} -> {count} criterios")


if __name__ == "__main__":
    main()
