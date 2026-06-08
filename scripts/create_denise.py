import sys
import os

# Adiciona o diretório backend ao path para importar o database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

import database

def create_denise():
    username = (os.getenv("CREATE_USER_USERNAME") or "Denise").strip()
    password = (os.getenv("CREATE_USER_PASSWORD") or "").strip()
    role = (os.getenv("CREATE_USER_ROLE") or "admin").strip()

    if not password:
        print("Configure CREATE_USER_PASSWORD para criar o usuario.")
        raise SystemExit(1)
    
    print(f"--- Criando usuário: {username} ---")
    success = database.create_user(username, password, role)
    
    if success:
        print(f"Sucesso! Usuário '{username}' criado como '{role}'.")
    else:
        print(f"Erro: O usuário '{username}' já existe ou houve um problema na criação.")

if __name__ == "__main__":
    create_denise()
