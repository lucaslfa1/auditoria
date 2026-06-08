import yaml

with open('backend/db/scoring_rules.yaml', encoding='utf-8') as f:
    data = yaml.safe_load(f)

for alert in data['alerts']:
    total = sum(c.get('weight', 0) for c in alert['criteria'])
    if abs(total - 10.0) > 0.01:
        print(f"{alert['id']} total weight is {total:.2f}")
