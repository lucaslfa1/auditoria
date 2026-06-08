import sys
from typing import Optional

def append_to_file(filepath, content):
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(content)

db_content = '''
def list_pending_dispatch_audits(older_than_hours: Optional[int] = None) -> list[dict]:
    from repositories.audits import list_pending_dispatch_audits as repo_list
    return repo_list(get_connection, older_than_hours)

def upsert_audit_draft(input_hash: str, user_id: str, details_json: str, transcription_json: str) -> None:
    from repositories.audits import upsert_audit_draft as repo_upsert
    return repo_upsert(get_connection, input_hash, user_id, details_json, transcription_json)

def get_audit_draft(input_hash: str, user_id: str) -> Optional[dict]:
    from repositories.audits import get_audit_draft as repo_get
    return repo_get(get_connection, input_hash, user_id)
'''

append_to_file('backend/database.py', db_content)
