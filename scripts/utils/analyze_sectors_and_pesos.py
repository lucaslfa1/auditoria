import pandas as pd

file_path = r'C:\Users\lucas.afonso\projetos\auditoria\auditoria_criterios\criterios_pesos\CRITÉRIOS - PESOS -.xlsm'

xl = pd.ExcelFile(file_path)

print("--- Unique Setores in BD sheet ---")
bd_df = xl.parse('BD')
if 'Setor' in bd_df.columns:
    print(bd_df['Setor'].unique())
else:
    print("Column 'Setor' not found in BD sheet")

print("\n--- Pesos sheet content (subset) ---")
pesos_df = xl.parse('Pesos')
# Show rows where Questions is not null or show a sample
print(pesos_df[['Ref.Search', 'Questions', 'Peso', 'Deflator']].head(50))

print("\n--- Value Counts for Ref.Search to see patterns ---")
print(pesos_df['Ref.Search'].str.extract(r'^([A-Z\s]+)')[0].unique())
