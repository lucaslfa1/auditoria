"""Repositorio dos prompts de IA configuraveis em runtime (tabela `ai_prompts`).

Le e atualiza os prompts usados pela transcricao/avaliacao sem precisar de deploy
(editaveis pela tela admin de Prompts). As chaves usam dot-path (ex.:
`audit_system.regra_senha`, `whisper_prompt.<setor>`); `list_prompts` reconstroi a
estrutura aninhada que o codigo cliente espera. Toda escrita registra trilha em
`ai_prompts_audit_log` e permite restaurar um estado anterior do log.

Cache: mantem um cache de modulo (`_PROMPTS_CACHE`) populado sob demanda no
primeiro `get_prompt`/`list_prompts`, para nao bater no banco a cada requisicao;
`update_prompt` e `invalidate_ai_prompts_cache` o invalidam.

Sem custo de API de IA aqui (apenas acesso a banco) — este modulo so guarda/serve
o TEXTO dos prompts; o custo ocorre quando a transcricao/avaliacao os envia a Azure.
"""
import json
import logging
from typing import Any, Callable, Dict, List, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# O cache_utils no backend tem ferramentas para invalidar caches locais.
# Vamos criar um cache no proprio repository para evitar bater no banco em cada requisicao.

_PROMPTS_CACHE: Dict[str, Any] = {}
_PROMPTS_CACHE_POPULATED = False


def invalidate_ai_prompts_cache() -> None:
    """Limpa o cache de modulo de prompts, forcando recarga do DB na proxima leitura.

    Sem acesso a banco; apenas zera o estado em memoria.
    """
    global _PROMPTS_CACHE_POPULATED
    _PROMPTS_CACHE.clear()
    _PROMPTS_CACHE_POPULATED = False
    logger.info("Cache de ai_prompts invalidado.")


def _ensure_cache_populated(get_connection: Callable) -> None:
    global _PROMPTS_CACHE_POPULATED
    if _PROMPTS_CACHE_POPULATED:
        return

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT chave, valor FROM ai_prompts")
        _PROMPTS_CACHE.clear()
        for row in cursor.fetchall():
            chave, valor = row
            _PROMPTS_CACHE[chave] = valor
        _PROMPTS_CACHE_POPULATED = True
    except Exception:
        logger.exception("Erro ao popular cache de ai_prompts")
    finally:
        conn.close()


def get_prompt(get_connection: Callable, chave: str, default: Any = None) -> Any:
    """Retorna o valor do prompt de dot-path `chave`, ou `default` se inexistente.

    Popula o cache de modulo no primeiro uso (le `ai_prompts` via `get_connection`,
    que e uma callable que devolve uma conexao). Leituras subsequentes vem do cache.
    """
    _ensure_cache_populated(get_connection)
    return _PROMPTS_CACHE.get(chave, default)


def get_whisper_prompt_for_sector(
    get_connection: Callable,
    sector_id: Optional[str],
    default: str = "",
) -> str:
    """Resolve o prompt do Whisper para um setor, com cadeia de fallback.

    Tenta nesta ordem, devolvendo o primeiro nao-vazio: `whisper_prompt.<setor>`
    (setor normalizado para minusculas) -> `whisper_prompt.default` ->
    `whisper_prompt` (chave legada) -> `default`. So leitura (via cache de prompts).
    """
    normalized_sector = str(sector_id or "").strip().lower()
    if normalized_sector:
        sector_prompt = get_prompt(get_connection, f"whisper_prompt.{normalized_sector}", None)
        if isinstance(sector_prompt, str) and sector_prompt.strip():
            return sector_prompt.strip()

    default_prompt = get_prompt(get_connection, "whisper_prompt.default", None)
    if isinstance(default_prompt, str) and default_prompt.strip():
        return default_prompt.strip()

    legacy_prompt = get_prompt(get_connection, "whisper_prompt", None)
    if isinstance(legacy_prompt, str) and legacy_prompt.strip():
        return legacy_prompt.strip()

    return str(default or "").strip()


def list_prompts(get_connection: Callable) -> Dict[str, Any]:
    """Retorna TODOS os prompts como dicionario aninhado (reconstruido do dot-path).

    Ex.: a chave `audit_system.regra_senha` vira
    `{"audit_system": {"regra_senha": <valor>}}`, formato que o codigo cliente
    espera. Le do cache (populado no primeiro uso via `get_connection`).
    """
    _ensure_cache_populated(get_connection)

    # Reconstrói a estrutura aninhada a partir do dot-path (ex: audit_system.regra_senha)
    # Mas como o código do cliente atual (ex: PROMPTS_CONFIG.get("audit_system", {}).get("regra_senha"))
    # espera a estrutura aninhada, precisamos converter as chaves dot-path para dicionário aninhado.
    
    result = {}
    for chave, valor in _PROMPTS_CACHE.items():
        parts = chave.split('.')
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = valor
    return result


