import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import db.database as database

def clear_history():
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM huawei_sync_logs")
    c.execute("DELETE FROM fila_revisao_classificacao")
    c.execute("UPDATE configuracoes SET valor = 'false' WHERE chave = 'sync_lock'")
    conn.commit()
    print("Historico de sincronizacao da Huawei e Fila de Triagem apagados com sucesso!")

if __name__ == "__main__":
    clear_history()