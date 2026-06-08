# Revisao do Fluxo de Auditoria — Transcricoes, Laudos e Contestacao

**Data:** 2026-03-12
**Revisado por:** Claude Opus 4.6
**Foco:** Transcricoes, laudos de analise, envio ao supervisor, botao contestar
**Baseline:** 177 passed, 1 skipped (30.88s)

---

## Sumario executivo

O fluxo principal de auditoria (upload -> transcricao -> avaliacao IA -> laudo) esta
**funcionalmente operacional**. O fluxo de envio ao supervisor e aprovacao funcionam.
O botao de contestacao funciona e a auditoria volta para revisao.

Porem, foram encontrados **bugs reais** que afetam a qualidade dos dados e a robustez:
- Reavaliacao nao persiste no banco (dados perdidos)
- `ai_feedback` perdido ao carregar audit do cache
- Falta mapeamento de setores nos criterios (laudos podem sair vazios)
- Sem validacao de status de origem nas transicoes (supervisor pode burlar revisao via API)
- Formulario de feedback do supervisor esta **desligado** no frontend

| Severidade | Qtd | Area |
|------------|-----|------|
| Alta       |   3 | Transcricao/Laudo: reevaluate nao salva, setores faltando, ai_feedback perdido |
| Media      |   6 | Contestacao: sem guard de status, ValueError nao tratado, campos apagados |
| Baixa      |   8 | Cache mutavel, parse_json_with_repair, details inconsistente, etc. |

---

## FLUXO 1: Transcricao e Laudo de Analise

### Como funciona (trace completo)

```
POST /api/audit (audio + alert JSON)
  -> core/audit.py: process_audit_with_ai()
     -> compute_input_hash() -> check cache
     -> transcribe_audio() (Azure Speech / AssemblyAI / GPT-4o)
     -> build_diarization_quality() -> speaker detection
     -> load_criteria_for_sector() -> carrega criterios JSON
     -> evaluate_with_ai_priority() -> Azure OpenAI / Gemini
        -> get_audit_system_prompt() (injeta setor, regras, operador)
        -> AI retorna JSON com score por criterio
        -> parse_json_with_repair() se JSON malformado
     -> result_from_raw() -> monta AuditResult
  -> background: persist_audit_artifacts() salva no banco
  -> retorna AuditResult ao frontend
```

### Bugs encontrados

#### T1. ALTA — Reavaliacao nao salva no banco
**Arquivo:** `routers/audit.py:139` + `core/audit.py:124`

O endpoint `POST /api/audit/reevaluate` chama `reevaluate_audit()` que retorna um
`AuditResult` mas **nunca chama** `persist_audit_artifacts`. O resultado existe apenas
na resposta HTTP e se perde se o frontend nao salvar manualmente.

O audit original no banco mantem os scores antigos.

**Impacto:** Reevaliacoes sao efemeras. Se o usuario reevaliar uma auditoria e fechar
a pagina, os novos scores sao perdidos.

**Correcao:** Adicionar `persist_audit_artifacts` ao final de `reevaluate_audit`, ou
retornar flag ao frontend indicando que precisa salvar.

---

#### T2. ALTA — `ai_feedback` perdido ao carregar do cache
**Arquivo:** `repositories/common.py:144-156`

`row_to_audit_result()` reconstroi um `AuditResult` a partir do banco mas **nao le**
a coluna `ai_feedback`. O campo e salvo corretamente (linha 246 de `audits.py`) mas
nunca restaurado.

**Impacto:** Qualquer auditoria carregada do cache (deduplicacao por hash) perde o
feedback textual da IA.

**Correcao:** Adicionar `ai_feedback=row.get("ai_feedback")` em `row_to_audit_result`.

---

#### T3. ALTA — Setores faltando no mapeamento de criterios
**Arquivo:** `core/config.py:153-174`

