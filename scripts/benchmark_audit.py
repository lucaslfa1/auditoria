import requests
import json
import os
from pathlib import Path

# Configurações do ambiente
BASE_DIR = Path("C:/Users/lucas.afonso/projetos/auditoria")
API_URL = "http://localhost:8080/api/audit"
LOGIN_URL = "http://localhost:8080/api/auth/login"
LOG_FILE = BASE_DIR / "logs" / "audit_benchmark_results.log"

os.makedirs(LOG_FILE.parent, exist_ok=True)

# ============================================================
# Critérios REAIS por setor/alerta (extraídos de criteria.md)
# ============================================================

# Critérios comuns de comportamento (presentes em quase todos os alertas)
_COMPORTAMENTO_BAS = [
    {'id': 'cordialidade', 'label': 'Realizou a despedida padrão com cordialidade?', 'weight': 0.30},
    {'id': 'mudo', 'label': 'Utilizou a função mudo corretamente para evitar ruídos externos?', 'weight': 0.30},
    {'id': 'silencio', 'label': 'Evitou silêncios prolongados (mais de 45 segundos sem interação)?', 'weight': 0.15},
    {'id': 'registro', 'label': 'O operador registrou corretamente o contato no sistema?', 'weight': 0.20},
    {'id': 'finalizacao', 'label': 'Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?', 'weight': 0.30},
    {'id': 'entonacao', 'label': 'O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?', 'weight': 0.10},
]

_COMPORTAMENTO_UNILEVER = [
    {'id': 'cordialidade', 'label': 'Realizou a despedida padrão com cordialidade?', 'weight': 0.30},
    {'id': 'mudo', 'label': 'Utilizou a função mudo corretamente para evitar ruídos externos?', 'weight': 0.30},
    {'id': 'silencio', 'label': 'Evitou silêncios prolongados (mais de 45 segundos sem interação)?', 'weight': 0.15},
    {'id': 'finalizacao', 'label': 'Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?', 'weight': 0.20},
    {'id': 'qualificacao', 'label': 'O operador realizou a qualificação do atendimento corretamente?', 'weight': 0.30},
    {'id': 'entonacao', 'label': 'O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?', 'weight': 0.10},
]

_COMPORTAMENTO_CADASTRO = [
    {'id': 'cordialidade', 'label': 'Realizou a despedida padrão com cordialidade?', 'weight': 0.30},
    {'id': 'mudo', 'label': 'Utilizou a função mudo corretamente para evitar ruídos externos?', 'weight': 0.30},
    {'id': 'silencio', 'label': 'Evitou silêncios prolongados (mais de 45 segundos sem interação)?', 'weight': 0.15},
    {'id': 'finalizacao', 'label': 'Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?', 'weight': 0.30},
    {'id': 'qualificacao', 'label': 'O operador realizou a qualificação do atendimento corretamente?', 'weight': 0.25},
    {'id': 'entonacao', 'label': 'O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?', 'weight': 0.10},
]

_COMPORTAMENTO_LOGISTICA = [
    {'id': 'cordialidade', 'label': 'Realizou a despedida padrão com cordialidade?', 'weight': 0.30},
    {'id': 'mudo', 'label': 'Utilizou a função mudo corretamente para evitar ruídos externos?', 'weight': 0.30},
    {'id': 'silencio', 'label': 'Evitou silêncios prolongados (mais de 45 segundos sem interação)?', 'weight': 0.15},
    {'id': 'finalizacao', 'label': 'Após a resolução do alerta, finalizou corretamente a ligação sem reter a linha desnecessariamente (10s)?', 'weight': 0.20},
    {'id': 'qualificacao', 'label': 'O operador realizou a qualificação do atendimento corretamente?', 'weight': 0.30},
    {'id': 'entonacao', 'label': 'O volume de voz, entonação e condução da chamada transmitiram credibilidade e cordialidade, sem excesso de gírias?', 'weight': 0.10},
]


def _alert(alert_id, label, context, sector_id, specific_criteria, comportamento):
    criteria = []
    idx = 1
    for c in specific_criteria:
        criteria.append({**c, 'id': str(idx)})
        idx += 1
    for c in comportamento:
        criteria.append({**c, 'id': str(idx)})
        idx += 1
    return {
        'id': alert_id,
        'label': label,
        'context': context,
        'sector_id': sector_id,
        'criteria': criteria,
    }


