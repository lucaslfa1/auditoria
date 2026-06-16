"""Parser de JSON tolerante a falhas, com reparo local e via LLM.

Extraído de `core.evaluation` para legibilidade e para deduplicar a dependência:
`parse_json_with_repair` já era importado também por `core.transcription` e
`core.summary_regeneration`. `core.evaluation` reexporta `parse_json_with_repair`
(compat: `from core.evaluation import parse_json_with_repair` segue funcionando).

Estratégia de `parse_json_with_repair`:
1. `json.loads` direto;
2. reparo LOCAL determinístico (`_iter_local_json_candidates` /
   `_try_parse_json_locally`): remove cercas markdown e extrai o primeiro
   objeto/array balanceado do texto;
3. reparo via LLM (Azure OpenAI ou cliente primário) até `max_attempts`.
Cada transição é registrada por `_log_json_repair_event`.
"""
import json
import logging
import re
from typing import Any, Optional

from core.config import (
    AI_MODEL,
    AI_PROVIDER_PRIORITY,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    ai_client,
)

logger = logging.getLogger(__name__)


def _log_json_repair_event(
    *,
    event: str,
    attempt: int,
    provider: str,
    schema_hint: str,
    text,
    error=None,
) -> None:
    payload = {
        "event": event,
        "attempt": attempt,
        "provider": provider,
        "schema_hint": str(schema_hint or "")[:160],
        "text_length": len(text or ""),
    }
    if error is not None:
        payload["error_type"] = error.__class__.__name__
        payload["error_message"] = str(error)[:240]
    logger.info(
        "[evaluation-json-repair] %s",
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )


def _iter_local_json_candidates(raw_text: str):
    text = str(raw_text or "").strip()
    if not text:
        return

    seen: set[str] = set()

    def emit(candidate: str):
        candidate = str(candidate or "").strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            yield candidate

    yield from emit(text)

    if text.startswith("```"):
        stripped = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```\s*$", "", stripped)
        yield from emit(stripped)

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            _, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        yield from emit(text[index : index + end])
        break


def _try_parse_json_locally(raw_text: str) -> tuple[bool, Any]:
    last_error: Optional[Exception] = None
    for candidate in _iter_local_json_candidates(raw_text):
        try:
            return True, json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        _log_json_repair_event(
            event="local_repair_failed",
            attempt=0,
            provider="local",
            schema_hint="",
            text=raw_text,
            error=last_error,
        )
    return False, None


def _build_azure_json_repair_client(endpoint: str, api_key: str) -> Any:
    from openai import AzureOpenAI

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2025-01-01-preview",
        timeout=180.0,
    )


def parse_json_with_repair(
    raw_text: str,
    schema_hint: str,
    max_attempts: int = 2,
    *,
    azure_client: Any = None,
    primary_ai_client: Any = None,
    ai_provider_priority: Optional[str] = None,
    azure_openai_key: Optional[str] = None,
    azure_openai_endpoint: Optional[str] = None,
    azure_openai_deployment: Optional[str] = None,
    ai_model: Optional[str] = None,
    generation_config: Any = None,
) -> Any:
    """Faz parse de JSON tolerante a falhas, reparando local ou via LLM.

    Tenta em ordem: (1) `json.loads` direto; (2) reparo LOCAL determinístico
    (remove cercas markdown e extrai o primeiro objeto/array balanceado); (3)
    reparo via LLM até `max_attempts`, enviando o texto + `schema_hint` para o
    modelo corrigir. A rota de reparo LLM é Azure OpenAI quando
    `ai_provider_priority == "azure"` e há key/endpoint; caso contrário usa o
    cliente primário (`ai_client`/Gemini). Os parâmetros nomeados permitem
    injetar clientes/config (útil em testes); quando None, caem nos defaults de
    `core.config`.

    CUSTO DE API: o passo (3) faz chamadas PAGAS (Azure OpenAI ou cliente
    primário) — uma por tentativa de reparo, contabilizada via
    `cost_guard.record_call`. Os passos (1) e (2) são gratuitos (CPU). Levanta
    a exceção original se esgotar as tentativas sem JSON válido. Retorna o
    objeto Python já parseado.
    """
    provider_priority = ai_provider_priority or AI_PROVIDER_PRIORITY
    azure_key = AZURE_OPENAI_KEY if azure_openai_key is None else azure_openai_key
    azure_endpoint = AZURE_OPENAI_ENDPOINT if azure_openai_endpoint is None else azure_openai_endpoint
    azure_deployment = azure_openai_deployment or AZURE_OPENAI_DEPLOYMENT
    model_name = ai_model or AI_MODEL
    model_client = primary_ai_client or ai_client
    if generation_config is None:
        from core.config import GENERATION_CONFIG  # lazy: evita google.genai no boot
        effective_generation_config = GENERATION_CONFIG
    else:
        effective_generation_config = generation_config

    attempt = 0
    text = raw_text
    while True:
        try:
            if not text:
                raise ValueError("JSON input is empty or None")
            return json.loads(text)
        except Exception as exc:
            local_ok, parsed = _try_parse_json_locally(text)
            if local_ok:
                _log_json_repair_event(
                    event="local_repair_applied",
                    attempt=attempt,
                    provider="local",
                    schema_hint=schema_hint,
                    text=text,
                    error=exc,
                )
                return parsed

            if attempt >= max_attempts:
                _log_json_repair_event(
                    event="exhausted",
                    attempt=attempt,
                    provider="none",
                    schema_hint=schema_hint,
                    text=text,
                    error=exc,
                )
                raise
            attempt += 1
            use_azure_repair = bool(provider_priority == "azure" and azure_key and azure_endpoint)
            repair_provider = (
                "azure_openai"
                if use_azure_repair
                else "primary_ai"
            )
            _log_json_repair_event(
                event="invalid_json_detected",
                attempt=attempt,
                provider=repair_provider,
                schema_hint=schema_hint,
                text=text,
                error=exc,
            )

            fix_prompt = f"""
            Corrija o JSON para ficar valido e obedecer ao esquema abaixo.
            Responda somente com JSON, sem explicacoes.
            ESQUEMA:
            {schema_hint}
            TEXTO:
            {text}
            """
            # Use Azure OpenAI when the Azure route is selected
            if use_azure_repair:
                from core import cost_guard
                cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "json_repair")
                client = azure_client or _build_azure_json_repair_client(azure_endpoint, azure_key)
                completion = client.chat.completions.create(
                    model=azure_deployment,
                    messages=[{"role": "user", "content": fix_prompt}],
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                text = completion.choices[0].message.content
            else:
                if model_client is None:
                    raise RuntimeError("AI client not configured for JSON repair")
                repaired = model_client.models.generate_content(
                    model=model_name,
                    contents=[fix_prompt],
                    config=effective_generation_config
                )
                text = repaired.text

            _log_json_repair_event(
                event="repair_generated",
                attempt=attempt,
                provider=repair_provider,
                schema_hint=schema_hint,
                text=text,
            )
            # Loop volta ao while True -> json.loads(text) para tentar novamente
