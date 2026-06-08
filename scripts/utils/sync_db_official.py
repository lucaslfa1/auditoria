import os
import random
import string
import pandas as pd
import psycopg2
from urllib.parse import urlparse
import datetime
from dotenv import load_dotenv
import bcrypt

load_dotenv("backend/.env")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/auditoria")
EXCEL_PATH = "docs/Lista - Operadores e Supervisores.xlsx"

def generate_password(length=12):
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choice(chars) for _ in range(length))

def get_connection():
    parsed = urlparse(DATABASE_URL)
    ssl_mode = 'require' if 'neon.tech' in DATABASE_URL else 'disable'
    return psycopg2.connect(
        dbname=parsed.path[1:],
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port,
        sslmode=ssl_mode
    )

def extract_data():
    df = pd.read_excel(EXCEL_PATH)
    df.fillna('', inplace=True)
    
    operators = []
    supervisors_in_excel = set()
    current_supervisor = ""
    
    for index, row in df.iterrows():
        func = str(row['Função']).strip()
        nome = str(row['Operadores']).strip()
        
        if 'Supervisor' in func:
            current_supervisor = nome.title()
            supervisors_in_excel.add(current_supervisor)
        elif 'Operador' in func:
            mat = str(row['Matrícula']).strip()
            # Try to handle .0 in case pandas parsed it as float
            if mat.endswith('.0'): mat = mat[:-2]
            
            huawei = str(row['Código Huawei']).strip()
            if huawei.endswith('.0'): huawei = huawei[:-2]
            
            if mat == '' or mat == '-': continue
            
            operators.append({
                'matricula': mat,
                'nome': nome,
                'setor': str(row['Setor']).strip(),
                'escala': '', # no escala in this file,
                'supervisor': current_supervisor,
                'status': 'ATIVO',
                'auditavel': 1,
                'huawei': huawei if huawei not in ('', '-') else None,
            })
            
    return operators, supervisors_in_excel

def main():
    print(f"[{datetime.datetime.now()}] Iniciando sync pela planilha OFICIAL...")
    operators, supervisors_in_excel = extract_data()
    print(f"Lidos {len(operators)} operadores e {len(supervisors_in_excel)} supervisores.")
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # Get existing admins
        cur.execute("SELECT username FROM users WHERE role = 'admin'")
        admins = {r[0] for r in cur.fetchall()}
        
        # 1. DELETE COLLABORATORS NOT IN SPREADSHEET
        excel_matriculas = tuple(op['matricula'] for op in operators)
        cur.execute(f"SELECT COUNT(*) FROM colaboradores WHERE matricula NOT IN %s", (excel_matriculas,))
        colabs_to_delete = cur.fetchone()[0]
        
        # Deletar auditorias relacionadas antes para não dar erro de FK
        cur.execute(f"DELETE FROM audits WHERE colaborador_id IN (SELECT id FROM colaboradores WHERE matricula NOT IN %s)", (excel_matriculas,))
        print("Audits de teste de colaboradores removidos foram deletadas.")
        
        cur.execute(f"DELETE FROM colaboradores WHERE matricula NOT IN %s", (excel_matriculas,))
        print(f"Deletados {colabs_to_delete} colaboradores que não estavam na planilha.")
        
        # 2. UPSERT COLLABORATORS
        for op in operators:
            cur.execute("SELECT id FROM colaboradores WHERE matricula = %s", (op['matricula'],))
            res = cur.fetchone()
            if res:
                update_q = """
                    UPDATE colaboradores SET
                        nome = %(nome)s,
                        setor = %(setor)s,
                        supervisor = %(supervisor)s,
                        status = %(status)s,
                        auditavel = %(auditavel)s,
                        id_huawei = %(huawei)s
                    WHERE id = %(id)s
                """
                op_update = op.copy()
                op_update['id'] = res[0]
                cur.execute(update_q, op_update)
            else:
                insert_q = """
                    INSERT INTO colaboradores (matricula, nome, setor, escala, supervisor, status, auditavel, id_huawei)
                    VALUES (%(matricula)s, %(nome)s, %(setor)s, %(escala)s, %(supervisor)s, %(status)s, %(auditavel)s, %(huawei)s)
                """
                cur.execute(insert_q, op)
        print(f"Upsert de {len(operators)} colaboradores concluído.")
        
        # 3. SUPERVISORS (USERS)
        new_passwords = {}
        for sup_name in supervisors_in_excel:
            parts = sup_name.lower().split()
            if len(parts) > 1:
                username = f"{parts[0]}.{parts[-1]}"
            else:
                username = parts[0]
            
            # Remove accents
            username = username.replace('á', 'a').replace('ã', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ç', 'c')
            
            cur.execute("SELECT username FROM users WHERE role = 'supervisor' AND supervisor_name = %s", (sup_name,))
            res = cur.fetchone()
            
            if not res:
                cur.execute("SELECT username FROM users WHERE username = %s", (username,))
                if not cur.fetchone():
                    pwd = generate_password()
                    hashed = bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    cur.execute("INSERT INTO users (username, password_hash, role, supervisor_name) VALUES (%s, %s, 'supervisor', %s)", (username, hashed, sup_name))
                    new_passwords[username] = pwd
                else:
                    cur.execute("UPDATE users SET supervisor_name = %s WHERE username = %s", (sup_name, username))
        
        # 4. DELETE SUPERVISORS NOT IN EXCEL
        excel_sup_names = tuple(supervisors_in_excel)
        cur.execute("SELECT username, supervisor_name FROM users WHERE role = 'supervisor' AND supervisor_name NOT IN %s", (excel_sup_names,))
        sups_to_delete = cur.fetchall()
        
        if sups_to_delete:
            print(f"Deletando {len(sups_to_delete)} supervisores que não estão mais na planilha: {sups_to_delete}")
            cur.execute("DELETE FROM users WHERE role = 'supervisor' AND supervisor_name NOT IN %s", (excel_sup_names,))

        # Commit all changes
        conn.commit()
        print("Alterações commitadas com sucesso!")
        
        if new_passwords:
            print("\nNOVAS CONTAS CRIADAS (SENHAS):")
            for u, p in new_passwords.items():
                print(f"Usuário: {u} | Senha: {p}")
        else:
            print("\nNenhuma conta de supervisor nova criada.")
            
    except Exception as e:
        conn.rollback()
        print(f"Erro: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