# === 4.1.1 BAS Prioritário - Motorista ===
ALERT_BAS_PRIORITARIO_MOT = _alert(
    'UTI-PRIORITARIO-MOT', 'Alerta Prioritário - Contato com Motorista',
    'Auditoria de ligação do setor BAS/UTI/Distribuição/Transferência para tratativa de alerta prioritário com o motorista. O operador deve identificar-se, validar a senha, informar motivo, confirmar localização e condição, identificar causa do alerta, solicitar vídeo se necessário.',
    'uti',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'O operador confirmou a senha de segurança antes de prosseguir?', 'weight': 2.00},
        {'id': '3', 'label': 'O operador informou claramente o motivo do contato?', 'weight': 1.03},
        {'id': '4', 'label': 'O operador confirmou a localização e a condição do motorista?', 'weight': 1.70},
        {'id': '5', 'label': 'O operador identificou o motivo do alerta?', 'weight': 1.92},
        {'id': '6', 'label': 'O operador solicitou vídeo do veículo nos casos necessários?', 'weight': 1.70},
    ],
    _COMPORTAMENTO_BAS,
)

# === 4.1.2 BAS Prioritário - Cliente ===
ALERT_BAS_PRIORITARIO_CLI = _alert(
    'UTI-PRIORITARIO-CLI', 'Alerta Prioritário - Contato com Cliente',
    'Auditoria de ligação do setor BAS/UTI/Distribuição/Transferência para tratativa de alerta prioritário com o cliente. O operador deve identificar-se, confirmar interlocutor, informar motivo, enfatizar suspeita de sinistro, informar ações adotadas, local do alerta e contatos do condutor.',
    'uti',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'O operador informou claramente o motivo do contato?', 'weight': 1.20},
        {'id': '4', 'label': 'O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?', 'weight': 2.00},
        {'id': '5', 'label': 'O operador informou as ações adotadas até o momento?', 'weight': 1.15},
        {'id': '6', 'label': 'O operador informou corretamente o local onde gerou o alerta?', 'weight': 1.80},
        {'id': '7', 'label': 'O operador confirmou os contatos atuais do condutor?', 'weight': 1.80},
    ],
    _COMPORTAMENTO_BAS,
)

# === 4.1.3 BAS Posição em Atraso - Motorista ===
ALERT_BAS_POSICAO_MOT = _alert(
    'UTI-POSICAO-MOT', 'Posição em Atraso - Contato com Motorista',
    'Auditoria de ligação do setor BAS/UTI/Distribuição para tratativa de posição em atraso com o motorista. O operador deve identificar-se, validar senha, informar motivo, confirmar localização, orientar forçar posicionamento, identificar motivo da perda de sinal e informar riscos.',
    'uti',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'O operador confirmou a senha de segurança antes de prosseguir?', 'weight': 2.00},
        {'id': '3', 'label': 'O operador informou claramente o motivo do contato?', 'weight': 1.03},
        {'id': '4', 'label': 'O operador confirmou a localização atual do motorista?', 'weight': 1.22},
        {'id': '5', 'label': 'Passou orientações para forçar posicionamento do rastreador?', 'weight': 2.00},
        {'id': '6', 'label': 'O operador procurou identificar o motivo da perda de sinal?', 'weight': 1.05},
        {'id': '7', 'label': 'O operador informou os riscos operacionais e de seguro caso o sinal não restabelecer?', 'weight': 1.05},
    ],
    _COMPORTAMENTO_BAS,
)

