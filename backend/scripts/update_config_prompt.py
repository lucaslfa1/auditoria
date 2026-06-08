import db.database as database
database.init_db()
new_rule = """REGRA MONDELEZ EXPERT (Áudio Ruim):
1. TRADUÇÃO DE TERMOS (Mapeamento de Transcrição Confusa):
   - "uma delícia" ou "torre" = Saudação/Empresa (Identificação OK).
   - "moto", "tipo", "números" = Código do Cliente / Nota Fiscal (Informou Código OK).
   - "corrente", "meia oito...", "quatro oito..." = Número da Ocorrência (Ação Resultante OK).
   - "duas horas", "atualizando" = Próximo passo (Próximo passo OK).
   - "unibox", "moça", "interrogativa" = Transportadora/Interlocutor (Confirmou Interlocutor OK).
   - "horas que entrou", "nove e meia" = Informou endereço ou local de carga (Informou Endereço OK).
2. IDENTIFICAÇÃO DE NOME: Se o operador atende com tom profissional e diz a empresa, dê PASS no critério de Identificação mesmo que o nome individual esteja inaudível. Use "Operador Mondelez" como nome se não identificar um específico.
3. CRITÉRIOS NÃO PERTINENTES: Se a ligação for sobre uma ocorrência simples de Monitoramento I, os critérios de Logística Reversa (NF de devolução, quantidade de caixas) devem ser marcados como 'na', não como 'fail'."""

database.update_config(
    'ia_prompt_global',
    new_rule,
    alterado_por='script:update_config_prompt',
    motivo='Aplicar Regra Mondelez Expert via script manual',
    origem='script',
)
print("Regra Mondelez Expert aplicada com sucesso!")
