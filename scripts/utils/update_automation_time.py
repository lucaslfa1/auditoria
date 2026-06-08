import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # Define o intervalo do loop da automação para 600 segundos (10 minutos)
    cur.execute("UPDATE configuracoes SET valor = '600' WHERE chave = 'automacao_intervalo_segundos'")
    if cur.rowcount == 0:
        cur.execute("INSERT INTO configuracoes (chave, valor) VALUES ('automacao_intervalo_segundos', '600')")
        
    # Define a janela de busca na Huawei para 0.25 horas (15 minutos)
    # Isso dá uma margem de segurança de 5 minutos entre as chamadas de 10 minutos
    cur.execute("UPDATE configuracoes SET valor = '0.25' WHERE chave = 'huawei_horas_retroativas'")
    if cur.rowcount == 0:
        cur.execute("INSERT INTO configuracoes (chave, valor) VALUES ('huawei_horas_retroativas', '0.25')")
        
    conn.commit()
    print("Configuracoes de automacao atualizadas no banco.")
    conn.close()

if __name__ == "__main__":
    main()
