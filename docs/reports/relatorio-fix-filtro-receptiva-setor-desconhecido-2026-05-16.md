# Correção do Filtro de Receptivas no Sync Huawei — Setores Desconhecidos

**Data:** 16/05/2026
**Autor:** Lucas (com diagnóstico assistido)
**Componente:** `backend/core/huawei_sync.py`, `backend/tests/test_huawei_sync.py`, `src/features/telefonia/components/SyncPanel.tsx`, `src/features/telefonia/hooks/useTelefoniaSync.ts`
**Commit:** `f421346`
**Severidade:** Alta — receptivas de setores de risco vinham sendo baixadas e enviadas à triagem, violando a regra "setor de risco audita só ativas".

## Resumo Executivo

O filtro `_should_skip_call` que protege a coleta Huawei contra ligações receptivas em setores de risco (UTI, BAS, Distribuição, Transferência, Fênix) era **fail-open**: só descartava a ligação quando o setor do operador caía exatamente em um dos cinco slugs hardcoded. Para qualquer outro caso (operador não cadastrado em `colaboradores`, setor novo sem alias mapeado, ou alias resolvendo pra slug fora do set), a chamada **passava direto** e era baixada — inclusive receptivas legítimas de setores de risco ainda não reconhecidos pelo sistema.

A correção adiciona um *branch* fail-closed: quando o setor resolvido é vazio, a chamada **só é descartada se for inbound**. Outbound e direção indefinida seguem para a triagem, preservando o requisito do usuário de **detectar novos operadores** automaticamente sem precisar de cadastro prévio.

## Sintoma Observado

> "Os filtros de ligação da Huawei ainda não funcionam corretamente. Ao fazer o download de ligações testei nos setores de risco e eles ainda continuam baixando ligações receptivas."

A hipótese inicial do usuário foi cirúrgica:

> "talvez os setores que ainda não foram cadastrados não estejam discriminando os setores de risco e por isso acabam baixando receptivas."

A investigação confirmou exatamente esse padrão.

## Investigação

### 1. Mapa do gate de direção

O sync usa `OUTBOUND_ONLY_RISK_SECTORS = {"uti", "bas", "distribuicao", "fenix", "transferencia"}` (em `backend/core/huawei_direction.py:15`) para decidir quais setores aceitam apenas ligações ativas. O conjunto é importado em três pontos: `backend/core/huawei_sync.py`, `backend/automation.py` e `backend/routers/telefonia.py`. Apenas o `huawei_sync` decide o **download**; os demais usam o conjunto para enfileiramento pós-download.

### 2. Como `_should_skip_call` era avaliado

```python
def _should_skip_call(interacao: dict, operador: dict) -> Optional[str]:
    if _is_mondelez_operator(operador):
        return "mondelez"

    sector_slug = _operator_sector_id(operador)
    if sector_slug in _NON_TELEFONIA_SECTORS:
        return "non_telefonia_sector"

    if sector_slug in _AUDIO_DIRECTION_GATE_SECTORS:   # 5 risk sectors
        classified_direction = _resolve_huawei_is_call_in(interacao)
        if classified_direction is None:
            return "direction_unknown"
        if classified_direction is True:
            return "risk_inbound"
        return None

    regra = AUTOMATION_RULES.get(sector_slug)
    if regra:
        # ... aplica regra de direção quando definida
        ...

    return None   # <- fail-open: tudo que não casou cai aqui
```

Para um operador identificado em setor de risco, o filtro funcionava como esperado. **Mas** quando `_resolve_operador_interacao` não casava o `workNo`/`operatorName` da chamada com nenhum operador auditável no banco, ele caía no fallback (`backend/core/huawei_sync.py:569-576`):

```python
return {
    "nome": format_pt_br_name(str(operator_name or "Nao Identificado").strip()),
    "id_huawei": str(operator_id or "").strip(),
    "id_telefonia": str(operator_id or "").strip(),
    "setor": "",           # <- vazio
    "escala": "",
    "matricula": "",
}
```

Com `setor=""`, o `_operator_sector_id` retornava `""`, que não casa com nenhum bucket nem com `AUTOMATION_RULES`. Resultado: **o filtro silenciosamente liberava qualquer direção, inclusive receptivas**.

### 3. Como esse cenário aparece em produção

O manifest CSV `Contact_Record/contact-record/10-minutes/{date}/` traz **todas** as chamadas da janela, não só as dos operadores auditáveis. Três caminhos típicos para o gap:

| Cenário | Causa raiz |
|---|---|
| Operador detectado pelo Huawei mas ainda não cadastrado em `colaboradores` | `_resolve_operador_interacao` cai no fallback `setor=""` |
| Setor de risco novo (ex.: "GRS Zona 2") sem alias em `sector_aliases` | `normalize_huawei_sector` não normaliza para um dos 5 slugs conhecidos |
| Alias presente mas mapeando para slug fora de `OUTBOUND_ONLY_RISK_SECTORS` | Slug não dispara o gate |

### 4. Por que os testes existentes não pegavam

A suíte cobria os caminhos felizes (`setor="uti"` + `isCallIn="true"` → pula) e até casos com aliases reais (`"DIST - VERDE"`, `"GRS - AZUL"`), mas **nenhum teste passava `setor=""` ou simulava o operador-fantasma**. Pior: 5 testes do mecanismo de download (`_processar_candidato_*`) dependiam silenciosamente do bug — eles passavam `operator_by_id={}` esperando que a chamada com `isCallIn="true"` continuasse pelo pipeline, justamente o caminho que o fix bloqueia.

