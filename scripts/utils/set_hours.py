import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
import database

def set_hours():
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO configuracoes(chave, valor) VALUES ('huawei_horas_retroativas', '48') ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor")
    conn.commit()
    print("Janela de tempo expandida para 48 horas!")

if __name__ == "__main__":
    set_hours()
