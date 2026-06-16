"""Triagem de ligações por LLM: escolhe quais chamadas valem auditoria.

Papel no fluxo: dado um lote de metadados de chamadas de um setor (já
filtradas por tempo mínimo), pede ao LLM para selecionar as melhores candidatas
a auditoria real e descartar "lixo" (caixa postal, recusa, tabulação genérica).
Chamado pela esteira de automação (`huawei_sync._triagem_grupo`); quando a
triagem LLM não roda (Azure ausente ou orçamento estourado), o caller cai no
fallback determinístico e nada é descartado.

CUSTO DE API: `filtrar_ligacoes_com_llm` faz UMA chamada PAGA ao Azure OpenAI
(chat completions) por lote, contabilizada via `cost_guard.record_call`. É
guardada por `cost_guard.budget_exceeded()` (teto diário) e por checagem das
credenciais Azure (falha fechada = retorna vazio).
"""
import json
import logging
from typing import List, Dict, Any

from core import cost_guard
from core.automation_rules import get_call_duration_seconds, get_call_reason_text
from services import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_DEPLOYMENT
)

logger = logging.getLogger(__name__)


MAX_LLM_CANDIDATES = 10
MAX_LLM_APPROVED_CALLS = 2
LLM_TRIAGE_TIMEOUT_SECONDS = 30.0


def _get_duracao(chamada: Dict[str, Any]) -> int:
    return get_call_duration_seconds(chamada)


def _parse_ids_aprovados(payload: str, total_candidatos: int) -> List[int]:
    """Extrai e valida os IDs aprovados da resposta JSON do LLM.

    Lê a chave `ids_aprovados` do `payload`; aceita só inteiros (descarta bool,
    que é subclasse de int) dentro do intervalo [0, total_candidatos),
    remove duplicatas e limita a `MAX_LLM_APPROVED_CALLS`. Retorna a lista de
    índices válidos (vazia se o JSON for inválido/inesperado).
    """
    dados = json.loads(payload or "{}")
    ids_aprovados = dados.get("ids_aprovados", [])
    if not isinstance(ids_aprovados, list):
        return []

    selecionados: List[int] = []
    for idx in ids_aprovados:
        if type(idx) is not int:  # bool is a subclass of int; keep it out.
            continue
        if idx < 0 or idx >= total_candidatos:
            continue
        if idx in selecionados:
            continue
        selecionados.append(idx)
        if len(selecionados) >= MAX_LLM_APPROVED_CALLS:
            break
    return selecionados


