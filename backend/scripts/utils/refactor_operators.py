import os, re
func_list = [
    'ensure_colaborador_exists', 'ensure_operador_exists', 'upsert_colaborador',
    'upsert_operador_rh', 'upsert_colaborador_telefonia', 'upsert_operador_telefonia',
    'get_supervisores_e_escalas', 'list_supervisores', 'buscar_colaborador_por_nome',
    'buscar_operador_por_nome', 'buscar_colaborador_por_matricula',
    'buscar_colaborador_por_id_huawei', 'map_db_sector_to_classification_sector',
    'resolve_auditable_colaborador', 'listar_operadores_auditaveis_com_id_huawei',
    'list_colaboradores', 'listar_auditaveis_com_id_huawei', 'list_operadores_rh',
    'create_colaborador', 'create_operador_rh', 'update_colaborador',
    'update_operador_rh', 'delete_colaborador', 'delete_operador_rh',
    'bulk_apply_colaborador_action', 'get_colaboradores_lookup',
    'get_operadores_rh_lookup', 'get_colaboradores_para_prompt',
    'get_operadores_rh_para_prompt'
]

for root, dirs, files in os.walk('backend'):
    if '.venv' in dirs: dirs.remove('.venv')
    if '.pytest_cache' in dirs: dirs.remove('.pytest_cache')
    for file in files:
        if file.endswith('.py') and file not in ['database.py', 'refactor_database.py', 'operators.py']:
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                original = content
                
                # Replace module calls
                for f_name in func_list:
                    content = re.sub(r'\bdatabase\.' + f_name + r'\s*\(', f'operators.{f_name}(database.get_connection, ', content)
                    content = re.sub(r'patch\([\"\']database\.' + f_name + r'[\"\']', f'patch(\"repositories.operators.{f_name}\"', content)
                    content = re.sub(r'patch\.object\(database,\s*[\"\']' + f_name + r'[\"\']', f'patch(\"repositories.operators.{f_name}\"', content)

                # Special handling for "from database import"
                for f_name in func_list:
                    pattern = re.compile(r'^from database import (.*?\b' + f_name + r'\b.*)$', re.MULTILINE)
                    if pattern.search(content):
                        # Not doing complex from database import parsing here, mostly tests use patch or database.XXX
                        pass

                # Add import if needed
                if content != original and 'from repositories import operators' not in content and 'import operators' not in content:
                    if 'import database' in content:
                        content = content.replace('import database', 'import database\nfrom repositories import operators')
                    else:
                        content = 'from repositories import operators\n' + content

                if content != original:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f'Updated {path}')
            except Exception as e:
                print(e)