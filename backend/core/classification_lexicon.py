"""Léxico de sinais da triagem (dados puros, sem lógica).

Keywords ponderadas e conjuntos de alert_ids usados pelos guardrails
determinísticos de `core.classification` (temperatura, parada×desvio,
hierarquia de alertas, manutenção). Movido sem mudança de comportamento.
"""

# ── Léxico de sinais (keywords ponderadas dos guardrails determinísticos) ───
# Pesos maiores = evidência mais forte. Os guardrails somam ocorrências na
# transcrição (e, com peso menor, no nome do arquivo) para decidir correções.

TEMPERATURE_KEYWORDS = (
    "temperatura",
    "setpoint",
    "set point",
    "termografo",
    "termometro",
    "refrigerado",
    "refrigerada",
    "refrigeracao",
    "bau refrigerado",
    "controle de temperatura",
    "desligamento de temperatura",
)

TEMPERATURE_OFF_KEYWORDS = (
    "desligamento de temperatura",
    "temperatura desligada",
    "desligou a temperatura",
    "temperatura foi desligada",
    "desligar a temperatura",
)

DRIVER_CUES = ("motorista", "condutor", "caminhoneiro", "carreteiro")
CLIENT_CUES = ("cliente", "destinatario", "recebedor", "embarcador")

TEMPERATURE_ALERTS_BY_CONTEXT = {
    "driver_control": ("LOGISTICA-TEMPERATURA-MOT", "Temperatura - Motorista"),
    "driver_shutdown": ("LOGISTICA-DESLIG-TEMP-MOT", "Desligamento Temperatura - Motorista"),
    "client_control": ("LOGISTICA-TEMPERATURA-CLI", "Temperatura - Cliente"),
    "client_shutdown": ("LOGISTICA-DESLIG-TEMP-CLI", "Desligamento Temperatura - Cliente"),
}

TEMPERATURE_ALERT_IDS = {"LOGISTICA-TEMPERATURA-MOT", "LOGISTICA-TEMPERATURA-CLI", "LOGISTICA-DESLIG-TEMP-MOT", "LOGISTICA-DESLIG-TEMP-CLI"}

PARADA_DESVIO_ALERT_IDS = {
    "LOGISTICA-PARADA",
    "LOGISTICA-DESVIO",
    "LOGISTICA-PARADA-EXCESSIVA-MOT",
    "LOGISTICA-PARADA-EXCESSIVA-CLI",
    "UTI-PARADA-MOT",
    "UTI-DESVIO-MOT",
    "UTI-PARADA-CLI",
    "UTI-DESVIO-CLI",
    "TRANSFERENCIA-PARADA-MOT",
    "TRANSFERENCIA-DESVIO-MOT",
    "TRANSFERENCIA-PARADA-CLI",
    "TRANSFERENCIA-DESVIO-CLI",
    "DISTRIBUICAO-PARADA-MOT",
    "DISTRIBUICAO-DESVIO-MOT",
    "DISTRIBUICAO-PARADA-CLI",
    "DISTRIBUICAO-DESVIO-CLI",
    "FENIX-PARADA-MOT",
    "FENIX-DESVIO-MOT",
    "FENIX-PARADA-CLI",
    "FENIX-DESVIO-CLI",
}

POSITION_SIGNAL_WEIGHTS = {
    "posicao em atraso": 5,
    "perda de posicao": 5,
    "perda de sinal": 5,
    "sem sinal": 4,
    "sem posicao": 4,
    "perdeu posicao": 4,
    "forcar posicionamento": 4,
    "posicionamento": 2,
}

PRIORITY_SIGNAL_WEIGHTS = {
    "painel violado": 5,
    "violacao de painel": 5,
    "botao de panico": 5,
    "sensor de desengate": 5,
    "desengate": 4,
    "violacao": 3,
    "violacoes": 3,
    "bau violado": 5,
    "violacao de bau": 5,
    "porta do bau": 3,
    "bau aberto": 4,
}

POLICE_SIGNAL_WEIGHTS = {
    "acionamento policial": 6,
    "contato com a policia": 6,
    "contato com policia": 6,
    "viatura": 4,
    "patrulhamento": 4,
    "prf": 4,
    "policia": 3,
    "policial": 3,
}

PARADA_SIGNAL_WEIGHTS = {
    "parada excessiva": 5,
    "parada indevida": 4,
    "parada": 3,
    "parado": 2,
    "parou": 2,
    "ficou parado": 3,
    "permaneceu parado": 3,
}

DESVIO_SIGNAL_WEIGHTS = {
    "desvio de rota": 4,
    "fora da rota": 4,
    "fora de rota": 4,
    "fora rota": 3,
    "desvio": 3,
    "desviou": 3,
    "rota": 1,
}

MAINTENANCE_CONTEXT_KEYWORDS = (
    "manutencao",
    "oficina",
    "conserto",
    "reparo",
    "reparar",
    "arrumar",
    "borracharia",
    "pneu",
    "mecanico",
    "mecanica",
    "guincho",
    "quebrou",
    "quebrado",
    "pane",
)

NON_AUDITABLE_OUTPUT_KEYWORDS = (
    "informativo",
    "nao auditavel",
    "nao auditavel manutencao",
    "nao auditavel informativo",
    "manutencao",
)

STADIA_CONTEXT_KEYWORDS = (
    "doca",
    "carga",
    "descarga",
    "carregamento",
    "descarregamento",
    "no cliente",
    "na cliente",
    "em cliente",
    "no destinatario",
    "na doca",
    "em doca",
)