# === 4.1.4 BAS Posição em Atraso - Cliente ===
ALERT_BAS_POSICAO_CLI = _alert(
    'UTI-POSICAO-CLI', 'Posição em Atraso - Contato com Cliente',
    'Auditoria de ligação do setor BAS/UTI/Distribuição para tratativa de posição em atraso com o cliente.',
    'uti',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'O operador informou claramente o motivo do contato?', 'weight': 1.20},
        {'id': '4', 'label': 'O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?', 'weight': 1.20},
        {'id': '5', 'label': 'O operador informou as ações adotadas, resumindo os contatos/tratativas realizados?', 'weight': 1.15},
        {'id': '6', 'label': 'O operador informou corretamente o local onde perdeu a posição?', 'weight': 1.10},
        {'id': '7', 'label': 'O operador questionou se o conjunto possui equipamento de contingência?', 'weight': 1.10},
        {'id': '8', 'label': 'O operador questionou se o cliente tem informações recentes sobre o veículo e o motorista?', 'weight': 1.10},
        {'id': '9', 'label': 'O operador confirmou os contatos atuais do condutor?', 'weight': 1.10},
    ],
    _COMPORTAMENTO_BAS,
)

# === 4.1.5 BAS Parada Indevida - Motorista ===
ALERT_BAS_PARADA_MOT = _alert(
    'UTI-PARADA-MOT', 'Parada Indevida - Contato com Motorista',
    'Auditoria de ligação do setor BAS/UTI/Distribuição para tratativa de parada indevida com o motorista. O operador deve identificar-se, validar senha, informar motivo, confirmar razão da parada, verificar plano de viagem, orientar a reiniciar viagem e informar riscos.',
    'uti',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'O operador confirmou a senha de segurança antes de prosseguir?', 'weight': 2.00},
        {'id': '3', 'label': 'O operador informou claramente o motivo do contato?', 'weight': 1.03},
        {'id': '4', 'label': 'O operador confirmou o motivo pelo qual o motorista parou em local indevido?', 'weight': 1.30},
        {'id': '5', 'label': 'O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento?', 'weight': 1.30},
        {'id': '6', 'label': 'O operador orientou o motorista a reiniciar a viagem e seguir para um local homologado?', 'weight': 1.32},
        {'id': '7', 'label': 'O operador informou os riscos operacionais da parada indevida, incluindo problemas com seguro?', 'weight': 1.40},
    ],
    _COMPORTAMENTO_BAS,
)

# === 4.1.6 BAS Parada Indevida - Cliente ===
ALERT_BAS_PARADA_CLI = _alert(
    'UTI-PARADA-CLI', 'Parada Indevida - Contato com Cliente',
    'Auditoria de ligação do setor BAS/UTI/Distribuição para tratativa de parada indevida com o cliente.',
    'uti',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'O operador informou claramente o motivo do contato?', 'weight': 1.20},
        {'id': '4', 'label': 'O operador informou as ações adotadas até o momento?', 'weight': 1.15},
        {'id': '5', 'label': 'O operador informou corretamente o local da parada?', 'weight': 1.40},
        {'id': '6', 'label': 'O operador confirmou se os pontos de parada autorizada foram passados ao motorista antes do início da viagem?', 'weight': 1.40},
        {'id': '7', 'label': 'O operador informou ao cliente sobre os riscos operacionais e de seguro caso a parada indevida permaneça?', 'weight': 1.40},
        {'id': '8', 'label': 'O operador indicou medidas de segurança ao cliente?', 'weight': 1.40},
    ],
    _COMPORTAMENTO_BAS,
)

# === 4.1.7 BAS Desvio de Rota - Motorista ===
ALERT_BAS_DESVIO_MOT = _alert(
    'UTI-DESVIO-MOT', 'Desvio de Rota - Contato com Motorista',
    'Auditoria de ligação do setor BAS/UTI/Distribuição para tratativa de desvio de rota com o motorista. O operador deve identificar-se, validar senha, informar motivo, confirmar razão do desvio, verificar plano de viagem, orientar retorno à rota, coletar itinerário e informar riscos.',
    'uti',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'O operador confirmou a senha de segurança antes de prosseguir?', 'weight': 2.00},
        {'id': '3', 'label': 'O operador informou claramente o motivo do contato?', 'weight': 1.03},
        {'id': '4', 'label': 'O operador confirmou o motivo do desvio de rota?', 'weight': 1.05},
        {'id': '5', 'label': 'Confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento?', 'weight': 1.05},
        {'id': '6', 'label': 'Orientou o motorista a retornar para a rota ou permanecer parado até confirmação com o cliente?', 'weight': 1.05},
        {'id': '7', 'label': 'Coletou qual itinerário o motorista está realizando?', 'weight': 1.05},
        {'id': '8', 'label': 'O operador informou os riscos operacionais e de seguro caso o motorista continue fora da rota?', 'weight': 1.12},
    ],
    _COMPORTAMENTO_BAS,
)

