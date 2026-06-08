
import yaml

def check_yaml_weights():
    with open('backend/db/scoring_rules.yaml', 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    for alert in data['alerts']:
        total = sum(c['weight'] for c in alert['criteria'])
        id_items = [c for c in alert['criteria'] if 'Saudação' in c['label'] or 'Nome?' in c['label'] or 'Setor/Empresa' in c['label']]
        print(f"Alert: {alert['id']}")
        print(f"  Total Weight: {total}")
        print(f"  ID criteria count: {len(id_items)}")
        if id_items:
             print(f"  ID criteria sum: {sum(c['weight'] for c in id_items)}")

if __name__ == "__main__":
    check_yaml_weights()
