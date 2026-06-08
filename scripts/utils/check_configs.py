import sys
import json
sys.path.append('backend')
import database

def check_configs():
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT chave, valor FROM configuracoes")
    rows = [dict(zip(['chave', 'valor'], row)) for row in cur.fetchall()]
    print(json.dumps(rows, indent=2))

if __name__ == '__main__':
    check_configs()