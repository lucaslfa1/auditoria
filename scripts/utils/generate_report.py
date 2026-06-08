import pandas as pd

file_path = r'C:\Users\lucas.afonso\projetos\auditoria\auditoria_criterios\criterios_pesos\CRITÉRIOS - PESOS -.xlsm'

xl = pd.ExcelFile(file_path)
pesos_df = xl.parse('Pesos')

def get_labels(sheet_name, col_index=1, start_row=1, end_row=20):
    if sheet_name not in xl.sheet_names:
        return []
    df = xl.parse(sheet_name)
    labels = df.iloc[start_row:end_row, col_index].dropna().tolist()
    return labels

# Mapping sectors to sheet names and Ref.Search prefixes
sector_config = {
    'Mondelez': [
        {'name': 'Monitoramento I', 'prefix': 'MONITORAMENTO 1Receptiva'},
        {'name': 'Monitoramento II', 'prefix': 'MONITORAMENTO 2Receptiva'},
        {'name': 'Logística Reversa', 'prefix': 'LOGISTICA REVERSAReceptiva'}
    ],
    'Unilever': [
        {'name': 'Loss Tree', 'prefix': 'LOSS TREECliente'},
        {'name': 'Devolução', 'prefix': 'DEVOLUÇÃOCliente'},
        {'name': 'Atuação', 'prefix': 'ATUAÇÃO TRATATIVACliente'},
        {'name': 'Cabinets', 'prefix': 'CABINETSCliente'},
        {'name': 'Distribuição', 'prefix': 'DISTRIBUIÇÃO CD/Transportadora'}
    ],
    'Cadastro': [
        {'name': 'Antecedente', 'prefix': 'ANTECEDENTESReceptiva'},
        {'name': 'Impedimento', 'prefix': 'IMPEDIMENTOSReceptiva'}
    ]
}

report = []

for sector, categories in sector_config.items():
    print(f"\nProcessing Sector: {sector}")
    for cat in categories:
        sheet_name = cat['name']
        prefix = cat['prefix']
        
        labels = get_labels(sheet_name)
        # Search for weights in Pesos sheet
        # Usually they are indexed like Prefix1, Prefix2...
        
        print(f"  Category: {sheet_name} (Prefix: {prefix})")
        for i, label in enumerate(labels, 1):
            # Try to find prefix + i
            search_term = f"{prefix}{i}"
            weight_row = pesos_df[pesos_df['Ref.Search'].str.strip() == search_term]
            
            if weight_row.empty:
                # Try with space
                search_term = f"{prefix} {i}"
                weight_row = pesos_df[pesos_df['Ref.Search'].str.strip() == search_term]
            
            if not weight_row.empty:
                peso = weight_row.iloc[0]['Peso']
                deflator = weight_row.iloc[0]['Deflator']
                report.append({
                    'Setor': sector,
                    'Categoria': sheet_name,
                    'Item': label,
                    'Peso': peso,
                    'Deflator': deflator
                })
            else:
                report.append({
                    'Setor': sector,
                    'Categoria': sheet_name,
                    'Item': label,
                    'Peso': 'NOT FOUND',
                    'Deflator': 'NOT FOUND'
                })

report_df = pd.DataFrame(report)
print("\n--- Final Report ---")
print(report_df)

# Save to csv for easier reading if needed
report_df.to_csv('criterios_report.csv', index=False, encoding='utf-8-sig')
