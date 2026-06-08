import os, ast
import re
import glob

mapping = {}
repos_dir = 'repositories'
for file in os.listdir(repos_dir):
    if file.endswith('.py') and file != '__init__.py':
        with open(os.path.join(repos_dir, file), 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
            mod_name = file[:-3]
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    mapping[node.name] = mod_name

test_files = glob.glob('tests/test_*.py')
changed_count = 0

for filepath in test_files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    
    # 1. string patch: patch('module.database.func') -> patch('repositories.target.func')
    # Or patch('db.database.func') -> patch('repositories.target.func') if moved
    def string_patch_replacer(match):
        func_name = match.group(1)
        if func_name in mapping:
            return f"patch('repositories.{mapping[func_name]}.{func_name}'"
        return match.group(0)

    # regex to match patch("...database.FUNC"
    # Matches patch("db.database.func", patch("routers.abc.database.func"
    content = re.sub(r'patch\([\"\'](?:[a-zA-Z0-9_\.]*\.)?database\.([a-zA-Z0-9_]+)', string_patch_replacer, content)

    # 2. object patch: patch.object(module.database, "func") -> patch("repositories.target.func")
    # This might require changing @patch.object to @patch, or with patch.object to with patch.
    # It's easier to just replace `module.database` with `repositories.target` if we import repositories.target,
    # but we don't know if it's imported.
    # So `patch.object(main.database, "func")` can become `patch("repositories.target.func")` ONLY IF it's in a `with` statement.
    # If it's a decorator, `@patch.object(...)` -> `@patch("...")`.
    def obj_patch_decorator_replacer(match):
        func_name = match.group(1)
        if func_name in mapping:
            return f'@patch("repositories.{mapping[func_name]}.{func_name}")'
        return match.group(0)
    
    # match @patch.object(module.database, "func")
    content = re.sub(r'@patch\.object\([a-zA-Z0-9_\.]*\.?database,\s*[\"\']([a-zA-Z0-9_]+)[\"\']\)', obj_patch_decorator_replacer, content)

    def obj_patch_with_replacer(match):
        func_name = match.group(1)
        if func_name in mapping:
            return f'patch("repositories.{mapping[func_name]}.{func_name}")'
        return match.group(0)

    # match patch.object(module.database, "func") not preceded by @
    content = re.sub(r'(?<!@)patch\.object\([a-zA-Z0-9_\.]*\.?database,\s*[\"\']([a-zA-Z0-9_]+)[\"\']\)', obj_patch_with_replacer, content)

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        changed_count += 1
        print(f"Updated {filepath}")

print(f"Total files updated: {changed_count}")
