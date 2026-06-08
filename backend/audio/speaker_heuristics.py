import re
import unicodedata
from typing import Tuple

import audio.speaker_constants as constants

_RE_WHITESPACE = re.compile(r"\s+")
_RE_SENHOR_PREFIX = re.compile(r"^(o senhor|a senhora|o sr|a sra)\b")
_RE_PRF = re.compile(r"\bprf\b")
_RE_POLICE_RANKS = re.compile(r"\b(delegad[oa]|sargento|tenente|coronel|guarnicao|viatura)\b")
_RE_DIGITS_SEQUENCE = re.compile(r"^\d+(?:\s+\d+)*\??$")
_RE_SOCIAL_QUESTION_PREFIX = re.compile(r"^(tudo bem|e voce|voce|ta bem|voce ta bem|como voce ta)\b")
_RE_PREV_SOCIAL_QUESTION_PREFIX = re.compile(r"^(tudo bem|e voce|como voce ta|ta bem)\b")
_RE_ALPHA_TOKEN = re.compile(r"[a-z]+")
_RE_CONTEXTUAL_SHORT_RESPONSE = re.compile(r"^(tudo bem(,?\s+e voce)?|e voce)\??$")
_RE_OPERATOR_SOCIAL_SHORT_RESPONSE = re.compile(
    r"^(eu\s+(to|estou)\s+bem(\s+tambem)?|tudo\s+certo(\s+tambem)?)\b"
)
_RE_SHORT_NOISE_DIGITS = re.compile(r"^\d{1,2}$")
_RE_OPENTECH_ALIAS = re.compile(r"\bopen\s+tech\b")

_ALFABETO_FONETICO = {
    "alfa", "bravo", "charlie", "delta", "eco", "faca", "dado", "bola",
    "aguia", "hotel", "india", "julieta", "kilo", "lima", "mike",
    "negativo", "oscar", "papa", "quebec", "romeu", "sierra", "tango",
    "uniforme", "victor", "whisky", "whiskey", "uisque", "xadrez", "yankee", "zulu",
    "oitavo", "nono", "primeiro", "segundo", "terceiro", "quarto", "quinto",
    "sexto", "setimo",
}

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    text = unicodedata.normalize("NFKD", texto)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _RE_WHITESPACE.sub(" ", text.lower().strip())
    text = _RE_OPENTECH_ALIAS.sub("opentech", text)
    return text

def eh_segmento_telefonia(texto_normalizado: str) -> bool:
    texto = (texto_normalizado or "").strip()
    if not texto or len(texto) < 8:
        return False

    strong_hits = sum(1 for marker in constants.TELEPHONY_MARKERS_STRONG if marker in texto)
    soft_hits = sum(1 for marker in constants.TELEPHONY_MARKERS_SOFT if marker in texto)

    if "ligacao receptiva" in texto or "ligacao recebida" in texto:
        return True
    if "bem vindo" in texto and ("digite" in texto or "fique na linha" in texto):
        return True
    if "torre mondelez" in texto and "digite" in texto:
        return True
    if strong_hits >= 2:
        return True
    if strong_hits >= 1 and soft_hits >= 1:
        return True
    return False

def eh_handoff_interlocutor(texto_normalizado: str) -> bool:
    texto = (texto_normalizado or "").strip()
    if not texto:
        return False
    return any(marker in texto for marker in constants.SUPPORT_POINT_HANDOFF_MARKERS)

def eh_pergunta(texto_normalizado: str) -> bool:
    t = (texto_normalizado or "").strip()
    if not t:
        return False

    if t.endswith("?"):
        return True

    if t.startswith(("pode deixar", "pode sim", "consegue sim", "tudo bem", "ta bem", "e voce")):
        return False

    if t.startswith(constants.PERGUNTA_PREFIXOS):
        return True

    return bool(_RE_SENHOR_PREFIX.match(t))

