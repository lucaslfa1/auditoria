import pandas as pd

file_path = r'C:\Users\lucas.afonso\projetos\auditoria\auditoria_criterios\criterios_pesos\CRITÉRIOS - PESOS -.xlsm'

xl = pd.ExcelFile(file_path)

sheets_to_extract = [
    'Monitoramento I', 'Monitoramento II', 'Logística Reversa',
    'Loss Tree', 'Devolução', 'Atuação', 'Cabinets', 'Distribuição',
    'Receptiva', 'Checklist', 'Antecedente', 'Impedimento'
]

results = {}

for sheet in sheets_to_extract:
    if sheet in xl.sheet_names:
        df = xl.parse(sheet)
        print(f"\n--- Sheet: {sheet} ---")
        print(df.head(10))
        # Usually 'Critério Avaliado' or similar
        results[sheet] = df
    else:
        print(f"Sheet {sheet} not found")

# Let's also check the 'Pesos' sheet again but for non-null Questions
pesos_df = xl.parse('Pesos')
print("\n--- Pesos sheet (Non-null Questions) ---")
print(pesos_df[pesos_df['Questions'].notnull()][['Ref.Search', 'Questions', 'Peso', 'Deflator']].head(20))
