import os
import pandas as pd
import math
from db.database import get_connection, upsert_colaborador

SECTORS_DIR = os.environ.get(
    "SECTORS_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "instrucoes", "setores"),
)

def clean_val(val):
    if pd.isna(val) or val is None:
        return ""
    if isinstance(val, (int, float)) and math.isnan(val):
        return ""
    return str(val).strip()

def process_file(file_path):
    print(f"Processando arquivo: {os.path.basename(file_path)}")
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Erro ao ler {os.path.basename(file_path)}: {e}")
        return

    # Mapeamento dinâmico de colunas baseado na investigação anterior
    # Alguns arquivos chamam a escala de 'TURNO / OPERAÇÃO' outros só 'TURNO' e outros não tem.
    col_nome = next((c for c in df.columns if 'nome' in str(c).lower()), None)
    col_mat = next((c for c in df.columns if 'mat' in str(c).lower()), None)
    col_sup = next((c for c in df.columns if 'super' in str(c).lower()), None)
    col_setor = next((c for c in df.columns if 'setor' in str(c).lower()), None)
    col_escala = next((c for c in df.columns if 'turno' in str(c).lower() or 'escala' in str(c).lower() or 'opera' in str(c).lower()), None)
    col_status = next((c for c in df.columns if 'status' in str(c).lower() and 'sem nome' not in str(c).lower() and 'Unnamed' not in str(c)), None)
    col_weon = next((c for c in df.columns if 'weon' in str(c).lower()), None)
    col_huawei = next((c for c in df.columns if 'huawei' in str(c).lower()), None)

    if not col_nome:
        print(f"Alerta: Arquivo {os.path.basename(file_path)} ignorado (sem coluna de NOME)")
        return

    inserted_count = 0
    for _, row in df.iterrows():
        nome = clean_val(row[col_nome])
        status = clean_val(row[col_status]) if col_status else "ATIVO"
        
        # Só importar se o nome for válido
        if not nome or "unnamed" in nome.lower() or nome.lower() == "nan":
            continue

        matricula = clean_val(row[col_mat]) if col_mat else ""
        supervisor = clean_val(row[col_sup]) if col_sup else ""
        setor = clean_val(row[col_setor]) if col_setor else ""
        escala = clean_val(row[col_escala]) if col_escala else ""
        # Normalizando alguns valores de status que vêm nulos na planilha como "ATIVO" por padrão
        if not status:
            status = "ATIVO"

        # Normalização de nomes antigos → atuais
        # GRS é o nome antigo de UTI (ainda usado em algumas planilhas)
        if setor.upper() == "GRS":
            setor = "UTI"
        if "GRS" in escala.upper():
            escala = escala.upper().replace("GRS", "UTI")

        id_weon = clean_val(row[col_weon]) if col_weon else ""
        id_huawei = clean_val(row[col_huawei]) if col_huawei else ""

        try:
            upsert_colaborador(matricula, nome, supervisor, setor, escala, status, id_weon, id_huawei)
            inserted_count += 1
        except Exception as e:
            print(f"Erro na inserção de {nome}: {e}")

    print(f"Arquivo {os.path.basename(file_path)}: {inserted_count} operadores válidos processados.")

def run_import():
    # Tabela colaboradores já é criada pelas migrations (runtime_schema).
    # Não recriar manualmente aqui.

    if not os.path.exists(SECTORS_DIR):
        print(f"Diretório não encontrado: {SECTORS_DIR}")
        return

    files = [f for f in os.listdir(SECTORS_DIR) if f.endswith(".xlsx") and not f.startswith("~")]
    print(f"Iniciando importação de {len(files)} planilhas de setor...")
    
    for f in files:
        process_file(os.path.join(SECTORS_DIR, f))
    
    print("Processamento concluído com sucesso!")

if __name__ == "__main__":
    run_import()
