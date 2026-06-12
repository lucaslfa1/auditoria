# Revisao Completa - Modulo Auditoria

**Data**: 2026-04-09
**Escopo**: Backend (services, classification, quality, evaluation, DB, exports) + Frontend (Dashboard, Classifier, SupervisorPortal) + Testes e Dados

---

## Sumario Executivo

| Severidade | Qtd | Descricao |
|------------|-----|-----------|
| CRITICO    | 6   | Bugs que podem causar perda de dados, scores incorretos ou falhas silenciosas |
| ALTO       | 12  | Gaps de seguranca, testes faltantes, dados desatualizados |
| MEDIO      | 15  | UX, performance, type safety, manutencao |
| BAIXO      | 10  | Acessibilidade, documentacao, code smell |

---

## 1. FINDINGS CRITICOS

### C-01: Script `sync_criteria_json_to_db.py` referencia JSON inexistente
- **Arquivo**: `backend/scripts/sync_criteria_json_to_db.py`
- **Problema**: Faz `DELETE FROM audit_criteria, audit_alerts, audit_sectors` e tenta ler de `/src/features/audit/data/auditCriteria.json` que nao existe. O source of truth e `scoring_rules.yaml`.
- **Risco**: Se executado, apaga todos os criterios do banco sem conseguir recria-los.
- **Fix**: Reescrever para ler de `scoring_rules.yaml` ou deletar o script e documentar que o sync e via outro mecanismo.

### C-02: Pesos de scoring > 100% sem validacao
- **Arquivo**: `backend/db/scoring_rules.yaml`
- **Problema**: Weights individuais chegam a 2.00 (200%). Totais por alerta chegam a 11.55 (1155%). Nao ha validacao de bounds.
- **Risco**: Score final pode ultrapassar 100% ou ficar incoerente com a intencao de avaliacao.
- **Fix**: Adicionar validacao no loader do YAML: `assert 0 < weight <= MAX_WEIGHT` e documentar se a intencao e deflator (multiplicador) ou percentual.

### C-03: Mapeamento de alertas no export hardcoded e desincronizado
- **Arquivo**: `backend/core/export_gestores.py:24-100`
- **Problema**: `ALERT_MAP` com 47 entradas hardcoded. `scoring_rules.yaml` tem 33 alertas. Novos alertas adicionados ao YAML nao aparecem nos exports de gestores.
- **Risco**: Relatorios de gestores ficam incompletos para alertas novos.
- **Fix**: Gerar `ALERT_MAP` dinamicamente a partir do YAML, ou adicionar teste que valida cobertura 1:1.

### C-04: `pesos_gestores.json` pode nao existir - falha silenciosa
- **Arquivo**: `backend/core/export_gestores.py` (funcao `load_pesos()`)
- **Problema**: Se o JSON nao existe, retorna dict vazio sem log. Deflators nao sao aplicados.
- **Risco**: Exports de gestores saem sem pesos de deflacao, sem nenhum aviso.
- **Fix**: Logar WARNING ou lancar erro se arquivo nao encontrado. Validar na inicializacao.

### C-05: Excecoes silenciosas em caminhos criticos
- **Arquivos**: Multiplos
  - `database.py:434, 786, 894, 1040` - bare `except Exception: pass`
  - `classification.py:828, 858, 956, 1289, 1305` - swallow errors
  - `automation.py:82, 291, 343, 450` - swallow errors
  - `text_processing.py:77-78` - silent pass
- **Risco**: Erros de banco, parsing e IA sao engolidos. Bugs ficam invisiveis em producao.
- **Fix**: Substituir `pass` por `logger.exception(...)` no minimo. Em caminhos criticos (DB, AI), re-raise ou retornar erro explicito.

### C-06: Quota de auditoria (2/operador/mes) so avisa, nao bloqueia
- **Arquivo**: `backend/routers/audit.py:70-75`
- **Problema**: Verificacao de quota emite warning mas nao impede a auditoria de prosseguir.
- **Risco**: Regra de compliance "2 calls per operator/month" nao e enforced.
- **Fix**: Retornar HTTP 429 quando quota excedida, com mensagem clara.

---

## 2. FINDINGS ALTOS

### A-01: Credenciais expostas no repositorio
- `backend/gcp-key.json` presente no diretorio
- `backend/.env` com chaves Azure
- **Fix**: Adicionar ao `.gitignore`, rotacionar chaves, usar secret manager.

### A-02: Testes de banco desabilitados
- `test_database_security.py` e varios testes de integracao marcados como `@unittest.skip`
- Zero cobertura de integracao com PostgreSQL real.
- **Fix**: Criar pipeline de testes com banco efemero (Docker/testcontainers).

### A-03: RAG training docs desatualizados
- `criterios_auditoria.md` lista 33 alertas; YAML tem 33. Contagens alinhadas apos fase 2.
- Maioria dos docs RAG de 2026-04-06, sem refresh automatico.
- **Fix**: Automatizar regeneracao via `db_knowledge_agent.py` no CI/CD.

