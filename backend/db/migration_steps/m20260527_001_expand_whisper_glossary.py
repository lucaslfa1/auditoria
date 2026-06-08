"""Expand whisper prompts with GR Glossary terms.

Update the existing prompts using the new DEFAULT_PROMPT containing 
risk management (GR) and trucking specific terms.
"""

import json


MIGRATION_NAME = "m20260527_001_expand_whisper_glossary"


NEW_DEFAULT_PROMPT = (
    "Opentech, nstech, BAS, motorista, placa, Mondelez, Unilever, Buonny, "
    "Sascar, Tracker, Onix, Autotrac, Omnilink, Ravex, isca, CPF, AE, "
    "Posto Décio, Graal, Arco-Íris, Aldo, Sakamoto, QRA, QAP, Chapa, "
    "Cavalo, Bitrem, Sider, Baú, Quinta Roda, Pino Rei, Romaneio, CTE, "
    "Macro, Pernoite, Jammer, Chupa-Cabra, Trava de Baú, Botão de Pânico, "
    "Desengate, Pronta Resposta, Escolta, PRF, Viatura, VTR, UOP, 191, "
    "B.O., B.A.T., Thermo King, Carrier, Setpoint, Datalogger, Degelo, "
    "Frigorífico, JSL, Braspress, Tegma, Jadlog, TNT, Sequoia, Rodonaves, "
    "Patrus, Loggi, JBS, Friboi, BRF, Seara, Marfrig, Minerva, Aurora, "
    "Pamplona, Frimesa, Copacol, Complexo do Alemão, Maré, Jacarezinho, "
    "Chapadão, Pedreira, Vila Kennedy, Cidade de Deus, Rocinha, "
    "Avenida Brasil, Linha Vermelha, Linha Amarela, Arco Metropolitano, "
    "Baixada Fluminense, CV, Comando Vermelho, TCP, Terceiro Comando Puro, "
    "ADA, Milícia, Bonde, Caveirão, VUC, Toco, Truck, Bitruck, "
    "Cavalo Mecânico, Carreta LS, Vanderléia, Treminhão, Rodotrem, "
    "Carga Seca, Perecível, Carga Perigosa, Granel, Carga Fracionada, "
    "Lotação, BR-116, Via Dutra, Régis Bittencourt, BR-101, Rio-Santos, "
    "BR-381, Fernão Dias, BR-153, BR-040, Washington Luís, BR-277, BR-163, "
    "Bandeirantes, Anhanguera, Castello Branco, URA, Protocolo, SLA, "
    "Triagem, Transferência, Monitoramento, Espelho de Carga, Liberação, "
    "Inteligência Embarcada, Área de Risco, Centro de Distribuição, "
    "Carga de Distribuição, Carga de Transferência, Cerca Eletrônica, "
    "Ajudante, Conhecimento de Transporte, EADI, Aduana, Escolta Armada, "
    "Comboio, Tecnologias, Sighra, T4S, 3S, Maxtrack, OBC, Atuadores, "
    "Bloqueio, Sensores, Carreta, GPS, Manifesto, Seguro, Embarcador, "
    "Corretora, Seguradora, Reguladora, PR, Cliente, Transportadora, "
    "Funcionário, Agregado, Terceiro, Isca, 2º Localizador, Ponto de Apoio, "
    "Posto Avançado, P.A, [Inaudivel]."
)


SECTOR_PROMPTS = {
    "bas": (
        f"{NEW_DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "gerenciamento de risco, rastreamento, motorista em movimento."
    ),
    "bbm": (
        f"{NEW_DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "gerenciamento de risco, rastreamento, motorista em movimento."
    ),
    "distribuicao": (
        f"{NEW_DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "distribuicao, rastreamento, motorista em movimento."
    ),
    "fenix": (
        f"{NEW_DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "Fenix, rastreamento, motorista em movimento."
    ),
    "rastreamento": (
        f"{NEW_DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "rastreamento, gerenciamento de risco, motorista em movimento."
    ),
    "transferencia": (
        f"{NEW_DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "transferencia, rastreamento, motorista em movimento."
    ),
    "uti": (
        f"{NEW_DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "UTI, rastreamento, motorista em movimento."
    ),
    "cadastro": (
        f"{NEW_DEFAULT_PROMPT} Cadastro, condutor, CPF, RG, CNH, carregamento, "
        "bloqueio, reprovado, transportadora."
    ),
    "mondelez": (
        f"{NEW_DEFAULT_PROMPT} Mondelez, cadastro, condutor, CPF, RG, CNH, "
        "carregamento, bem-vindo a Mondelez."
    ),
    "logistica": (
        f"{NEW_DEFAULT_PROMPT} Logistica, parada, desvio, ponto de apoio, origem, "
        "destino, temperatura, entrega, canhoto."
    ),
    "logistica_unilever": (
        f"{NEW_DEFAULT_PROMPT} Unilever, logistica, parada, desvio, ponto de apoio, "
        "origem, destino, temperatura, entrega."
    ),
    "operacao_taborda": (
        f"{NEW_DEFAULT_PROMPT} Taborda, logistica, parada, desvio, ponto de apoio, "
        "origem, destino, entrega."
    ),
    "checklist": (
        f"{NEW_DEFAULT_PROMPT} Checklist, vistoria, placa, carreta, cavalo, condutor, "
        "documento, liberacao."
    ),
    "celula_atendimento": (
        f"{NEW_DEFAULT_PROMPT} Celula de atendimento, motorista, placa, protocolo, "
        "acionamento, tratativa."
    ),
}


def apply(c):
    rows = [("whisper_prompt.default", NEW_DEFAULT_PROMPT)]
    rows.extend((f"whisper_prompt.{sector}", prompt) for sector, prompt in SECTOR_PROMPTS.items())

    c.executemany(
        """
        INSERT INTO ai_prompts (chave, valor)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor
        """,
        [(key, json.dumps(value, ensure_ascii=False)) for key, value in rows],
    )