def pontuar_operador(texto_normalizado: str) -> int:
    score = 0
    t = texto_normalizado
    token = t.strip(" .,!?:;")

    if t.startswith(("alo", "boa tarde", "boa noite", "bom dia")): score += 2
    if token in ("cadastro", "monitoramento", "rastreamento", "opentech"): score += 3
    if (
        t.startswith(("estou ligando", "aqui e", "meu nome e", "quem fala aqui e", "eu falo em nome"))
        or any(x in t for x in [" aqui e ", " estou ligando", " meu nome e ", " falo da ", " quem fala aqui e ", " eu falo em nome "])
        or "sou da central" in t
        or "trabalho aqui" in t
    ): score += 2
    if t.startswith(("ok", "certo", "perfeito", "entendi")): score += 1
    if t.startswith(("pode", "consegue", "me fala", "me conta", "me diga", "me confirma")): score += 2
    if t.startswith(("qual", "como", "quando", "onde", "confirma")): score += 2
    if t.startswith(("informar", "vamos", "agora a gente")): score += 2
    if any(x in t for x in ["vamos comecar", "pode comecar", "seu relato", "as perguntas que eu fizer"]): score += 2
    if any(x in t for x in constants.OPERADOR_FRASES_SUPORTE): score += 2
    if any(x in t for x in constants.OPERADOR_FRASES_MUITO_FORTES): score += 2
    if any(x in t for x in constants.OPERADOR_FRASES_POLICIA): score += 3
    # Frases institucionais (operador usa "eu"/"a gente" em contexto de trabalho)
    if any(x in t for x in constants.OPERADOR_FRASES_INSTITUCIONAIS): score += 4
    if "o senhor" in t or "a senhora" in t: score += 2
    if any(x in t for x in ["cpf", "placa", "sinistro", "ocorrencia", "roteiro"]): score += 1

    return score

def tem_indicador_policial(texto_normalizado: str) -> bool:
    t = texto_normalizado
    return (
        bool(_RE_PRF.search(t))
        or "policia militar" in t
        or "policia civil" in t
        or bool(_RE_POLICE_RANKS.search(t))
    )

def pontuar_motorista(texto_normalizado: str) -> int:
    score = 0
    t = texto_normalizado

    # Verificar se há linguagem institucional — se sim, NÃO pontuar como motorista
    tem_institucional = any(x in t for x in constants.OPERADOR_FRASES_INSTITUCIONAIS)

    if t.startswith(("sim", "nao", "isso", "exato")): score += 2
    if any(x in t for x in ["tudo bem", "gracas a deus", "aham", "uhum"]): score += 2
    if any(x in t for x in ["ponto de apoio", "posto de apoio", "portaria", "recepcao", "patio", "balanca"]): score += 4
    if tem_indicador_policial(t): score += 4
    if _RE_DIGITS_SEQUENCE.match(t): score += 2
    # "eu"/"a gente" só conta como motorista se NÃO for contexto institucional
    if not tem_institucional:
        if t.startswith(("eu ", "a gente", "nos ", "meu ", "minha ")): score += 2
        if any(x in t for x in [" eu ", " fui ", " estava ", " tava ", "aconteceu"]): score += 1
    if t.startswith(("foi", "e ", "era")): score += 1
    if "fui abordado" in t or "sai" in t: score += 2
    # Logistics-specific driver indicators
    if not tem_institucional:
        if any(x in t for x in [
            "to parado aqui",
            "estou parado aqui",
            "to esperando",
            "estou esperando",
            "to aguardando",
            "estou aguardando",
            "to na fila",
            "estou na fila",
            "to carregando",
            "to descarregando",
            "estou descarregando",
            "fazer a descarga",
            "aguardando descarga",
            "to no cliente",
            "estou no cliente",
            "cheguei agora",
            "acabei de chegar",
            "ja entreguei",
            "ja descarreguei",
            "to voltando",
            "estou voltando",
            "to na estrada",
            "estou na estrada",
            "perdi o sinal",
            "nao sei o que aconteceu",
            "nao sei porque",
            "deu problema",
        ]): score += 3

    return score

def eh_pergunta_ou_direcionamento_operador(texto_normalizado: str) -> bool:
    t = texto_normalizado
    prefixes = constants.PERGUNTA_PREFIXOS

    if t.startswith(("pode deixar", "pode sim", "consegue sim")):
        return False

    if t.startswith(prefixes) or "o senhor" in t or "a senhora" in t:
        return True

    if not eh_pergunta(t):
        return False

    # Perguntas sociais curtas tendem a vir do interlocutor como resposta,
    # não como condução do operador.
    if _RE_SOCIAL_QUESTION_PREFIX.match(t):
        return False

    score_op = pontuar_operador(t)
    score_mot = pontuar_motorista(t)
    return score_op >= score_mot + 1