## Solução

### Branch fail-closed em `_should_skip_call`

```python
regra = AUTOMATION_RULES.get(sector_slug)
if regra:
    # ... regra de direção quando definida
    return None

# Setor desconhecido (operador nao cadastrado em colaboradores ou setor
# ainda sem regra mapeada): default conservador para evitar baixar
# receptivas de setores de risco ainda nao reconhecidos. Outbound e
# direcao indefinida continuam descendo para a triagem identificar o
# operador novo.
if not sector_slug:
    if _resolve_huawei_is_call_in(interacao) is True:
        return "receptiva_setor_desconhecido"

return None
```

### Telemetria nova

- `ignoradas_receptiva_setor_desconhecido` adicionado a `_SKIP_REASON_COUNTERS`, `_PROCESS_DELTA_INT_KEYS` e ao dicionário inicial de `executar_sync_huawei`.
- Também conta no agregado `ignoradas_direcao_incompativel` via `_SKIP_REASON_EXTRA_COUNTERS`.
- Registro no log do sync (`huawei_sync_logs`) com `status="skipped_direction"` e `failure_reason="receptiva_setor_desconhecido"`, via `_register_direction_skip` e `_is_direction_skip`.

### UI

`SyncPanel.tsx` ganhou item novo no relatório de sync mostrando "Receptivas ignoradas (setor desconhecido)" quando o contador é > 0. Tipo `SyncResult` em `useTelefoniaSync.ts` estendido com o campo opcional.

## Tabela de Comportamento

| Cenário | Antes | Depois |
|---|---|---|
| Operador cadastrado em setor de risco, receptiva | Pula (`risk_inbound`) | Pula (`risk_inbound`) |
| Operador cadastrado em setor de risco, outbound | Baixa | Baixa |
| **Operador não cadastrado, receptiva** | **Baixa** ⚠️ | **Pula** (`receptiva_setor_desconhecido`) ✅ |
| Operador não cadastrado, outbound | Baixa | Baixa (mantém detecção de novos) |
| Operador não cadastrado, direção indefinida | Baixa | Baixa (mantém detecção de novos) |
| Setor não-telefonia (`celula_atendimento`) | Pula | Pula |
| Operador Mondelez | Pula | Pula |

## Decisão de Design

A alternativa estrutural — importar via API Huawei (`cmsapp/v1/openapi/realindex/agent/agentsinskill`) o mapa `workNo → skill → setor` e usar como verdade independentemente do cadastro local — foi avaliada e adiada. O fix pragmático aplicado:

- **Não bloqueia** o requisito do usuário de detectar operadores novos automaticamente (outbound de desconhecidos continua descendo).
- **Bloqueia** o vazamento de receptivas de setor de risco, mesmo quando o operador ainda não foi cadastrado nem o setor está em `OUTBOUND_ONLY_RISK_SECTORS`.
- Tem custo trivial: 5 linhas na função do filtro + telemetria.
- Tem caso-borda aceitável: pode descartar receptiva legítima de operador novo em setor não-risco (ex.: cadastro). Em produção, isso se auto-corrige assim que o operador for incluído em `colaboradores`.

A solução estrutural via API Huawei fica como evolução futura: ao implementá-la, basta substituir o `not sector_slug` por uma lookup nesse mapa e a heurística atual vira último-recurso.

## Verificação

### Testes

- **3 testes novos** em `backend/tests/test_huawei_sync.py`:
  - `test_should_skip_call_descarta_receptiva_quando_setor_desconhecido`
  - `test_should_skip_call_libera_outbound_quando_setor_desconhecido`
  - `test_should_skip_call_libera_direcao_indefinida_quando_setor_desconhecido`
- **6 testes pré-existentes ajustados** para não dependerem do bug:
  - 5 de `_processar_candidato_*` passaram a injetar operador real (`{"setor": "cadastro", "id_huawei": "189"}`).
  - `test_executar_sync_limits_downloads_to_twenty_and_defers_to_triage` migrado para setor de risco + outbound (evitando que a triagem setorial por LLM consumisse os 20 candidatos do teste).
- `tests.test_huawei_sync`: **60/60** ✓
- `tests.test_telefonia_router` + `tests.test_review_queue_contract`: **35/35** ✓
- `npx tsc -b --noEmit`: ✓

### Validação em produção (a fazer)

Recomendado: executar uma sync manual de janela curta (ex.: última 1h) e verificar no painel se "Receptivas ignoradas (setor desconhecido)" aparece com valor > 0. Esse contador dá a métrica real do impacto do fix.

## Diff

```
backend/core/huawei_sync.py       | 22 +++++++++++++-
backend/tests/test_huawei_sync.py | 61 ++++++++++++++++++++++++++++++++++-----
src/features/telefonia/components/SyncPanel.tsx | 7 +++++
src/features/telefonia/hooks/useTelefoniaSync.ts | 1 +
4 files changed, 82 insertions(+), 9 deletions(-)
```

## Próximos Passos

1. **Observar produção**: 1 semana de telemetria de `ignoradas_receptiva_setor_desconhecido` para dimensionar o impacto.
2. **Avaliar opção estrutural** (`workNo → skill → setor` via API Huawei) se o contador continuar consistentemente alto ou se aparecerem casos legítimos descartados.
3. **Considerar mover** `OUTBOUND_ONLY_RISK_SECTORS` para tabela editável via UI (mesmo padrão de `sector_aliases`), caso surjam setores de risco novos que precisem ser adicionados sem deploy.
