import pandas as pd

xls = pd.ExcelFile('auditoria_criterios/criterios_pesos/CRITÉRIOS - PESOS -.xlsm')
keywords = ['GRS', 'BAS', 'DISTRIBUIÇÃO', 'LONGO PERCURSO', 'TRANSFERÊNCIA']

for sheet in xls.sheet_names:
    try:
        df = pd.read_excel(xls, sheet_name=sheet)
        for col in df.columns:
            if any(df[col].astype(str).str.contains('|'.join(keywords), case=False, na=False)):
                print(f"Sheet: {sheet} contains matches")
                break
    except Exception as e:
        print(f"Error reading sheet {sheet}: {e}")
