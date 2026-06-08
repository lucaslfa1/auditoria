import sys

path = 'backend/tests/test_huawei_sync.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace('download_chain=HuaweiDownloadChain(mode="manual_interval")))', 'download_chain=HuaweiDownloadChain(mode="manual_interval")')
c = c.replace('download_chain=HuaweiDownloadChain(mode="manual_interval"))', 'download_chain=HuaweiDownloadChain(mode="manual_interval")')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
