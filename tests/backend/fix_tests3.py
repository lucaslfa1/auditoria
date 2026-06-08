import sys
import re

path = 'backend/tests/test_huawei_sync.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Make sure HuaweiDownloadChain is imported
if 'from core.huawei_download_chain import HuaweiDownloadChain' not in c:
    c = c.replace('from core.huawei_sync import', 'from core.huawei_download_chain import HuaweiDownloadChain\nfrom core.huawei_sync import')

# Replace the mocked download chain with the real one
c = re.sub(
    r'download_chain=AsyncMock\(.*?\)',
    r'download_chain=HuaweiDownloadChain(mode="manual_interval")',
    c
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