`load_criteria_for_sector()` nao tem mapeamento para:
- `transferencia` (setor valido no SECTOR_RULES)
- `logistica_unilever`
- `operacao_taborda`
- `celula_atendimento`

Se o frontend enviar `sector_id="transferencia"`, os criterios nao sao carregados do
arquivo JSON. A IA avalia sem criterios, produzindo laudo vazio ou generico.

**Correcao:** Adicionar aliases:
```python
"transferencia": "rastreamento",
"logistica_unilever": "logistica",
"operacao_taborda": "logistica",
"celula_atendimento": "distribuicao",
```

---

#### T4. MEDIA — Background task de persistencia falha silenciosamente
**Arquivo:** `routers/audit.py:94-107`

`persist_audit_artifacts` roda como `background_task`. Se falhar (DB locked, disco cheio),
o usuario ve audit bem-sucedida mas ela nunca aparece no historico.

**Correcao:** Mover persistencia para antes da resposta, ou implementar retry/notificacao.

---

#### T5. MEDIA — `lru_cache` retorna lista mutavel
**Arquivo:** `core/config.py:183-221`

`_load_criteria_from_file` tem `@lru_cache` mas retorna `list[AuditCriterion]`.
Se qualquer codigo downstream mutar a lista, o cache fica corrompido para todas as
chamadas futuras.

**Correcao:** Retornar `tuple(criterios)` em vez de `list`.

---

#### T6. MEDIA — `parse_json_with_repair` bloqueia event loop
**Arquivo:** `core/evaluation.py:74-109`

As chamadas de reparo de JSON sao sincronas (nao usam `asyncio.to_thread`), bloqueando
o event loop do FastAPI durante a comunicacao com Azure/Gemini.

**Correcao:** Envolver chamadas de reparo em `asyncio.to_thread`.

---

#### T7. BAIXA — `globals().update()` cria dependencias implicitas frageis
**Arquivos:** `core/evaluation.py:36-39`, `core/audit.py:22-26`, `services.py:14-18`

Colisoes de nomes entre modulos podem ocorrer silenciosamente.

---

## FLUXO 2: Envio ao Supervisor

### Como funciona

```
Frontend: AuditResultActions "Enviar ao supervisor"
  -> POST /api/dashboard/save (routers/system.py)
     -> Salva em arquivos_salvos com status inicial
     -> queue_audit_for_supervisor_review()
        -> status = awaiting_pair (1a auditoria do operador)
        -> status = pending_approval (2a auditoria -> envia par ao supervisor)
  -> Supervisor ve em GET /api/gestores/auditorias
     -> Filtra por supervisor do usuario logado
     -> Mostra KPIs: nota media, taxa aprovacao, etc.
```

### Status: FUNCIONAL

O fluxo de envio funciona corretamente:
- Auditor cria auditoria e clica "Enviar ao supervisor"
- Sistema aguarda par de auditorias por operador (regra de negocio)
- Supervisor ve apenas suas auditorias (filtro forcado por role)
- Supervisor pode aprovar

### Bugs encontrados

#### S1. MEDIA — `POST /api/dashboard/save` requer role `admin`, nao `supervisor_or_admin`
**Arquivo:** `routers/system.py:125`

Se um usuario supervisor tentar salvar audit no dashboard, recebe 403.
Na pratica, quem cria auditorias sao auditores (role admin), entao funciona.
Mas o botao aparece na UI sem verificar role.

---

#### S2. BAIXA — Formulario de feedback do supervisor esta DESLIGADO
**Arquivo:** `src/features/supervisor/components/SupervisorPortal.tsx:70`

```typescript
const SHOW_SUPERVISOR_FEEDBACK = false;
```

O backend (`POST /api/gestores/feedback`) funciona, mas a UI nunca mostra o form.
O supervisor so pode aprovar ou contestar, sem deixar comentarios textuais.

---

## FLUXO 3: Contestacao (Botao Contestar)

### Como funciona

