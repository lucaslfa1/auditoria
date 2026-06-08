import sys
import os
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))
from dotenv import load_dotenv
load_dotenv('.env')

import database

def gerar_relatorio():
    print("=========================================================")
    print("   RELATÓRIO DE PERDAS NO FUNIL DE TELEFONIA (HUAWEI)    ")
    print("=========================================================")
    
    conn = database.get_connection()
    cur = conn.cursor()
    
    # 1. Analisar os logs recentes da Huawei para ver os motivos reais das perdas
    print("\n1. MOTIVOS DE BLOQUEIO (Últimas 24 horas):")
    cur.execute("""
        SELECT status, failure_reason, COUNT(*) 
        FROM huawei_sync_logs 
        WHERE sincronizado_em >= CURRENT_TIMESTAMP - INTERVAL '1 day' 
        GROUP BY status, failure_reason
        ORDER BY COUNT(*) DESC
    """)
    logs = cur.fetchall()
    total_tentativas = 0
    for status, reason, count in logs:
        total_tentativas += count
        motivo_amigavel = reason if reason else status
        if status == 'success':
            print(f"   ✅ SUCESSO: {count} ligações passaram pelos filtros.")
        else:
            print(f"   ❌ BLOQUEADO por '{motivo_amigavel}': {count} ligações perdidas.")
            
    print(f"\n   Total de tentativas no período: {total_tentativas}")

    # 2. Identificar operadores sem ID da Huawei
    print("\n---------------------------------------------------------")
    print("2. OPERADORES SEM ID DA HUAWEI CADASTRADO:")
    cur.execute("""
        SELECT nome, setor 
        FROM colaboradores 
        WHERE auditavel = TRUE 
          AND ativo = TRUE 
          AND (id_huawei IS NULL OR id_huawei = '')
        ORDER BY setor, nome
    """)
    sem_id = cur.fetchall()
    if sem_id:
        print(f"   ATENÇÃO: Encontramos {len(sem_id)} operadores ativos que NUNCA serão auditados pois não têm o 'ID Huawei' preenchido.")
        for nome, setor in sem_id[:10]: # Mostra os 10 primeiros para não poluir
            print(f"   - {nome} (Setor: {setor})")
        if len(sem_id) > 10:
            print("   ... e mais outros.")
        print("\n   => COMO RESOLVER: Vá no painel 'Colaboradores', edite esses nomes e preencha o campo 'ID Huawei'.")
    else:
        print("   Ótimo! Todos os operadores ativos e auditáveis possuem ID da Huawei.")

    # 3. Mostrar setores onde ligações receptivas estão sendo bloqueadas
    print("\n---------------------------------------------------------")
    print("3. SETORES DE RISCO (Bloqueando chamadas Inbound/Receptivas):")
    cur.execute("""
        SELECT setor, COUNT(*) 
        FROM colaboradores 
        WHERE auditavel = TRUE AND ativo = TRUE
        GROUP BY setor
    """)
    setores = cur.fetchall()
    # Apenas informativo sobre distribuição
    print(f"   Você possui operadores em {len(setores)} setores diferentes.")
    print("   Lembre-se: Setores marcados como 'Risco' na configuração ignoram sumariamente qualquer ligação onde o cliente liga para a nstech (Receptiva).")

    print("\n=========================================================")
    print("   FIM DO RELATÓRIO")
    print("=========================================================")
    
    conn.close()

if __name__ == '__main__':
    gerar_relatorio()