# === 4.1.8 BAS Desvio de Rota - Cliente ===
ALERT_BAS_DESVIO_CLI = _alert(
    'UTI-DESVIO-CLI', 'Desvio de Rota - Contato com Cliente',
    'Auditoria de ligação do setor BAS/UTI/Distribuição para tratativa de desvio de rota com o cliente.',
    'uti',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'O operador informou claramente o motivo do contato?', 'weight': 1.20},
        {'id': '4', 'label': 'O operador enfatizou ao cliente que estava atuando em uma suspeita de sinistro?', 'weight': 1.30},
        {'id': '5', 'label': 'O operador informou as ações adotadas, resumindo os contatos/tratativas realizados?', 'weight': 1.15},
        {'id': '6', 'label': 'O operador informou o trajeto que o motorista está realizando e o que estava programado na rota?', 'weight': 1.00},
        {'id': '7', 'label': 'O operador questionou se o cliente tem conhecimento do motivo do desvio?', 'weight': 1.00},
        {'id': '8', 'label': 'O operador confirmou se o motorista recebeu o plano de viagem e instruções de rastreamento antes da viagem?', 'weight': 1.00},
        {'id': '9', 'label': 'O operador indicou medidas de segurança ao cliente?', 'weight': 1.30},
    ],
    _COMPORTAMENTO_BAS,
)

# === 4.2.1 Cadastro - Antecedentes ===
ALERT_CADASTRO_ANTECEDENTES = _alert(
    'CADASTRO-ANTECEDENTES', 'Antecedentes - Contato Receptivo',
    'Auditoria de ligação receptiva do setor Cadastro para tratativa de alerta de antecedentes. O operador deve identificar-se, solicitar CPF/Placa, informar sobre bloqueio/cadastro negativado, processo/inquérito/apontamento, estado/justiça federal e documento necessário. NAO exige senha.',
    'cadastro',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'O operador solicitou CPF/Placa para iniciar o atendimento?', 'weight': 1.60},
        {'id': '3', 'label': 'O operador enfatizou sobre bloqueio/cadastro negativado?', 'weight': 1.70},
        {'id': '4', 'label': 'O operador informou se o cliente possui inquérito/processo/apontamento?', 'weight': 1.70},
        {'id': '5', 'label': 'O operador informou qual o estado/justiça federal?', 'weight': 1.65},
        {'id': '6', 'label': 'O operador informou qual documento é necessário?', 'weight': 1.65},
    ],
    _COMPORTAMENTO_CADASTRO,
)

# === 4.3.1 Unilever - Devolução ===
ALERT_UNILEVER_DEVOLUCAO = _alert(
    'UNILEVER-DEVOLUCAO', 'Devolução - Contato com Cliente',
    'Auditoria de ligação do setor Logística Unilever para tratativa de devolução com o cliente. O operador deve identificar-se, confirmar interlocutor, informar devolução e próximo passo, nome/endereço/código do cliente, quantidade de caixas e registrar ação. NAO exige senha.',
    'logistica_unilever',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'Informou que a devolução foi confirmada e qual o próximo passo?', 'weight': 0.76},
        {'id': '4', 'label': 'Informou o nome do cliente corretamente?', 'weight': 1.60},
        {'id': '5', 'label': 'Informou o endereço correto do cliente?', 'weight': 1.60},
        {'id': '6', 'label': 'Informou o código do cliente?', 'weight': 1.60},
        {'id': '7', 'label': 'Confirmou a quantidade de caixas a serem devolvidas?', 'weight': 0.81},
        {'id': '8', 'label': 'Ação resultante (e-mail, ligação, mobile) foi registrada corretamente?', 'weight': 1.58},
    ],
    _COMPORTAMENTO_UNILEVER,
)

