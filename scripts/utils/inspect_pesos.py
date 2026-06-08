import pandas as pd

file_path = r'C:\Users\lucas.afonso\projetos\auditoria\auditoria_criterios\criterios_pesos\CRITÉRIOS - PESOS -.xlsm'

xl = pd.ExcelFile(file_path)
pesos_df = xl.parse('Pesos')
print("Pesos columns:", pesos_df.columns.tolist())
print(pesos_df.head(20))

# Also check BD sheet as it might have more labels
bd_df = xl.parse('BD')
print("\nBD columns:", bd_df.columns.tolist())
