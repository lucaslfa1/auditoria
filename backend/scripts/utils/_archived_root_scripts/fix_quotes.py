import os
import re

def fix_quotes(filepath):
    content = None
    encodings = ['utf-8', 'utf-16', 'latin-1']
    used_encoding = None
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                content = f.read()
            used_encoding = enc
            break
        except UnicodeDecodeError:
            continue
            
    if content is None:
        return

    original = content
    content = re.sub(r'patch\(\'([^\'"]+)"', r'patch("\1"', content)
    content = re.sub(r'patch\("([^\'"]+)\'', r"patch('\1'", content)

    if content != original:
        with open(filepath, 'w', encoding=used_encoding) as f:
            f.write(content)
        print(f"Fixed quotes in {filepath}")

for root, _, files in os.walk('backend'):
    if '.venv' in root or '__pycache__' in root or '.pytest_cache' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            fix_quotes(os.path.join(root, file))
