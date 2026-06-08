import sys
path = 'backend/core/huawei_sync.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace(
    'result = await _DOWNLOAD_CHAIN.download(call_context, client, obs_client)',
    'result = await download_chain.download(call_context, client, obs_client)'
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
