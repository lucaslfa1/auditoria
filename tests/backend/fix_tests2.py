import sys
import re

path = 'backend/tests/test_huawei_sync.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Add MagicMock to unittest.mock imports
c = re.sub(r'from unittest\.mock import (.*)AsyncMock(.*)', r'from unittest.mock import \1AsyncMock, MagicMock\2', c)

# Instead of MagicMock everywhere, just use the correct mock.
c = c.replace(
    'download_chain=AsyncMock(download=AsyncMock(return_value=download_result))',
    'download_chain=AsyncMock(download=AsyncMock(return_value=DownloadResult(audio_bytes=b"RIFFdata", method_used="obs_primary", methods_tried=["obs_primary"], attempts_per_method={"obs_primary": 1})))'
)

c = c.replace(
    'download_chain=AsyncMock(),',
    'download_chain=AsyncMock(download=AsyncMock(return_value=DownloadResult(audio_bytes=b"RIFFdata", method_used="obs_primary", methods_tried=["obs_primary"], attempts_per_method={"obs_primary": 1}))),'
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
