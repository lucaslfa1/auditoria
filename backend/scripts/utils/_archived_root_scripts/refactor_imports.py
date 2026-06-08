import os
import re

MAPPINGS = {
    'automation': 'core.automation',
    'automation_engine': 'core.automation_engine',
    'classification': 'core.classification',
    'audit_evaluator': 'core.audit_evaluator',
    'transcription_orchestrator': 'core.transcription_orchestrator',
    'quality_analyzer': 'core.quality_analyzer',
    'sentiment': 'core.sentiment',
    'database': 'db.database',
    'speaker_detection': 'audio.speaker_detection',
    'text_processing': 'utils.text_processing',
    'network_utils': 'utils.network_utils',
    'audit_storage': 'storage.audit_storage',
    'speech_sdk_transcriber': 'transcription_providers.speech_sdk_transcriber',
    'generate_word_report': 'scripts.generate_word_report',
    'scheduler': 'jobs.scheduler',
}

def refactor_file(filepath):
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

    for old_module, new_module in MAPPINGS.items():
        # Handle `from module import ...` (allowing leading spaces)
        content = re.sub(rf'^(\s*)from {old_module}\b', rf'\1from {new_module}', content, flags=re.MULTILINE)
        
        # Handle `import module` (allowing leading spaces)
        content = re.sub(rf'^(\s*)import {old_module}\b', rf'\1import {new_module} as {old_module}', content, flags=re.MULTILINE)

        # Handle patch('module.something') in tests
        content = re.sub(rf'patch\([\'"]{old_module}\.', f'patch(\'{new_module}.', content)
        content = re.sub(rf'patch\.object\({old_module},', f'patch.object({old_module},', content)
        
        # Fix dynamic patch string building e.g. patch(f"{old_module}...")
        content = re.sub(rf'patch\([f]?[\'"]{old_module}\.', f'patch(\'{new_module}.', content)

    if content != original:
        with open(filepath, 'w', encoding=used_encoding) as f:
            f.write(content)
        print(f"Updated {filepath}")

for root, _, files in os.walk('backend'):
    if '.venv' in root or '__pycache__' in root or '.pytest_cache' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            refactor_file(os.path.join(root, file))
