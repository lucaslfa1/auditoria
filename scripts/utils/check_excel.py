import pandas as pd

df = pd.read_excel('docs/Lista - Operadores e Supervisores.xlsx')
df.fillna('', inplace=True)

supervisores = []
current_supervisor = ""

for index, row in df.iterrows():
    if 'Supervisor' in str(row['Função']):
        current_supervisor = row['Operadores']
        if current_supervisor not in supervisores:
            supervisores.append(current_supervisor)
            
print(f"Supervisores encontrados: {supervisores}")

ops_count = 0
for index, row in df.iterrows():
    if 'Operador' in str(row['Função']):
        ops_count += 1
print(f"Total de operadores: {ops_count}")