# === 4.3.2 Unilever - Cabinets ===
ALERT_UNILEVER_CABINETS = _alert(
    'UNILEVER-CABINETS', 'Cabinets - Contato com Cliente',
    'Auditoria de ligação do setor Logística Unilever para tratativa de cabinets (insucesso) com o cliente. O operador deve identificar-se, confirmar interlocutor, comunicar insucesso, nome/endereço/código do cliente e registrar ação. NAO exige senha.',
    'logistica_unilever',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'Informou que irá comunicar um insucesso?', 'weight': 1.57},
        {'id': '4', 'label': 'Informou o nome do cliente corretamente?', 'weight': 1.60},
        {'id': '5', 'label': 'Informou o endereço correto do cliente?', 'weight': 1.60},
        {'id': '6', 'label': 'Informou o código do cliente?', 'weight': 1.60},
        {'id': '7', 'label': 'Ação resultante (e-mail, ligação, mobile) foi registrada corretamente?', 'weight': 1.58},
    ],
    _COMPORTAMENTO_UNILEVER,
)

# === 4.3.3 Unilever - Atuação Tratativa ===
ALERT_UNILEVER_TRATATIVA = _alert(
    'UNILEVER-TRATATIVA', 'Atuação Tratativa - Contato com Cliente',
    'Auditoria de ligação do setor Logística Unilever para tratativa de atuação com o cliente. O operador deve identificar-se, confirmar interlocutor, informar motivo, nome/endereço/código do cliente, motivo da devolução, quantidade de caixas, tempo de espera e registrar ação. NAO exige senha.',
    'logistica_unilever',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'Informou o motivo do contato?', 'weight': 1.32},
        {'id': '4', 'label': 'Informou o nome do cliente corretamente?', 'weight': 1.00},
        {'id': '5', 'label': 'Informou o endereço correto do cliente?', 'weight': 1.00},
        {'id': '6', 'label': 'Informou o código do cliente?', 'weight': 0.85},
        {'id': '7', 'label': 'Informou o motivo da devolução?', 'weight': 1.00},
        {'id': '8', 'label': 'Informou a quantidade de caixas?', 'weight': 1.00},
        {'id': '9', 'label': 'Informou o tempo de espera?', 'weight': 1.00},
        {'id': '10', 'label': 'Ação resultante (e-mail, ligação, mobile). Ação final ao atendimento?', 'weight': 0.78},
    ],
    _COMPORTAMENTO_UNILEVER,
)

# === 4.4.x Logística Geral ===
# Atraso (baseado em 4.1.3 adaptado para logística - sem senha)
ALERT_LOGISTICA_ATRASO = _alert(
    'LOGISTICA-ATRASO', 'Atraso - Contato com Motorista',
    'Auditoria de ligação do setor Logística para tratativa de atraso com o motorista. O operador deve identificar-se, confirmar interlocutor, informar motivo do contato, confirmar localização, orientar sobre posicionamento e informar riscos. NAO exige senha.',
    'logistica',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'Informou o motivo do contato?', 'weight': 2.00},
        {'id': '4', 'label': 'O operador confirmou a localização atual do motorista?', 'weight': 1.50},
        {'id': '5', 'label': 'Passou orientações para forçar posicionamento do rastreador?', 'weight': 2.00},
        {'id': '6', 'label': 'O operador procurou identificar o motivo da perda de sinal/atraso?', 'weight': 1.50},
        {'id': '7', 'label': 'O operador informou os riscos operacionais caso o sinal não restabelecer?', 'weight': 1.00},
    ],
    _COMPORTAMENTO_LOGISTICA,
)

# Desvio de Rota (logística - sem senha)
ALERT_LOGISTICA_DESVIO = _alert(
    'LOGISTICA-DESVIO', 'Desvio de Rota - Contato com Motorista',
    'Auditoria de ligação do setor Logística para tratativa de desvio de rota com o motorista. O operador deve identificar-se, confirmar interlocutor, informar motivo, confirmar razão do desvio, orientar retorno e informar riscos. NAO exige senha.',
    'logistica',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'Informou o motivo do contato?', 'weight': 2.00},
        {'id': '4', 'label': 'O operador confirmou o motivo do desvio de rota?', 'weight': 1.50},
        {'id': '5', 'label': 'Confirmou se o motorista recebeu o plano de viagem?', 'weight': 1.50},
        {'id': '6', 'label': 'Orientou o motorista a retornar para a rota?', 'weight': 1.50},
        {'id': '7', 'label': 'O operador informou os riscos operacionais do desvio?', 'weight': 1.50},
    ],
    _COMPORTAMENTO_LOGISTICA,
)