async def filtrar_ligacoes_com_llm(chamadas: List[Dict[str, Any]], setor: str, regra: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Pede ao LLM que selecione as melhores chamadas para auditar.

    Recebe `chamadas` (metadados já filtrados por tempo mínimo), o `setor` e a
    `regra` opcional do setor (cujo `motivos_alvo` vira prioridade no prompt).
    Pré-ordena por duração e considera no máximo `MAX_LLM_CANDIDATES`; o LLM
    devolve até `MAX_LLM_APPROVED_CALLS` IDs aprovados.

    Falha fechada: retorna lista vazia se o Azure OpenAI não estiver
    configurado, se o orçamento diário estiver estourado
    (`cost_guard.budget_exceeded`) ou se qualquer exceção ocorrer — nesses
    casos o caller usa o fallback determinístico.

    CUSTO DE API: faz UMA chamada paga ao Azure OpenAI (chat completions,
    `response_format=json_object`) quando não cai em nenhuma das guardas.
    Efeitos colaterais: logging e `cost_guard.record_call`. Retorna a sublista
    de `chamadas` aprovadas (objetos originais).
    """
    if not chamadas:
        return []

    # Sem Azure configurado, falhe fechado para nao aprovar chamadas ruins automaticamente.
    if not AZURE_OPENAI_KEY or not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_DEPLOYMENT:
        logger.warning("Azure OpenAI triage not configured. Nenhuma chamada sera aprovada pela triagem LLM.")
        return []

    # Guardrail de orcamento: com teto diario atingido, retorna vazio e o
    # caller (huawei_sync._triagem_grupo) cai no _triagem_fallback
    # deterministico — pipeline segue sem gastar LLM, nada e descartado.
    motivo_bloqueio = cost_guard.budget_exceeded()
    if motivo_bloqueio:
        logger.warning(
            "Triagem LLM pulada (%s). Setor '%s' segue via fallback deterministico.",
            motivo_bloqueio, setor,
        )
        return []

    # Pre-Filtro de Relevancia: Ordenar as chamadas pela duracao (maior para menor)
    # e pegar as top 10 para nao sobrecarregar o LLM
    chamadas_ordenadas = sorted(chamadas, key=_get_duracao, reverse=True)[:MAX_LLM_CANDIDATES]

    # 1. Preparamos os dados para o LLM
    lista_simplificada = []
    for idx, c in enumerate(chamadas_ordenadas):
        reason_text = get_call_reason_text(c)
        reason_code = str(c.get("callReasonCode") or c.get("leaveReason") or "").strip()
        lista_simplificada.append({
            "id_interno": idx,
            "duracao_segundos": get_call_duration_seconds(c),
            "motivo_tabulacao": reason_text or (f"leaveReason={reason_code}" if reason_code else None),
            "data_hora": c.get("beginTime")
        })

    # Extrair palavras-chave do setor se existirem
    regras_alvo = ""
    if regra and regra.get("motivos_alvo"):
        motivos = ", ".join(regra["motivos_alvo"])
        regras_alvo = f"\n    ATENCAO ESPECIAL (Regra de Negocio do Setor): Dê prioridade maxima para ligacoes cuja tabulacao contenha as seguintes palavras ou sinônimos: {motivos}\n"

    prompt_sistema = f"""
    Voce eh um especialista em controle de qualidade de call center do setor '{setor}'.
    Sua tarefa eh analisar a lista de ligacoes abaixo (em JSON) e escolher APENAS as 2 ligacoes 
    com MAIOR probabilidade de conterem uma conversa real e util entre o operador e o cliente.
{regras_alvo}
    Regras para descartar ligacoes (LIXO):
    - Tabulacoes muito genericas cruzadas com tempos baixos.
    - Sinais de que foi caixa postal ou recusa de atendimento.
    
    Regras para escolher ligacoes (BOAS):
    - Tempos de ligacao compativeis com tratativas reais (ex: mais de 2 minutos).
    - Motivos de tabulacao especificos e detalhados.

    Retorne APENAS um objeto JSON com a chave "ids_aprovados" contendo os `id_interno` das 2 melhores ligacoes em um array.
    Exemplo: {{"ids_aprovados": [0, 3]}}
    Se apenas 1 for boa, retorne o array com 1 id. Exemplo: {{"ids_aprovados": [2]}}
    Se todas forem lixo, retorne array vazio. Exemplo: {{"ids_aprovados": []}}
    """

    prompt_usuario = json.dumps(lista_simplificada, indent=2)

    logger.info(f"Enviando {len(chamadas_ordenadas)} chamadas do setor '{setor}' para triagem do LLM...")

    try:
        from openai import AsyncAzureOpenAI
        client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version="2025-01-01-preview",
            timeout=LLM_TRIAGE_TIMEOUT_SECONDS,
        )

        cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "triagem_llm")
        response = await client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": prompt_usuario}
            ],
            temperature=0,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        
        resposta_texto = response.choices[0].message.content
        logger.debug(f"Resposta LLM na triagem: {resposta_texto}")

        ids_aprovados = _parse_ids_aprovados(resposta_texto, len(chamadas_ordenadas))

        chamadas_aprovadas = []
        for idx in ids_aprovados:
            chamadas_aprovadas.append(chamadas_ordenadas[idx])
                
        logger.info(f"O LLM aprovou {len(chamadas_aprovadas)} chamadas para auditoria real.")
        return chamadas_aprovadas

    except Exception:
        logger.exception("Erro na triagem com LLM.")
        return []