```
Supervisor: clica "Contestar" no portal
  -> POST /api/gestores/auditorias/{id}/contest
     -> body: { reason: "motivo da contestacao" }
     -> update_audit_status(id, "contestation_pending_review", reason)
     -> status muda para contestation_pending_review

Admin: ve em "Revisao de Contestacoes"
  -> GET /api/revisao/contestacoes
     -> Filtra auditorias com status = contestation_pending_review
  -> Abre detalhe: GET /api/revisao/auditorias/{id}
  -> Emite veredito: POST /api/revisao/auditorias/{id}/veredito
     -> body: { verdict: "accepted"|"rejected", defense: "justificativa" }
     -> "accepted" -> status = contestation_accepted
     -> "rejected" -> status = approved (mantem nota original)
```

### Status: FUNCIONAL COM RESSALVAS

O fluxo basico funciona end-to-end. A contestacao chega ao admin e o veredito
atualiza o status corretamente. Porem, ha falhas na validacao de transicoes.

### Bugs encontrados

#### C1. MEDIA — Sem validacao de status de ORIGEM nas transicoes
**Arquivo:** `routers/supervisor.py:247-264` + `repositories/audits.py:423-482`

Nenhum endpoint verifica o status atual antes de transicionar. Via API direta:
- Supervisor pode aprovar auditoria que esta em `contestation_pending_review`
  (burlando revisao do admin)
- Supervisor pode contestar auditoria ja `approved` ou `contestation_accepted`
  (reabrindo caso fechado)
- Supervisor pode contestar multiplas vezes (sobrescrevendo motivo anterior)

O frontend protege corretamente (botoes so aparecem para `pending_approval`),
mas chamadas diretas a API nao tem guard.

**Correcao:** Adicionar validacao de status de origem:
```python
ALLOWED_TRANSITIONS = {
    "pending_approval": {"approved", "contestation_pending_review"},
    "contestation_pending_review": {"contestation_accepted", "approved"},
}
current = get_audit_status(audit_id)
if target not in ALLOWED_TRANSITIONS.get(current, set()):
    raise ValueError(f"Transicao invalida: {current} -> {target}")
```

---

#### C2. MEDIA — `ValueError` nao tratado nos endpoints do supervisor
**Arquivo:** `routers/supervisor.py:248-264`

Se `update_audit_status` levantar `ValueError`, o FastAPI retorna 500 generico
em vez de 400 com mensagem clara. O endpoint de review (`review.py:73-81`)
trata corretamente, mas os do supervisor nao.

**Correcao:** Adicionar `try/except ValueError as exc: raise HTTPException(400, str(exc))`.

---

#### C3. MEDIA — Campos de revisao apagados em re-transicao
**Arquivo:** `repositories/audits.py:443-478`

Os campos `contestation_verdict`, `review_defense`, `reviewed_by`, `reviewed_at`
so sao preservados na transicao para `approved`. Em qualquer outra transicao
(incluindo `contestation_pending_review`), sao zerados.

Se BUG C1 permitir re-contestacao, o historico da revisao anterior e perdido.

---

#### C4. BAIXA — Feedback id hardcoded como 0 na listagem
**Arquivo:** `repositories/audits.py:637`

O id do feedback vem como 0 na listagem mas com valor real no detalhe.

---

#### C5. BAIXA — Multiplas conexoes nao-transacionais no facade
**Arquivo:** `database.py:978-990`

`update_audit_status` abre 3 conexoes separadas (update + get_audit + rebalance).
Janela de inconsistencia entre o status atualizado e o rebalanceamento.

---

## Plano de correcoes

### Fase 1 — Correcoes criticas (impactam laudo e dados) — APLICADA

