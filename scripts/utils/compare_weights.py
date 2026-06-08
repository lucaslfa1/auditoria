
import json
import yaml

def compare():
    with open('criterios_pesos_extraidos.json', 'r', encoding='utf-8') as f:
        excel_data = json.load(f)
    
    with open('backend/db/scoring_rules.yaml', 'r', encoding='utf-8') as f:
        yaml_data = yaml.safe_load(f)
    
    # Check a few categories
    # UTI-PRIORITARIO-MOT in YAML
    yaml_alerts = {a['id']: a for a in yaml_data['alerts']}
    
    if 'UTI-PRIORITARIO-MOT' in yaml_alerts:
        print("--- UTI-PRIORITARIO-MOT (YAML) ---")
        total_w = 0
        for c in yaml_alerts['UTI-PRIORITARIO-MOT']['criteria']:
            print(f"{c['label']}: {c['weight']}")
            total_w += c['weight']
        print(f"Total Weight: {total_w}")
    
    # Try to find matching category in Excel JSON
    # It might be "ALERTAS PRIORIT"
    if "ALERTAS PRIORIT" in excel_data:
        print("\n--- ALERTAS PRIORIT (Excel JSON) ---")
        total_p = 0
        for c in excel_data["ALERTAS PRIORIT"]:
            print(f"{c['pergunta']}: {c['peso']} (Deflator: {c['deflator']})")
            total_p += c['peso']
        print(f"Total Peso: {total_p}")

if __name__ == "__main__":
    compare()
