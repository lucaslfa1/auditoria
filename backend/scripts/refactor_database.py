import os
import re

func_to_module = {
    # auth_users
    'get_user_by_username': 'auth_users',
    'create_user': 'auth_users',
    'list_users': 'auth_users',
    'delete_user': 'auth_users',
    'update_user_password': 'auth_users',
    'update_user': 'auth_users',

    # operators
    'ensure_colaborador_exists': 'operators',
    'ensure_operador_exists': 'operators',
    'upsert_colaborador': 'operators',
    'upsert_operador_rh': 'operators',
    'upsert_colaborador_telefonia': 'operators',
    'upsert_operador_telefonia': 'operators',
    'get_supervisores_e_escalas': 'operators',
    'list_supervisores': 'operators',
    'buscar_colaborador_por_nome': 'operators',
    'buscar_operador_por_nome': 'operators',
    'buscar_colaborador_por_matricula': 'operators',
    'buscar_colaborador_por_id_huawei': 'operators',
    'map_db_sector_to_classification_sector': 'operators',
    'resolve_auditable_colaborador': 'operators',
    'listar_operadores_auditaveis_com_id_huawei': 'operators',
    'list_colaboradores': 'operators',
    'listar_auditaveis_com_id_huawei': 'operators',
    'list_operadores_rh': 'operators',
    'create_colaborador': 'operators',
    'create_operador_rh': 'operators',
    'update_colaborador': 'operators',
    'update_operador_rh': 'operators',
    'delete_colaborador': 'operators',
    'delete_operador_rh': 'operators',
    'bulk_apply_colaborador_action': 'operators',
    'get_colaboradores_lookup': 'operators',
    'get_operadores_rh_lookup': 'operators',
    'get_colaboradores_para_prompt': 'operators',
    'get_operadores_rh_para_prompt': 'operators',

    # classification_review
    'upsert_ligacao_auditada': 'classification_review',
    'get_ligacao_auditada_por_hash': 'classification_review',
    'registrar_resultado_classificacao': 'classification_review',
    'sincronizar_fila_revisao_classificacao': 'classification_review',
    'limpar_fila_revisao_classificacao_antiga': 'classification_review',
    'listar_fila_revisao_classificacao': 'classification_review',
    'obter_fila_revisao_classificacao_por_hash': 'classification_review',
    'obter_fila_revisao_classificacao_por_auditoria': 'classification_review',
    'listar_paths_audio_classificado_fila_revisao': 'classification_review',
    'atualizar_status_fila_revisao_classificacao': 'classification_review',
    'corrigir_classificacao_fila_revisao': 'classification_review',
    'registrar_resultado_auditoria': 'classification_review',
    'get_resumo_ligacoes_auditadas': 'classification_review',
    'listar_ligacoes_auditadas': 'classification_review',

    # audits
    'save_audit': 'audits',
    'queue_audit_for_supervisor_review': 'audits',
    'get_audit_media_record': 'audits',
    'update_audit_result': 'audits',
    'update_audit_by_id': 'audits',
    'get_audit_by_hash': 'audits',
    'get_audit_by_id': 'audits',
    'update_audit_status': 'audits',
    'discard_audit': 'audits',
    'restore_audit': 'audits',
    'get_audits_for_export': 'audits',
    'finalize_contestation_review': 'audits',
    'list_pending_dispatch_audits': 'audits',
    'upsert_audit_draft': 'audits',
    'get_audit_draft': 'audits',

    # analytics
    'get_stats': 'analytics',
    'get_history': 'analytics',
    'get_sectors': 'analytics',
    'get_analytics': 'analytics',
    'get_technical_incidents': 'analytics',

    # supervisor_feedback
    'save_gestor_feedback': 'supervisor_feedback',
    'get_gestor_feedback': 'supervisor_feedback',

    # report_exports
    'save_report_export': 'report_exports',
    'list_report_exports': 'report_exports',

    # configuration
    'get_all_configs': 'configuration',
    'update_config': 'configuration',
    'get_config_value': 'configuration',

    # telefonia
    'save_telefonia_sync_history': 'telefonia',
    'list_telefonia_sync_history': 'telefonia',

    # saved_files
    'save_arquivo': 'saved_files',
    'list_arquivos_salvos': 'saved_files',
    'get_arquivo_salvo': 'saved_files',
    'update_arquivo_salvo': 'saved_files',
    'delete_arquivo_salvo': 'saved_files',
    'count_arquivos_salvos': 'saved_files',
    'get_arquivo_by_audit_id': 'saved_files',
    'update_arquivo_by_audit_id': 'saved_files'
}

def process_file(filepath):
    if not filepath.endswith('.py') or os.path.basename(filepath) in ('database.py', 'refactor_database.py'):
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        original_content = f.read()

    new_content = original_content
    imports_to_add = set()
    modified = False

    for func, mod in func_to_module.items():
        pattern = r'database\.' + func + r'\s*\('
        if re.search(pattern, new_content):
            imports_to_add.add(mod)
            modified = True
            new_content = re.sub(pattern, f'{mod}.{func}(database.get_connection, ', new_content)
        
        ref_pattern = r'(?<!def )\bdatabase\.' + func + r'\b(?!\s*\()'
        if re.search(ref_pattern, new_content):
            imports_to_add.add(mod)
            modified = True
            new_content = re.sub(ref_pattern, f'(lambda *args, **kwargs: {mod}.{func}(database.get_connection, *args, **kwargs))', new_content)

    import_pattern = re.compile(r'^from database import (.+)$', re.MULTILINE)
    def repl_import(match):
        nonlocal modified
        imports_str = match.group(1)
        parts = [p.strip() for p in imports_str.split(',')]
        new_db_imports = []
        repo_imports = {}
        for p in parts:
            p_clean = p.split(' as ')[0].strip()
            if p_clean in func_to_module:
                mod = func_to_module[p_clean]
                if mod not in repo_imports:
                    repo_imports[mod] = []
                repo_imports[mod].append(p)
                modified = True
            else:
                new_db_imports.append(p)
        res = []
        if new_db_imports:
            res.append(f'from database import {", ".join(new_db_imports)}')
        else:
            res.append('from database import get_connection')
        for mod, funcs in repo_imports.items():
            res.append(f'from repositories.{mod} import {", ".join(funcs)}')
        return '\n'.join(res)

    if re.search(import_pattern, new_content):
        new_content = import_pattern.sub(repl_import, new_content)
        for func in func_to_module:
            call_pattern = r'(?<!def )(?<!\.)\b' + func + r'\s*\('
            if re.search(call_pattern, new_content):
                modified = True
                new_content = re.sub(call_pattern, f'{func}(get_connection, ', new_content)

    if imports_to_add:
        mods_str = ", ".join(sorted(list(imports_to_add)))
        import_stmt = f'from repositories import {mods_str}'
        lines = new_content.split('\n')
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                insert_idx = i
        lines.insert(insert_idx + 1, import_stmt)
        new_content = '\n'.join(lines)

    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Modified {filepath}")

# Limit to strictly backend files and skip .venv
root_dir = r'C:\Users\lucas.afonso\projetos\auditoria\backend'
for root, dirs, files in os.walk(root_dir):
    if '.venv' in dirs: dirs.remove('.venv')
    if '.pytest_cache' in dirs: dirs.remove('.pytest_cache')
    if '__pycache__' in dirs: dirs.remove('__pycache__')

    for file in files:
        if file.endswith('.py'):
            process_file(os.path.join(root, file))

print("Done refactoring backend files.")
