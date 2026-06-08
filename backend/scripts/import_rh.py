import sys
import os
sys.path.append(os.path.abspath('backend'))
import pandas as pd
import bcrypt
import db.database as database

def run_import():
    file_path = 'instrucoes/01 - LISTAGEM.xlsx'
    
    print("Lendo planilha de funcionários...")
    df = pd.read_excel(file_path, sheet_name='BASE') if 'BASE' in pd.ExcelFile(file_path).sheet_names else pd.read_excel(file_path)
    
    conn = database.get_connection()
    c = conn.cursor()
    
    # Limpando registros antigos para garantir hierarquia atualizada
    c.execute('DELETE FROM colaboradores')
    
    supervisores_encontrados = set()
    cadastrados = 0

    for index, row in df.iterrows():
        matricula = str(row.get('MATRICULA', '')).replace('.0', '').strip()
        nome = str(row.get('NOME', '')).strip()
        setor = str(row.get('SETOR', '')).strip()
        supervisor = str(row.get('SUPERVISOR', '')).strip()
        escala = str(row.get('TURNO / OPERAÇÃO', '')).strip()
        status = str(row.get('STATUS', '')).strip().upper()

        if not nome or nome == 'nan' or 'total' in nome.lower() or status != 'ATIVO':
            continue
            
        if supervisor and supervisor != 'nan':
            supervisores_encontrados.add(supervisor)

        c.execute('''
            INSERT INTO colaboradores (matricula, nome, setor, supervisor, escala)
            VALUES (%s, %s, %s, %s, %s)
        ''', (matricula, nome, setor, supervisor, escala))
        cadastrados += 1
        
    for sup in supervisores_encontrados:
        supervisor_display_name = str(sup or "").strip()
        normalized_username = supervisor_display_name.lower()
        c.execute("SELECT id FROM users WHERE username = %s", (normalized_username,))
        if not c.fetchone():
            password_raw = normalized_username.replace(" ", "") + "123"
            pw_hash = bcrypt.hashpw(password_raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            
            c.execute(
                "INSERT INTO users (username, password_hash, role, supervisor_name) VALUES (%s, %s, %s, %s)",
                (normalized_username, pw_hash, "supervisor", supervisor_display_name)
            )
            print(f"[+] Conta de Supervisor criada: {supervisor_display_name} | Senha padrão: {password_raw}")

    conn.commit()
    conn.close()
    
    print(f"\n✅ Importação concluída! {cadastrados} operadores ativos cadastrados.")
    print(f"👥 {len(supervisores_encontrados)} supervisores mapeados.")

if __name__ == '__main__':
    run_import()
