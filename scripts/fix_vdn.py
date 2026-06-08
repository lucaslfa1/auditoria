import sys
import os
sys.path.append(os.path.abspath('backend'))
import database

def update_vdn():
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE configuracoes SET valor = '25' WHERE chave = 'huawei_vdn'")
    conn.commit()
    print("VDN atualizado para 25 com sucesso!")
    cur.close()
    conn.close()

if __name__ == "__main__":
    update_vdn()
