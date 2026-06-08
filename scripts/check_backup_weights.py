import yaml

try:
    with open('temp_backup_rules.yaml', encoding='utf-16') as f:
        data = yaml.safe_load(f)

    for alert in data['alerts']:
        total = sum(c.get('weight', 0) for c in alert['criteria'])
        if abs(total - 10.0) > 0.01:
            print(f"{alert['id']} total weight is {total:.2f}")
    print("Done checking temp_backup_rules.yaml")
except Exception as e:
    print(f"Error: {e}")
