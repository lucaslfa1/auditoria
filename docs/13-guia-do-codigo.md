# 13 — Guia do Código (mapa para quem nunca viu o repositório)

> Objetivo: dar a um dev novo o "onde está o quê" do **backend** para se localizar
> em minutos. Complementa o [02-arquitetura.md](02-arquitetura.md) (visão de alto
> nível) e o [03-banco-de-dados.md](03-banco-de-dados.md) (esquema). O detalhe de
> cada função está nas **docstrings** dos próprios módulos (PT-BR); este guia é o
> mapa que diz em qual arquivo procurar.

## 1. Como o backend é organizado (camadas)

O backend é FastAPI (Python) e segue uma separação por camadas. A regra mental:
**routers → core/services → repositories → db**.

```
backend/
├── main.py                 # cria o app FastAPI, registra os routers, middleware/auth
├── services.py             # fachada de auditoria (transcrição + avaliação) p/ os routers
├── routers/                # CAMADA HTTP: 1 arquivo por domínio (audit, review, telefonia, …)
│                           #   só validam request/response e delegam. Sem regra de negócio pesada.
├── core/                   # CAMADA DE DOMÍNIO: o "cérebro" (classificação, transcrição,
│   │                       #   avaliação, automação, fechamento, integração Huawei)
│   └── huawei/             #   subpacote da coleta Huawei (discovery, classificação, locks, config)
├── repositories/           # CAMADA DE DADOS: todo SQL vive aqui (1 arquivo por agregado).
│                           #   Funções recebem get_connection (injeção) e abrem/fecham a conexão.
├── db/                     # infra de banco: conexão, migrations, schema, constantes de domínio
│   ├── connection.py       #   get_connection() centralizado (psycopg2 + DictCursor) → Neon
│   ├── domain_constants.py #   STATUSES, SCOPES, prioridades — fonte única dos enums de string
│   ├── runtime_schema.py   #   CREATE TABLE/ensure_* idempotentes
│   └── migration_steps/    #   migrations individuais (information_schema, %s)
├── audio/                  # diarização e identificação de locutor (operador × interlocutor)
├── transcription_providers/# adaptadores de STT (Azure Fast Transcription, Whisper, SDK)
├── storage/                # storage da mídia de auditoria (audit_storage)
└── utils/                  # utilitários transversais (http_session, text_processing)
```

> Banco: **PostgreSQL no Neon** (não é mais Supabase nem SQLite). Conexão sempre via
> `db.connection.get_connection()`. Placeholders sempre `%s`. Ver
> [03-banco-de-dados.md](03-banco-de-dados.md).

## 2. O fluxo ponta-a-ponta → quais arquivos o implementam

O sistema audita ligações telefônicas com IA. O caminho de uma ligação:

1. **Coleta (Huawei)** — baixa as gravações da plataforma Huawei AICC.
   - Orquestrador: `core/huawei_sync.py` (`executar_sync_huawei`).
   - Descoberta de chamadas: `core/huawei_discovery.py` (`HuaweiDiscoveryService.fetch_all`).
   - Config/credenciais/tuning: `core/huawei/automation_config.py`.
   - Resolução de operador: `core/huawei/operator_resolution.py`.
   - Classificação automática (Fase 2): `core/huawei/sync_classification.py`.
   - Detalhes do domínio: [06-integracao-huawei.md](06-integracao-huawei.md).
2. **Triagem (classificação)** — cada gravação vira 1 linha na fila
   `fila_revisao_classificacao`.
   - Classificação IA + guardrails: `core/classification.py` (entrada `classify_audio`).
   - Repositório da fila: `repositories/classification_review.py` (escrita) e
     `repositories/classification_review_queries.py` (leitura).
   - Transcrição de triagem: `core/transcription.py` (cadeia de provedores).
3. **Auditoria** — itens prontos viram auditoria (status `awaiting_pair` = "Arquivos Salvos").
   - Pipeline: `core/audit_pipeline.py` (normaliza contexto) + `core/audit.py` (orquestra).
   - Avaliação IA: `core/audit_evaluator.py` (provedores) + `core/audit_evaluation_prompt.py`
     (montagem do prompt) + `core/audit_evaluation_payload.py` (normalização/scoring).
   - Automação em lote: `core/automation.py` + `core/automation_engine.py` (ciclo) +
     `core/automation_config.py` (parâmetros) + `core/automation_disposition.py` (descarte/retry).
   - Persistência: `repositories/audits.py` (+ `audits_export.py` p/ fechamento/BI).
4. **Revisão humana → Fechamento** — supervisor aprova/contesta; o aprovado entra no
   fechamento mensal.
   - Supervisão: `routers/supervisor.py` + `repositories/audits.py` (contestação/status).
   - Fechamento (contrato BI — **não alterar formato**): `core/fechamento_service.py`,
     `core/export_fechamento.py`. Ver [07-custos-e-guardrails.md](07-custos-e-guardrails.md)
     e a nota de contrato BI.

## 3. Convenções do código (importantes p/ não quebrar nada)