def update_prompt(
    get_connection: Callable,
    chave: str,
    valor: Any,
    alterado_por: str,
    motivo: str,
    origem: str = "ui",
) -> bool:
    """Faz upsert do prompt `chave` com `valor` e registra a mudanca no audit_log.

    Le o estado anterior; se for igual ao novo `valor`, retorna True sem escrever
    (no-op). Senao grava em `ai_prompts` (INSERT ... ON CONFLICT, `valor` como
    JSON), insere em `ai_prompts_audit_log` (acao 'create' ou 'update') na mesma
    transacao, commita e invalida o cache. `alterado_por`/`motivo`/`origem`
    alimentam a trilha. Retorna True em sucesso, False em erro (com rollback).
    Efeito colateral: escreve no DB.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Pega estado anterior
        cursor.execute("SELECT valor FROM ai_prompts WHERE chave = %s", (chave,))
        row = cursor.fetchone()
        payload_antes = row[0] if row else None
        
        acao = "update" if payload_antes is not None else "create"
        
        if payload_antes == valor:
            return True  # Nenhuma mudança real
            
        # Atualiza a tabela principal
        valor_json = json.dumps(valor)
        cursor.execute(
            """
            INSERT INTO ai_prompts (chave, valor, atualizado_em)
            VALUES (%s, %s, NOW())
            ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = NOW()
            """,
            (chave, valor_json)
        )
        
        # Insere no audit log
        cursor.execute(
            """
            INSERT INTO ai_prompts_audit_log
            (acao, entity_id, payload_antes, payload_depois, alterado_por, motivo, origem)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                acao,
                chave,
                json.dumps(payload_antes) if payload_antes is not None else None,
                valor_json,
                alterado_por,
                motivo,
                origem,
            )
        )
        
        conn.commit()
        invalidate_ai_prompts_cache()
        return True
    except Exception:
        logger.exception("Erro ao atualizar ai_prompt: %s", chave)
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def list_audit_log(get_connection: Callable, limit: int = 50, offset: int = 0, entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista o historico de mudancas de prompts (`ai_prompts_audit_log`), recentes primeiro.

    Pagina por `limit`/`offset`; filtra por `entity_id` (a chave do prompt) se
    informado. Read-only; retorna lista de dicts (vazia em erro). Abre e fecha a
    conexao.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, acao, entity_id, payload_antes, payload_depois, alterado_por, alterado_em, motivo, origem
            FROM ai_prompts_audit_log
        """
        params = []
        if entity_id:
            query += " WHERE entity_id = %s"
            params.append(entity_id)
            
        query += " ORDER BY alterado_em DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, tuple(params))
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception:
        logger.exception("Erro ao listar audit_log de ai_prompts")
        return []
    finally:
        conn.close()


def restore_from_audit(
    get_connection: Callable,
    audit_id: int,
    alterado_por: str,
    motivo: str,
) -> bool:
    """Restaura um prompt para o estado ANTERIOR registrado na entrada `audit_id` do log.

    Le `payload_antes` da entrada `ai_prompts_audit_log` e reaplica via
    `update_prompt` (gerando uma nova entrada de log com o motivo prefixado).
    Retorna False se a entrada nao existe ou se `payload_antes` for nulo (caso de
    'create' — nao da para restaurar a "nada"; delete-se o prompt manualmente).
    Efeito colateral: escreve no DB (via update_prompt).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT acao, entity_id, payload_antes FROM ai_prompts_audit_log WHERE id = %s", (audit_id,))
        row = cursor.fetchone()
        if not row:
            return False
            
        _, entity_id, payload_antes = row
        
        if payload_antes is None:
            logger.warning("Nao e possivel restaurar para um estado nulo (create) via este endpoint. Delete o prompt se necessario.")
            return False
            
        conn.close() # close before calling update_prompt
        return update_prompt(
            get_connection=get_connection,
            chave=entity_id,
            valor=payload_antes,
            alterado_por=alterado_por,
            motivo=f"Restore do log id {audit_id}: {motivo}",
            origem="ui",
        )
    except Exception:
        logger.exception("Erro ao restaurar ai_prompt do audit log")
        try:
            conn.close()
        except Exception:
            pass
        return False
