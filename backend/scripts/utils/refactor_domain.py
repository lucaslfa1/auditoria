import os, re
import sys

domain = "configuration"
func_list = ['get_config_value', 'update_config', 'get_all_configs']

for root, dirs, files in os.walk('backend'):
    if '.venv' in dirs: dirs.remove('.venv')
    if '.pytest_cache' in dirs: dirs.remove('.pytest_cache')
    for file in files:
        if file.endswith('.py') and file not in ['database.py', 'refactor_database.py', 'database_old.py']:
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                original = content
                
                # Code replacements
                for f_name in func_list:
                    # Replace direct calls
                    content = re.sub(r'\bdatabase\.' + f_name + r'\s*\(', f'{domain}.{f_name}(database.get_connection, ', content)
                    
                    # Replace patch string mocks
                    content = re.sub(r'patch\([\"\']database\.' + f_name + r'[\"\']', f'patch(\"repositories.{domain}.{f_name}\"', content)
                    
                    # Replace patch.object mocks
                    content = re.sub(r'patch\.object\(\s*database,\s*[\"\']' + f_name + r'[\"\']', f'patch.object({domain}, \"{f_name}\"', content)
                    content = re.sub(r'patch\.object\(\s*main\.database,\s*[\"\']' + f_name + r'[\"\']', f'patch.object(main.{domain}, \"{f_name}\"', content)

                if content != original:
                    # Make sure import exists
                    if f'from repositories import {domain}' not in content and f'import {domain}' not in content:
                        if 'import database' in content:
                            content = content.replace('import database', f'import database\nfrom repositories import {domain}')
                        else:
                            content = f'from repositories import {domain}\n' + content
                            
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f'Updated {path}')
            except Exception as e:
                print(f"Error in {path}: {e}")
