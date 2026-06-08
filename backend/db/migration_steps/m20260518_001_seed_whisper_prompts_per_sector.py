"""Seed prompts Whisper por setor.

Os prompts ficam em ai_prompts para permitir ajuste operacional sem deploy.
ON CONFLICT DO NOTHING preserva qualquer prompt ja customizado no ambiente.
"""

import json


MIGRATION_NAME = "m20260518_001_seed_whisper_prompts_per_sector"


DEFAULT_PROMPT = (
    "Opentech, nstech, BAS, motorista, placa, Mondelez, Unilever, Buonny, "
    "Sascar, Tracker, Onix, Autotrac, Omnilink, Ravex, isca, CPF, AE, "
    "[Inaudivel]."
)


SECTOR_PROMPTS = {
    "bas": (
        f"{DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "gerenciamento de risco, rastreamento, motorista em movimento."
    ),
    "bbm": (
        f"{DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "gerenciamento de risco, rastreamento, motorista em movimento."
    ),
    "distribuicao": (
        f"{DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "distribuicao, rastreamento, motorista em movimento."
    ),
    "fenix": (
        f"{DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "Fenix, rastreamento, motorista em movimento."
    ),
    "rastreamento": (
        f"{DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "rastreamento, gerenciamento de risco, motorista em movimento."
    ),
    "transferencia": (
        f"{DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "transferencia, rastreamento, motorista em movimento."
    ),
    "uti": (
        f"{DEFAULT_PROMPT} Senha de seguranca, CPF, AE, origem, destino, "
        "UTI, rastreamento, motorista em movimento."
    ),
    "cadastro": (
        f"{DEFAULT_PROMPT} Cadastro, condutor, CPF, RG, CNH, carregamento, "
        "bloqueio, reprovado, transportadora."
    ),
    "mondelez": (
        f"{DEFAULT_PROMPT} Mondelez, cadastro, condutor, CPF, RG, CNH, "
        "carregamento, bem-vindo a Mondelez."
    ),
    "logistica": (
        f"{DEFAULT_PROMPT} Logistica, parada, desvio, ponto de apoio, origem, "
        "destino, temperatura, entrega, canhoto."
    ),
    "logistica_unilever": (
        f"{DEFAULT_PROMPT} Unilever, logistica, parada, desvio, ponto de apoio, "
        "origem, destino, temperatura, entrega."
    ),
    "operacao_taborda": (
        f"{DEFAULT_PROMPT} Taborda, logistica, parada, desvio, ponto de apoio, "
        "origem, destino, entrega."
    ),
    "checklist": (
        f"{DEFAULT_PROMPT} Checklist, vistoria, placa, carreta, cavalo, condutor, "
        "documento, liberacao."
    ),
    "celula_atendimento": (
        f"{DEFAULT_PROMPT} Celula de atendimento, motorista, placa, protocolo, "
        "acionamento, tratativa."
    ),
}


def apply(c):
    rows = [("whisper_prompt.default", DEFAULT_PROMPT)]
    rows.extend((f"whisper_prompt.{sector}", prompt) for sector, prompt in SECTOR_PROMPTS.items())

    c.executemany(
        """
        INSERT INTO ai_prompts (chave, valor)
        VALUES (%s, %s::jsonb)
        ON CONFLICT DO NOTHING
        """,
        [(key, json.dumps(value, ensure_ascii=False)) for key, value in rows],
    )
