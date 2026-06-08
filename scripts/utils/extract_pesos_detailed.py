import pandas as pd
import json

file_path = r'C:\Users\lucas.afonso\projetos\auditoria\auditoria_criterios\criterios_pesos\CRITÉRIOS - PESOS -.xlsm'

try:
    xl = pd.ExcelFile(file_path)
    pesos_df = xl.parse('Pesos')
except Exception as e:
    print(f"Erro ao ler o Excel: {e}")
    exit(1)

# Filter important columns
df_pesos = pesos_df[['Ref.Search', 'Questions', 'Peso', 'Deflator']].copy()

# Identificar Categorias a partir do prefixo de Ref.Search
df_pesos['Category'] = df_pesos['Ref.Search'].str.extract(r'^([A-Z\s]+)')

print("--- Extraindo e processando dados da planilha de Pesos ---")

output_data = {}

for cat in df_pesos['Category'].dropna().unique():
    subset = df_pesos[df_pesos['Category'] == cat]
    
    # Preencher valores nulos
    subset = subset.fillna({
        'Questions': 'Sem pergunta',
        'Peso': 0.0,
        'Deflator': 0.0
    })
    
    criterios = []
    for _, row in subset.iterrows():
        # Clean numeric values
        try:
            peso = float(row['Peso'])
        except (ValueError, TypeError):
            peso = 0.0
            
        try:
            deflator = float(row['Deflator'])
        except (ValueError, TypeError):
            deflator = 0.0
            
        criterios.append({
            'referencia': str(row['Ref.Search']).strip(),
            'pergunta': str(row['Questions']).strip(),
            'peso': peso,
            'deflator': deflator
        })
    
    output_data[str(cat).strip()] = criterios

output_file = 'criterios_pesos_extraidos.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

print(f"Sucesso! {len(output_data)} categorias extraídas e salvas em '{output_file}'.")