| # | Bug | Acao | Arquivo | Status |
|---|-----|------|---------|--------|
| T1 | Reevaluate nao salva | `update_audit_result()` + `input_hash` no request | repositories/audits.py, routers/audit.py, schemas.py | CORRIGIDO |
| T2 | ai_feedback perdido | Ler `ai_feedback` em `row_to_audit_result` | repositories/common.py | CORRIGIDO |
| T3 | Setores faltando | Adicionar aliases no `sector_mapping` | core/config.py | CORRIGIDO |
| C1 | Sem guard de status | `_ALLOWED_STATUS_TRANSITIONS` com estados terminais | repositories/audits.py | CORRIGIDO |

### Fase 2 — Robustez (previne problemas futuros) — APLICADA

| # | Bug | Acao | Arquivo | Status |
|---|-----|------|---------|--------|
| T5 | Cache mutavel | Retornar `tuple()` no lru_cache + `list()` no caller | core/config.py | CORRIGIDO |
| C2 | ValueError nao tratado | try/except nos endpoints supervisor | routers/supervisor.py | CORRIGIDO |
| C3 | Campos apagados | Preservar campos de revisao em transicoes do review flow | repositories/audits.py | CORRIGIDO |
| S2 | Feedback desligado | Avaliar se `SHOW_SUPERVISOR_FEEDBACK` deve ser `true` | SupervisorPortal.tsx | PENDENTE (decisao de negocio) |

### Fase 3 — Melhorias (qualidade a longo prazo) — APLICADA

| # | Bug | Acao | Status |
|---|-----|------|--------|
| T4 | Background silencioso | Wrapper `_safe_persist` com logging de erro | CORRIGIDO |
| T6 | Event loop bloqueado | `await asyncio.to_thread(parse_json_with_repair, ...)` nos 3 call sites em audit_evaluator.py | CORRIGIDO |
| T7 | globals().update | Imports explicitos em core/evaluation.py e core/audit.py; services.py usa `from X import *` + re-exports transitivos | CORRIGIDO |
| C5 | Multi-conexao | `_SharedConnection` wrapper + conexao unica em `database.update_audit_status` | CORRIGIDO |

---

## Testes implementados

Arquivo: `backend/tests/test_audit_flow_fixes.py` (11 testes)

1. **test_ai_feedback_roundtrip_via_row_to_audit_result** — T2: ai_feedback sobrevive save -> load
2. **test_criteria_load_transferencia** — T3: aliases no sector_mapping
3. **test_criteria_cache_returns_fresh_list** — T5: cache retorna copias independentes
4. **test_approve_requires_pending_approval** — C1: nao pode aprovar audit ja aprovada
5. **test_contest_requires_pending_approval** — C1: nao pode contestar audit ja aprovada
6. **test_approve_works_from_pending_approval** — C1: fluxo normal funciona
7. **test_contest_works_from_pending_approval** — C1: fluxo normal funciona
8. **test_approve_from_contestation_pending_review** — C1: admin pode rejeitar contestacao
9. **test_review_fields_preserved_across_review_flow** — C3: campos preservados
10. **test_reevaluate_persists_via_update_audit_result** — T1: reevaluacao salva no banco
11. **test_update_audit_result_returns_none_for_unknown_hash** — T1: hash inexistente retorna None

---

## Validacao executada

```
python -m pytest backend/tests/ -v -> 188 passed, 1 skipped (41.60s)
Trace completo do fluxo POST /api/audit -> OK
Trace completo do fluxo contestacao -> OK (validacao de transicao implementada)
Verificacao de endpoints do supervisor -> OK (ValueError agora retorna 400)
Verificacao de endpoints de revisao -> OK
Frontend SupervisorPortal.tsx -> botoes corretos para cada status
Frontend ReviewPage.tsx -> veredito funcional
```

### Commits aplicados

1. `8d5783e` — fix: apply 6 critical audit flow fixes (T2, T3, T5, C1, C2, C3)
2. `46ea09d` — fix: apply T1 and T4 — reevaluate persistence and background task error logging
3. *(pendente)* — fix: apply T6, T7, C5 — event loop, explicit imports, shared connection