### A-04: Dead code do Gemini
- `core/config.py:100` - `AI_ENABLED = False` para Gemini
- Codigo de classificacao com Gemini ainda referenciado em `classification.py`
- **Fix**: Remover completamente ou reativar com feature flag.

### A-05: Sem validacao de credenciais Azure na inicializacao
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_SPEECH_KEY` sao opcionais
- Sistema inicia normalmente e so falha na primeira auditoria.
- **Fix**: Health check na inicializacao com fail-fast.

### A-06: Race condition no progress interval (Frontend)
- `useClassifier.ts:148-150` - `progressInterval` pode nao ser limpo se componente desmontar durante request.
- **Fix**: Cleanup no `useEffect` return.

### A-07: Non-null assertions sem type guard (SupervisorPortal)
- `SupervisorPortal.tsx:308-317` - `audit.feedback!.` sem verificacao.
- **Fix**: Adicionar guard `if (audit.feedback)` antes do acesso.

### A-08: Rate limiter in-memory nao funciona em multi-processo
- `main.py:131-132` - Dict in-memory para rate limiting.
- **Fix**: Usar Redis ou middleware distribuido se escalar.

### A-09: SQL injection potencial
- `database.py` - Verificar se ha string interpolation em queries.
- **Fix**: Auditar todas as queries e garantir uso de parametros preparados.

### A-10: Upload de PDF sem validacao de estrutura
- `routers/audit.py:78` - Aceita PDF por MIME type mas nao valida conteudo.
- **Fix**: Validar com biblioteca PDF antes de processar.

### A-11: Sem AbortController nas chamadas API (Frontend)
- Nenhuma chamada fetch usa AbortController para cancelamento.
- **Fix**: Implementar em useClassifier, useTranscription, useAuditFlow.

### A-12: Testes fortemente mockados sem integracao real
- `test_audit_evaluation_wrappers.py` - 100% delegation mocks.
- **Fix**: Adicionar smoke tests de integracao para fluxo completo.

---

## 3. FINDINGS MEDIOS

### M-01: Hardcoded thresholds sem configuracao externa
- `MAX_AUDIO_DURATION_SECONDS = 60`, `LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.8`, `silence_threshold = -40 dBFS`, etc.
- **Fix**: Mover para `config.py` com env vars ou YAML.

### M-02: LRU cache stampede
- `load_audit_criteria_catalog()` com `lru_cache(maxsize=1)` - thundering herd em cold start.
- **Fix**: Usar cache com TTL e lock, ou pre-aquecer na inicializacao.

### M-03: N+1 queries em guardrails
- `enforce_operator_and_direction_guardrails()` faz query por classificacao.
- **Fix**: Batch query para todas as classificacoes de uma vez.

### M-04: Array slice em todo render (Dashboard)
- `filteredHistory.slice().reverse()` cria array novo a cada render.
- **Fix**: Wrap com `useMemo`.

### M-05: SupervisorPortal com 897+ linhas
- Componente unico muito grande, dificil de manter.
- **Fix**: Extrair subcomponentes: FeedbackForm, AuditDetailPanel, SearchBar.

### M-06: FormData envia "undefined" string se props forem undefined
- `useTranscription.ts:34-38` - Sem null check antes de append.
- **Fix**: Filtrar campos undefined antes de enviar.

### M-07: Setor/Alerta race condition no frontend
- Quando usuario muda setor, dropdown de alerta nao limpa valor anterior.
- **Fix**: Reset alert selection on sector change.

### M-08: Sem paginacao para listas grandes (Classifier)
- 50+ classificacoes renderizam todas de uma vez.
- **Fix**: Implementar paginacao ou virtualizacao.

### M-09: Mensagens de erro genericas em downloads
- 7 funcoes de download mostram "Nao foi possivel baixar" sem contexto.
- **Fix**: Incluir tipo de erro (rede, permissao, backend).

### M-10: Memory leak em URL.createObjectURL
- `Classifier.tsx:253-260` - `revokeObjectURL` so chamado apos click.
- **Fix**: Revogar no cleanup do useEffect.

### M-11: Debounce timer nao limpo (SupervisorPortal)
- `searchTimerRef` cria timeout que dispara mesmo apos navegacao.
- **Fix**: Limpar no return do useEffect.

### M-12: Console.error em producao
- 23 `console.error()` calls espalhados pelo frontend.
- **Fix**: Usar servico de error tracking ou condicionar a dev.

### M-13: Normalizacao Unicode fragil no export
- `_normalize()` em `export_gestores.py` pode nao cobrir todos os diacriticos.
- **Fix**: Usar `unidecode` ou validar com testes para acentos PT-BR.

### M-14: Sem transaction rollback explicito no banco
- Updates em `database.py` sem pattern de rollback em caso de falha parcial.
- **Fix**: Usar context manager com rollback automatico.

### M-15: Alert ID aliases com mapeamento unidirecional
- `classification.py:45-47` - Apenas `BAS-POLICIAL -> BAS-PRIORITARIO-POLICIA`.
- **Fix**: Centralizar aliases no YAML com deprecation path.

---

## 4. FINDINGS BAIXOS

### B-01: Sem ARIA labels em botoes icon-only (Dashboard, Classifier)
### B-02: Indicadores so por cor sem alternativa texto (Dashboard metrics)
### B-03: Table headers sem `scope` (Classifier)
### B-04: Upload area nao ativa com tecla Space (Classifier)
### B-05: Modais nao restauram foco ao fechar (SupervisorPortal)
### B-06: Progress bar de audio sem aria-label (Classifier)
### B-07: Live region ausente para updates de progresso
### B-08: Documentacao de banco referencia SQLite (database.md)
### B-09: Sem documentacao de API (OpenAPI/Swagger)
### B-10: Empty state copy inconsistente entre componentes

---

## 5. PLANO DE ACAO

### Fase 1 - Criticos e Seguranca (Imediato - esta sprint)

| # | Acao | Arquivo(s) | Esforco |
|---|------|-----------|---------|
| 1 | Deletar ou reescrever `sync_criteria_json_to_db.py` | scripts/ | 1h |
| 2 | Adicionar validacao de weights no loader YAML | scoring_rules loader | 2h |
| 3 | Gerar ALERT_MAP dinamicamente do YAML | export_gestores.py | 3h |
| 4 | Fail-fast se `pesos_gestores.json` ausente | export_gestores.py | 30min |
| 5 | Substituir `except: pass` por logging em 15+ locais | database.py, classification.py, automation.py | 3h |
| 6 | Enforce quota de auditoria (HTTP 429) | routers/audit.py | 1h |
| 7 | Remover `gcp-key.json` e atualizar .gitignore | raiz | 30min |
| 8 | Health check de credenciais Azure no startup | main.py | 1h |

### Fase 2 - Estabilidade e Testes (Proxima sprint)

| # | Acao | Arquivo(s) | Esforco |
|---|------|-----------|---------|
| 9 | Reativar testes de banco com testcontainers | tests/ | 4h |
| 10 | Adicionar teste de cobertura YAML <-> export | tests/ | 2h |
| 11 | Automatizar regeneracao RAG docs | CI/CD + db_knowledge_agent | 2h |
| 12 | Remover dead code Gemini | config.py, classification.py | 1h |
| 13 | Implementar AbortController no frontend | hooks/ | 2h |
| 14 | Fix race condition no useClassifier | useClassifier.ts | 1h |
| 15 | Adicionar type guards no SupervisorPortal | SupervisorPortal.tsx | 1h |
| 16 | Auditar queries SQL para injection | database.py | 2h |

### Fase 3 - Performance e UX (Sprint seguinte)

| # | Acao | Arquivo(s) | Esforco |
|---|------|-----------|---------|
| 17 | Externalizar thresholds hardcoded | config.py + YAML | 2h |
| 18 | Fix cache stampede (TTL + lock) | core/ | 1h |
| 19 | Batch queries nos guardrails (N+1) | classification.py | 2h |
| 20 | useMemo no Dashboard | Dashboard.tsx | 30min |
| 21 | Paginacao no Classifier | Classifier.tsx | 2h |
| 22 | Refatorar SupervisorPortal (897 linhas) | SupervisorPortal.tsx | 3h |
| 23 | Mensagens de erro contextuais nos downloads | useTranscription.ts | 1h |
| 24 | Reset alert ao mudar setor | Classifier.tsx | 30min |

### Fase 4 - Acessibilidade e Documentacao (Backlog)

| # | Acao | Esforco |
|---|------|---------|
| 25 | ARIA labels em todos os botoes icon-only | 2h |
| 26 | Alternativas texto para indicadores de cor | 1h |
| 27 | Keyboard navigation completa nos modais | 2h |
| 28 | Atualizar database.md (PostgreSQL) | 1h |
| 29 | Gerar docs OpenAPI do FastAPI | 1h |
| 30 | Consistencia de empty states | 1h |

---

## Metricas de Acompanhamento

- **Excecoes silenciosas**: 15+ → 0
- **Cobertura de testes DB**: 0% → 80%+
- **Alertas YAML vs Export**: 33 alertas YAML → catalogo dinamico via gestores_mapping.py (fase 2)
- **Docs RAG vs YAML**: 33 vs 33 → sincronizado (fase 2)
- **Console.error em prod**: 23 → 0

---

*Relatorio gerado por analise estatica de 3 agentes paralelos cobrindo backend, frontend e camada de dados/testes.*
