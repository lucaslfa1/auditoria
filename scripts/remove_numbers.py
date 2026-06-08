import json
import re

file_path = r'd:\auditoria\src\data\auditCriteria.json'

with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

def clean_label(label):
    # Matches patterns like "4.1.1 ", "4.1.10 ", etc. at the start of the string
    return re.sub(r'^\d+(\.\d+)+\s+', '', label)

for sector in data['sectors']:
    for alert in sector['alerts']:
        if 'label' in alert:
            alert['label'] = clean_label(alert['label'])

with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4, ensure_ascii=False)

print("Labels cleaned successfully.")
