import pandas as pd

file_path = r'C:\Users\lucas.afonso\projetos\auditoria\auditoria_criterios\criterios_pesos\CRITÉRIOS - PESOS -.xlsm'

xl = pd.ExcelFile(file_path)
pesos_df = xl.parse('Pesos')

# Find rows with non-null Questions
non_null_q = pesos_df[pesos_df['Questions'].notnull()]
print("--- Sample of non-null Questions in Pesos sheet ---")
print(non_null_q[['Ref.Search', 'Questions', 'Peso', 'Deflator']].head(20))

# Examine Monitoramento I sheet more carefully
mon1_sheet = xl.parse('Monitoramento I')
print("\n--- Monitoramento I Sheet (Full Content of first columns) ---")
# Print the first few rows of the first two columns to see the labels
print(mon1_sheet.iloc[0:20, [1, 4]]) 
