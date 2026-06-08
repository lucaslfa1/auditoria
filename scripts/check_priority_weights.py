import json
with open('criterios_pesos_extraidos.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
for sector, alerts in data.items():
    for alert_name, criteria in alerts.items():
        if 'prioritário' in alert_name.lower():
            print(f'Sector: {sector} | Alert: {alert_name}')
            total = 0
            for c in criteria:
                print(f"  - {c['criterio']} -> {c['peso']}")
                total += c['peso']
            print(f'  Total: {total}')