# Parada Indevida (logística - sem senha)
ALERT_LOGISTICA_PARADA = _alert(
    'LOGISTICA-PARADA', 'Parada Indevida - Contato com Motorista',
    'Auditoria de ligação do setor Logística para tratativa de parada indevida com o motorista. O operador deve identificar-se, confirmar interlocutor, informar motivo, confirmar razão da parada, verificar plano de viagem, orientar reiniciar viagem e informar riscos. NAO exige senha.',
    'logistica',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'Informou o motivo do contato?', 'weight': 2.00},
        {'id': '4', 'label': 'O operador confirmou o motivo pelo qual o motorista parou?', 'weight': 1.50},
        {'id': '5', 'label': 'O operador confirmou se o motorista recebeu o plano de viagem?', 'weight': 1.50},
        {'id': '6', 'label': 'Orientou o motorista a reiniciar a viagem e seguir para um local homologado?', 'weight': 1.50},
        {'id': '7', 'label': 'O operador informou os riscos operacionais da parada indevida?', 'weight': 1.50},
    ],
    _COMPORTAMENTO_LOGISTICA,
)

# Posição em Atraso (logística - sem senha)
ALERT_LOGISTICA_POSICAO = _alert(
    'LOGISTICA-POSICAO', 'Posição em Atraso - Contato com Motorista',
    'Auditoria de ligação do setor Logística para tratativa de posição em atraso com o motorista. O operador deve identificar-se, confirmar interlocutor, informar motivo, confirmar localização, orientar posicionamento e informar riscos. NAO exige senha.',
    'logistica',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'Informou o motivo do contato?', 'weight': 2.00},
        {'id': '4', 'label': 'O operador confirmou a localização atual do motorista?', 'weight': 1.50},
        {'id': '5', 'label': 'Passou orientações para forçar posicionamento do rastreador?', 'weight': 2.00},
        {'id': '6', 'label': 'O operador procurou identificar o motivo da perda de sinal?', 'weight': 1.50},
        {'id': '7', 'label': 'O operador informou os riscos operacionais caso o sinal não restabelecer?', 'weight': 1.00},
    ],
    _COMPORTAMENTO_LOGISTICA,
)

# Temperatura (logística - sem senha)
ALERT_LOGISTICA_TEMPERATURA_MOT = _alert(
    'LOGISTICA-TEMPERATURA-MOT', 'Controle de Temperatura - Contato com Motorista',
    'Auditoria de ligação do setor Logística para tratativa de controle/desligamento de temperatura com o motorista. O operador deve identificar-se, confirmar interlocutor, informar motivo, verificar status da temperatura, orientar sobre procedimentos e informar riscos. NAO exige senha.',
    'logistica',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'Informou o motivo do contato?', 'weight': 2.00},
        {'id': '4', 'label': 'O operador verificou o status atual da temperatura?', 'weight': 2.00},
        {'id': '5', 'label': 'O operador orientou sobre os procedimentos corretos?', 'weight': 2.00},
        {'id': '6', 'label': 'O operador informou os riscos caso a temperatura não seja normalizada?', 'weight': 1.00},
    ],
    _COMPORTAMENTO_LOGISTICA,
)

ALERT_LOGISTICA_TEMPERATURA_CLI = _alert(
    'LOGISTICA-TEMPERATURA-CLI', 'Controle de Temperatura - Contato com Cliente',
    'Auditoria de ligação do setor Logística para tratativa de controle/desligamento de temperatura com o cliente. O operador deve identificar-se, confirmar interlocutor, informar motivo, relatar status da temperatura, ações tomadas e próximos passos. NAO exige senha.',
    'logistica',
    [
        {'id': '1_saudacao', 'label': 'O operador realizou a saudação?', 'weight': 0.075},
        {'id': '1_nome', 'label': 'O operador informou o próprio nome?', 'weight': 0.075},
        {'id': '1_setor', 'label': 'O operador informou o setor?', 'weight': 0.075},
        {'id': '1_empresa', 'label': 'O operador informou a empresa?', 'weight': 0.075},
        {'id': '2', 'label': 'Confirmou com quem está falando?', 'weight': 0.40},
        {'id': '3', 'label': 'Informou o motivo do contato?', 'weight': 2.00},
        {'id': '4', 'label': 'O operador relatou o status atual da temperatura?', 'weight': 2.00},
        {'id': '5', 'label': 'O operador informou as ações tomadas até o momento?', 'weight': 2.00},
        {'id': '6', 'label': 'O operador informou os próximos passos?', 'weight': 1.00},
    ],
    _COMPORTAMENTO_LOGISTICA,
)


