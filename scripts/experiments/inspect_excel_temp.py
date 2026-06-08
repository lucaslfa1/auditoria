import pandas as pd
import json
import os

folder = r"c:\Users\lucas.afonso\projetos\auditoria\instrucoes\setores"
files = [f for f in os.listdir(folder) if f.endswith('.xlsx')]

results = {}
for i, f in enumerate(files[:3]): # Inspecionando 3 planilhas diferentes para entender o padrão
    path = os.path.join(folder, f)
    # Header normalmente pode estar na primeira linha, ler preenchendo as calunas
    df = pd.read_excel(path, nrows=5)
    
    # Limpa colunas Unnamed
    cols = [str(c) for c in df.columns if 'Unnamed' not in str(c)]
    
    results[f] = {
        "columns": cols,
        "first_row": df.iloc[0].dropna().to_dict() if len(df) > 0 else {}
    }

print(json.dumps(results, indent=2, ensure_ascii=False))