- **Fachada + reexport (refatoração conservadora).** Vários módulos grandes foram
  divididos extraindo um cluster coeso para um módulo irmão e **reexportando os nomes
  antigos** do módulo original (ex.: `repositories/audits.py` reexporta de
  `audits_export.py`/`audit_drafts.py`; `core/huawei_sync.py` reexporta de
  `core/huawei/automation_config.py`). Consequência: `from modulo_antigo import nome`
  e `patch('modulo_antigo.nome')` continuam funcionando. **Ao mexer, mantenha o
  reexport** — testes dependem de `modulo.nome` resolver. Ver
  [project-arch-split-plan] no histórico de versões (`logs/versions/1.3.15x–17x`).
- **Prompts e correções fora do código.** Prompts da IA em
  `backend/config/prompts.json`; correções fonéticas em
  `backend/config/text_corrections.json`. **Não hardcodar prompt no código.**
- **Critérios de auditoria vêm do banco** (`audit_sectors`/`audit_alerts`/`audit_criteria`,
  tela admin IA > Critérios), não de YAML. Resolver alias canônico com
  `core.classification.canonicalize_alert_id` antes de consultar.
- **Zeragem de nota em 3 camadas** (não remover): (1) criterionId=senha/fail,
  (2) `fatal_flags` da IA, (3) substring fallback. A zeragem é aplicada no scoring
  (`core/evaluation.py`), não no `audit_evaluator`.
- **Custo de API** é controlado por `core/cost_guard.py` (teto diário + kill-switch).
  Toda chamada paga (avaliação, embedding, classificação) é registrada lá. As
  docstrings de módulo marcam "CUSTO DE API" onde houver.
- **Enums de string** (status da fila, da auditoria, scopes) vivem em
  `db/domain_constants.py` — use as constantes, não strings cruas.
- **Setores**: id interno é fixo; o rótulo é editável (tela de Setores) e o vínculo
  histórico vive em `sector_aliases`. Mapa: LP/Central=transferencia, Fênix=fenix,
  Diálogo=uti, GRS=nome antigo de UTI (normalizar).

## 4. Onde rodar e testar

- Testes backend: `tests/backend/` (pytest). **Sempre contra banco de TESTE**, nunca
  prod — há um guard em `tests/backend/conftest.py` que bloqueia `DATABASE_URL`
  apontando para o Neon de produção (host `ep-aged-river`). Ver [09-testes.md](09-testes.md).
- Rodar: `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/auditoria_test python -m pytest tests/backend -q`.
- Deploy/operação: [05-operacao-runbook.md](05-operacao-runbook.md), [11-deploy.md](11-deploy.md).

## 5. Dívida técnica conhecida (mapa honesto para o time)

Itens conscientes, documentados e **não bloqueantes** — registrados aqui para o time
não ser pego de surpresa:

- **Audit-log triplicado** (duplicação estrutural benigna): o padrão de validação +
  INSERT em `*_audit_log` (incl. `_VALID_ORIGINS`) existe em 3 lugares —
  `repositories/admin_criteria_audit_log.py`, `repositories/configuration.py` e
  `repositories/sector_aliases.py`. Candidato a unificar num helper compartilhado,
  **depois de confirmar** que as origens/esquemas das 3 tabelas são equivalentes.
- **`_resolve_operator_name_from_interacao` duplicado** entre `core/huawei_sync.py` e
  `core/huawei_sync_gatekeeper.py`. Consolidar exige decidir qual é a canônica.
- **Hardening NUL/jsonb (pontos de baixa severidade)**: o cast `metadata_json::jsonb`
  já foi protegido na fila de Triagem e nos pontos de escrita (`strip_json_nul`/
  `harden_jsonb_nul_cast` em `repositories/common.py`). Faltam pontos best-effort de
  baixo risco: `core/automation_engine.py` `_load_health_snapshot`, `core/rag_triagem.py`
  e a migração `m20260601_002`. A raiz (sanitização na escrita) já cobre dados novos.
- **Decisões de NÃO dividir** (registradas): `core/transcription.py`,
  `core/automation_engine.py`, `core/classification.py` (minefield de monkeypatch),
  `core/fechamento_service.py` (contrato BI), `db/database.py` e `routers/telefonia.py`
  (já fachada/modularizados). Splits adicionais aqui trocam risco por ganho marginal.

## 6. Para se aprofundar

- Visão e escopo: [01-visao-geral.md](01-visao-geral.md)
- Arquitetura: [02-arquitetura.md](02-arquitetura.md)
- Banco de dados (28 tabelas): [03-banco-de-dados.md](03-banco-de-dados.md)
- Variáveis de ambiente: [04-variaveis-de-ambiente.md](04-variaveis-de-ambiente.md)
- Integração Huawei: [06-integracao-huawei.md](06-integracao-huawei.md)
- Custos e guardrails: [07-custos-e-guardrails.md](07-custos-e-guardrails.md)
- Checklist de handover: [12-checklist-handover.md](12-checklist-handover.md)
- Histórico de mudanças: `logs/versions/x.y.z.md` (1 arquivo por versão).