def get_alert_config(root_path: str, filename: str) -> dict:
    """Determina o alert_config correto baseado no caminho e nome do arquivo."""
    root_upper = root_path.upper().replace("\\", "/")
    fname_upper = filename.upper()

    # RAST.-UTI-DIST-BAS / MOTORISTA
    if "RAST" in root_upper and "MOTORISTA" in root_upper:
        if fname_upper.startswith("PRIORIT"):
            return ALERT_BAS_PRIORITARIO_MOT
        if fname_upper.startswith("POSI"):
            return ALERT_BAS_POSICAO_MOT
        if fname_upper.startswith("PARADA"):
            return ALERT_BAS_PARADA_MOT
        if fname_upper.startswith("DESVIO"):
            return ALERT_BAS_DESVIO_MOT
        return ALERT_BAS_PRIORITARIO_MOT  # fallback

    # RAST.-UTI-DIST-BAS / CLIENTE
    if "RAST" in root_upper and "CLIENTE" in root_upper:
        if fname_upper.startswith("PRIORIT"):
            return ALERT_BAS_PRIORITARIO_CLI
        if fname_upper.startswith("POSI"):
            return ALERT_BAS_POSICAO_CLI
        if fname_upper.startswith("PARADA"):
            return ALERT_BAS_PARADA_CLI
        if fname_upper.startswith("DESVIO"):
            return ALERT_BAS_DESVIO_CLI
        return ALERT_BAS_PRIORITARIO_CLI  # fallback

    # CADASTRO
    if "CADASTRO" in root_upper:
        return ALERT_CADASTRO_ANTECEDENTES

    # UNILEVER
    if "UNILEVER" in root_upper:
        if "DEVOLU" in fname_upper:
            return ALERT_UNILEVER_DEVOLUCAO
        if "CABINET" in fname_upper:
            return ALERT_UNILEVER_CABINETS
        if "ATUA" in fname_upper or "TRATATIVA" in fname_upper:
            return ALERT_UNILEVER_TRATATIVA
        return ALERT_UNILEVER_DEVOLUCAO  # fallback

    # LOGÍSTICA
    if "LOG" in root_upper:
        if "ATRASO" in fname_upper:
            return ALERT_LOGISTICA_ATRASO
        if "DESVIO" in fname_upper:
            return ALERT_LOGISTICA_DESVIO
        if "PARADA" in fname_upper:
            return ALERT_LOGISTICA_PARADA
        if "POSI" in fname_upper:
            return ALERT_LOGISTICA_POSICAO
        if "TEMPERATURA" in fname_upper:
            if "CLIENTE" in fname_upper:
                return ALERT_LOGISTICA_TEMPERATURA_CLI
            return ALERT_LOGISTICA_TEMPERATURA_MOT
        return ALERT_LOGISTICA_ATRASO  # fallback

    # Fallback genérico (não deveria chegar aqui)
    return ALERT_BAS_PRIORITARIO_MOT


def login():
    session = requests.Session()
    username = (os.getenv("BACKEND_TEST_USERNAME") or "").strip()
    password = (os.getenv("BACKEND_TEST_PASSWORD") or "").strip()
    if not username or not password:
        raise RuntimeError("Configure BACKEND_TEST_USERNAME e BACKEND_TEST_PASSWORD para executar o benchmark.")
    try:
        res = session.post(LOGIN_URL, json={"username": username, "password": password})
        if res.status_code != 200:
            print(f"Erro no login: {res.status_code}")
    except Exception as e:
        print(f"Erro ao conectar no backend: {e}")
    return session


