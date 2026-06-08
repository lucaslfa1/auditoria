import sys
import re

path = 'backend/tests/test_huawei_sync.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Fix mock_obs_cls to MagicMock so it doesn't return a coroutine
c = re.sub(r'mock_obs_cls = AsyncMock\(\)', 'mock_obs_cls = MagicMock()', c)

# Add download_chain=MagicMock() to all _processar_candidato calls
c = re.sub(
    r'(should_cancel=None,?\s*)\)',
    r'\1\n                download_chain=AsyncMock(),\n            )',
    c
)

# Remove patch.object(huawei_sync._DOWNLOAD_CHAIN...) and replace with patching the download_chain passed to the function
c = c.replace('with patch.object(huawei_sync._DOWNLOAD_CHAIN, "download", AsyncMock(return_value=download_result)):', 'if True:')

# In the two pretriagem tests, we need to pass a specific download_chain mock
pretriagem_chain = 'download_chain=AsyncMock(download=AsyncMock(return_value=download_result))'
c = c.replace(
    'download_chain=AsyncMock(),',
    pretriagem_chain,
    2 # Apply only to the next 2 occurrences, or we can just replace all with the explicit one
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
