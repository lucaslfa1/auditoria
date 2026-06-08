import ast
import sys
import os

source_file = 'backend/core/huawei_sync.py'
candidates_file = 'backend/core/huawei/download_candidates.py'
telemetry_file = 'backend/core/huawei/telemetry.py'

candidates_funcs = {
    '_resolve_call_key',
    '_clean_obs_prefix',
    '_clean_huawei_operator_id',
    '_obs_prefix_candidates',
    '_obs_match_ids',
    '_download_id_candidates',
    '_download_candidate_sort_key',
    '_call_duration_is_known',
    '_slug_filename_part',
    '_make_filename',
}

telemetry_funcs = {
    '_empty_process_delta',
    '_increment_skip_counter',
    '_notify_progress',
    '_is_direction_skip',
}

with open(source_file, 'r', encoding='utf-8') as f:
    source_code = f.read()

tree = ast.parse(source_code)
lines = source_code.split('\n')

funcs_to_extract = {}
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
        if node.name in candidates_funcs or node.name in telemetry_funcs:
            # find end line
            end_line = node.end_lineno
            start_line = node.lineno
            # check decorators
            if node.decorator_list:
                start_line = min(d.lineno for d in node.decorator_list)
            
            funcs_to_extract[node.name] = {
                'start': start_line,
                'end': end_line,
                'name': node.name,
                'code': '\n'.join(lines[start_line-1:end_line])
            }

# Sort by start line descending to safely delete from bottom up
sorted_funcs = sorted(funcs_to_extract.values(), key=lambda x: x['start'], reverse=True)

# Delete from source
new_lines = list(lines)
for f in sorted_funcs:
    del new_lines[f['start']-1:f['end']]

# Add imports to top (after the docstring)
import_idx = 0
for i, line in enumerate(new_lines):
    if line.startswith('import ') or line.startswith('from '):
        import_idx = i
        break

new_lines.insert(import_idx, "from .huawei.download_candidates import " + ", ".join(candidates_funcs))
new_lines.insert(import_idx, "from .huawei.telemetry import " + ", ".join(telemetry_funcs))

with open(source_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

# Prepare candidates file
candidates_code = """from typing import Any, Optional, Dict, List
import re
import unicodedata
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

"""
for name in candidates_funcs:
    if name in funcs_to_extract:
        candidates_code += funcs_to_extract[name]['code'] + "\n\n"

# Prepare telemetry file
telemetry_code = """from typing import Any, Optional, Dict, List, Callable
import logging

logger = logging.getLogger(__name__)

"""
for name in telemetry_funcs:
    if name in funcs_to_extract:
        telemetry_code += funcs_to_extract[name]['code'] + "\n\n"

os.makedirs('backend/core/huawei', exist_ok=True)

with open(candidates_file, 'w', encoding='utf-8') as f:
    f.write(candidates_code)

with open(telemetry_file, 'w', encoding='utf-8') as f:
    f.write(telemetry_code)

with open('backend/core/huawei/__init__.py', 'w', encoding='utf-8') as f:
    f.write('')

with open('backend/core/huawei/protocols.py', 'w', encoding='utf-8') as f:
    f.write('from typing import Protocol, Any\n')

print("Extração concluída!")
