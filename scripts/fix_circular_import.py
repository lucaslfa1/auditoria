import os

with open('backend/core/huawei_sync.py', encoding='utf-8') as f:
    lines = f.read().split('\n')

idx = next(i for i, l in enumerate(lines) if 'def _normalize_identity_text' in l)
code = '\n'.join(lines[idx:idx+7])
del lines[idx:idx+7]

# add import
lines.insert(2, 'from .huawei.download_candidates import _normalize_identity_text')

with open('backend/core/huawei_sync.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

with open('backend/core/huawei/download_candidates.py', encoding='utf-8') as f:
    dc_lines = f.read().split('\n')

# remove bad import
dc_lines = [l for l in dc_lines if 'from core.huawei_sync import _normalize_identity_text' not in l]

with open('backend/core/huawei/download_candidates.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(dc_lines) + '\n' + code + '\n')
