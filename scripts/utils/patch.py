import os

file_path = os.path.abspath('backend/routers/supervisor.py')
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.read().splitlines()

for i, line in enumerate(lines):
    if 'audit["score"] / audit["max_score"] * 100' in line:
        lines[i] = '        (float(audit.get("score") or 0.0) / float(audit.get("max_score") or 1.0)) * 100'
    elif 'if audit.get("max_score", 0) > 0' in line:
        lines[i] = '        if audit.get("max_score") is not None and float(audit.get("max_score") or 0.0) > 0'

with open(file_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')

print("Patched successfully")
