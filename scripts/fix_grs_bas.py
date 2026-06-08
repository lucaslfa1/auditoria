import re

def process_file():
    with open('scripts/GRS_E_BAS.txt', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Adicionar nota de atualização no topo
    update_note = (
        "> [!ATENÇÃO - ATUALIZAÇÃO DE REGRA DE NEGÓCIO]\n"
        "> GRS (UTI) e BAS não fazem mais parte do mesmo setor.\n"
        "> Além disso, **NÃO SÃO AUDITADOS NA PARTE RECEPTIVA**, somente ATIVA.\n"
        "> A seção 'RECEPTIVA' foi completamente removida deste documento por ser obsoleta.\n\n"
    )
    
    # Remover o trecho RECEPTIVA
    # Procurar por "RECEPTIVA" até "## Página 3"
    pattern = re.compile(r'RECEPTIVA.*?## Página 3', re.DOTALL)
    new_content = pattern.sub('## Página 3', content)
    
    # Inserir no topo
    new_content = new_content.replace('# Critérios de Auditoria: CRITÉRIOS DA AUDITORIA - GRS & BAS', 
                                      '# Critérios de Auditoria: CRITÉRIOS DA AUDITORIA - GRS & BAS\n\n' + update_note)

    with open('scripts/GRS_E_BAS.txt', 'w', encoding='utf-8') as f:
        f.write(new_content)
        
process_file()
