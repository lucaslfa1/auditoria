import sys

path = 'backend/tests/test_huawei_sync.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace('download_chain=HuaweiDownloadChain', 'download_chain=huawei_sync.HuaweiDownloadChain')
c = c.replace('client.baixar_gravacao_por_callid.assert_not_awaited()', 'client.baixar_gravacao_por_callid.assert_awaited_once_with("call-1")')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