def inferir_speaker_sem_diarizacao(
    texto_normalizado: str,
    score_op: int,
    score_mot: int,
    ultimo_speaker: str,
    aguardando_resposta: bool,
    ultimo_texto_normalizado: str,
    operator_label: str,
    driver_label: str,
) -> Tuple[str, bool]:
    eh_direcionamento = eh_pergunta_ou_direcionamento_operador(texto_normalizado)
    indicador_op_forte = tem_indicador_operador_forte(texto_normalizado)
    indicador_mot = (
        eh_resposta_curta_motorista(texto_normalizado)
        or eh_resposta_curta_interlocutor_contextual(texto_normalizado)
        or tem_indicador_motorista_forte(texto_normalizado)
        or eh_ditado_alfanumerico(texto_normalizado)
    )
    resposta_social_operador = eh_resposta_social_curta_operador(texto_normalizado)
    prev_t = (ultimo_texto_normalizado or "").strip()
    prev_pergunta_social = bool(
        _RE_PREV_SOCIAL_QUESTION_PREFIX.match(prev_t)
        and eh_pergunta(prev_t)
    )

    if ultimo_speaker == driver_label and prev_pergunta_social and resposta_social_operador:
        return operator_label, False

    if eh_direcionamento and score_op >= score_mot:
        return operator_label, True

    if aguardando_resposta:
        if indicador_mot and not indicador_op_forte:
            return driver_label, False
        if score_mot >= score_op + 1 and not indicador_op_forte:
            return driver_label, False
        if indicador_op_forte and score_op >= score_mot:
            return operator_label, True
        if ultimo_speaker == operator_label:
            return driver_label, False
        return ultimo_speaker, False

    if ultimo_speaker == operator_label:
        if indicador_mot and not indicador_op_forte:
            return driver_label, False
        if score_mot >= score_op + 1 and not indicador_op_forte:
            return driver_label, False
        return operator_label, eh_direcionamento

    if indicador_op_forte and score_op >= score_mot:
        return operator_label, eh_direcionamento
    if score_op >= score_mot + 2:
        return operator_label, eh_direcionamento
    return driver_label, False

def eh_resposta_curta_motorista(texto_normalizado: str) -> bool:
    if _RE_DIGITS_SEQUENCE.match(texto_normalizado):
        return True
    if len(texto_normalizado) > 24:
        return False

    return texto_normalizado.startswith(("sim", "nao", "isso", "exato", "certo", "aham", "uhum", "tudo bem", "pode deixar", "consegue sim", "pode sim"))

def eh_ditado_alfanumerico(texto_normalizado: str) -> bool:
    """Detecta quando alguém está ditando placa/código letra por letra (faca, dado, bola, etc.)."""
    tokens = _RE_ALPHA_TOKEN.findall(texto_normalizado)
    if not tokens:
        return False
    matches = sum(1 for t in tokens if t in _ALFABETO_FONETICO or len(t) == 1)
    return matches >= 2 and matches / len(tokens) >= 0.4

def tem_intro_operador(texto_normalizado: str) -> bool:
    t = texto_normalizado
    return (t.startswith(("aqui e", "meu nome e", "estou ligando", "falo da", "quem fala aqui e", "eu falo em nome")) or
            any(x in t for x in [" aqui e ", " estou ligando", " meu nome e ", " falo da ", " quem fala aqui e ", " eu falo em nome "]) or
            "sou da central" in t)

def tem_indicador_operador_forte(texto_normalizado: str) -> bool:
    t = texto_normalizado
    token = t.strip(" .,!?:;")
    return (t.startswith(("estou ligando", "aqui e", "meu nome e", "vamos ", "agora ", "me confirma", "quem fala aqui e", "eu falo em nome")) or
            any(x in t for x in [" aqui e ", " estou ligando", " meu nome e ", " falo da ", " quem fala aqui e ", " eu falo em nome "]) or
            any(x in t for x in constants.OPERADOR_FRASES_SUPORTE) or
            any(x in t for x in constants.OPERADOR_FRASES_POLICIA) or
            any(x in t for x in constants.OPERADOR_FRASES_INSTITUCIONAIS) or
            token in ("cadastro", "monitoramento", "rastreamento", "opentech") or
            "sou da central" in t or "o senhor" in t or "a senhora" in t)

def tem_indicador_motorista_forte(texto_normalizado: str) -> bool:
    t = texto_normalizado
    return (
        t.startswith(("eu ", "meu ", "minha ", "a gente ", "sim", "nao"))
        or any(x in t for x in [" eu ", " fui ", " estava ", "aconteceu"])
        or tem_indicador_policial(t)
    )

def eh_resposta_curta_operador(texto_normalizado: str) -> bool:
    t = texto_normalizado
    return (
        len(t) <= 28 and t.startswith(constants.RESPOSTAS_CURTAS_OPERADOR)
    )

def eh_resposta_curta_interlocutor_contextual(texto_normalizado: str) -> bool:
    t = texto_normalizado
    if len(t) > 32:
        return False
    if t.startswith(constants.RESPOSTAS_CURTAS_INTERLOCUTOR):
        return True
    return bool(_RE_CONTEXTUAL_SHORT_RESPONSE.match(t))

def eh_resposta_social_curta_operador(texto_normalizado: str) -> bool:
    t = texto_normalizado
    return bool(_RE_OPERATOR_SOCIAL_SHORT_RESPONSE.match(t)) and len(t) <= 40

def eh_token_ruido_curto(token: str) -> bool:
    if _RE_SHORT_NOISE_DIGITS.match(token):
        return True
    return token in ["um", "uh", "hm", "hmm", "ah", "ha", "a"]
