import pandas as pd

file_path = r'C:\Users\lucas.afonso\projetos\auditoria\auditoria_criterios\criterios_pesos\CRITÉRIOS - PESOS -.xlsm'

xl = pd.ExcelFile(file_path)
pesos_df = xl.parse('Pesos')

mon1 = pesos_df[pesos_df['Ref.Search'].str.contains('MONITORAMENTO 1', na=False)]
print("--- MONITORAMENTO 1 Pesos ---")
print(mon1[['Ref.Search', 'Questions', 'Peso', 'Deflator']])

# Let's see if Questions column is really empty
print("\nAny non-null Questions in the whole sheet?")
print(pesos_df['Questions'].notnull().sum())

# Check columns of Monitoramento I sheet
mon1_sheet = xl.parse('Monitoramento I')
print("\n--- Monitoramento I Sheet Columns ---")
print(mon1_sheet.columns.tolist())
print(mon1_sheet.iloc[0:15, 0:5]) # Show first 15 rows and 5 columns