def run_benchmark():
    session = login()
    test_files = []

    for root, dirs, files in os.walk(str(BASE_DIR / "Ligações")):
        if "BOAS" in root or "RUINS" in root:
            label = "BOM" if "BOAS" in root else "RUIM"

            wav_files = [f for f in files if f.endswith(('.wav', '.mp3'))]
            for f in wav_files[:2]:
                alert_cfg = get_alert_config(root, f)
                test_files.append({
                    "path": os.path.join(root, f),
                    "expected": label,
                    "sector_id": alert_cfg['sector_id'],
                    "alert_config": alert_cfg,
                    "filename": f
                })

    if not test_files:
        print("Nenhum arquivo encontrado nas pastas BOAS/RUINS.")
        return

    print(f"Iniciando benchmark com {len(test_files)} arquivos...")

    results = {"total": 0, "success": 0, "failed": 0}

    with open(LOG_FILE, "w", encoding="utf-8") as log:
        log.write("=== BENCHMARK DE AUDITORIA ===\n\n")

        for test in test_files:
            alert_cfg = test['alert_config']
            print(f"Testando [{test['expected']}] {test['filename']} ({alert_cfg['id']})...")

            # Enviar alert_config com critérios reais
            alert_to_send = {
                'id': alert_cfg['id'],
                'label': alert_cfg['label'],
                'context': alert_cfg['context'],
                'criteria': alert_cfg['criteria'],
            }

            data = {
                'alert_json': json.dumps(alert_to_send),
                'operator_name': 'Auditor Benchmark',
                'sector_id': test['sector_id']
            }

            try:
                with open(test['path'], 'rb') as f:
                    res = session.post(API_URL, data=data, files={'file': ('audio.wav', f, 'audio/wav')})

                if res.status_code == 200:
                    audit = res.json()
                    score = audit.get('score', 0)
                    max_score = audit.get('maxPossibleScore', 100)
                    summary = audit.get('summary', '')

                    # Calcular porcentagem real
                    pct = round((score / max_score * 100) if max_score > 0 else 0, 1)
                    ia_verdict = "BOM" if pct >= 70 else "RUIM"
                    success = (ia_verdict == test['expected'])

                    results["total"] += 1
                    if success:
                        results["success"] += 1
                    else:
                        results["failed"] += 1

                    status_str = "SUCCESS" if success else "FAILED"
                    log.write(f"[{status_str}] Expected: {test['expected']} | IA: {ia_verdict} (Score: {score}/{max_score} = {pct}%)\n")
                    log.write(f"Alert: {alert_cfg['id']} | Sector: {test['sector_id']}\n")
                    log.write(f"File: {test['path']}\n")
                    log.write(f"Summary: {summary}\n")

                    # Log details for failures
                    if not success:
                        details = audit.get('details', [])
                        for d in details:
                            if d.get('status') in ('fail', 'partial'):
                                log.write(f"  >> [{d['status'].upper()}] {d.get('label', d.get('criterionId', '?'))}: {d.get('comment', '')}\n")

                    log.write("-" * 60 + "\n")
                    print(f"  {status_str} (Nota: {score}/{max_score} = {pct}%)")
                else:
                    print(f"  ERROR {res.status_code}")
                    log.write(f"ERROR {res.status_code} | File: {test['filename']}\n")
                    results["total"] += 1
                    results["failed"] += 1
            except Exception as e:
                print(f"  FAILURE: {e}")
                log.write(f"FAILURE | File: {test['filename']} | Error: {e}\n")
                results["total"] += 1
                results["failed"] += 1

        # Resumo final
        log.write("\n" + "=" * 60 + "\n")
        log.write(f"TOTAL: {results['total']} | SUCCESS: {results['success']} | FAILED: {results['failed']}\n")
        accuracy = round((results['success'] / results['total'] * 100) if results['total'] > 0 else 0, 1)
        log.write(f"ACCURACY: {accuracy}%\n")

    print(f"\nResultado: {results['success']}/{results['total']} ({accuracy}%)")
    print(f"Relatório em: {LOG_FILE}")


if __name__ == "__main__":
    run_benchmark()
