# Arquitetura — mapa do código

> Onde cada coisa vive no repositório e o que é legado. Visão de negócio em
> `docs/01-visao-geral.md`; schema do banco em `docs/03-banco-de-dados.md`.

## 1. Visão de alto nível

Monorepo full stack. Um único container serve tudo em produção: o FastAPI
expõe a API em `/api/*` e monta o build estático do frontend (Vite) na raiz.

```text
auditoria/
|-- backend/          # FastAPI (Python 3.11)
|-- src/              # React 19 + TypeScript + Vite + Tailwind
|-- tests/            # tests/backend (pytest) + tests/frontend (Node) — docs/09
|-- scripts/          # diagnósticos pontuais + scripts/migration/ (docs/10)
|-- docs/             # documentação (índice em docs/README.md)
|-- logs/versions/    # changelog técnico por versão (x.y.z.md)
|-- rag/sources/      # fontes curadas dos POPs (RAG)
|-- Dockerfile        # multi-stage: build Vite -> Python 3.11-slim + ffmpeg
```

## 2. Backend (`backend/`)

### 2.1 Entrada e fachadas

| Arquivo | Papel |
| --- | --- |
| `main.py` | Bootstrap FastAPI: CORS, security headers, rate limit, Sentry opcional, registro dos routers, mount do frontend estático |
| `prestart.py` | Roda no boot do container: `init_db()` (migrations + seeds idempotentes) |
| `services.py` | Fachada de compatibilidade — re-exporta `core.config/transcription/evaluation/audit/export` para callers antigos (`from services import X`) |
| `schemas.py` | Modelos Pydantic compartilhados (`AuditAlert`, `AuditCriterion`, ...) |
| `jobs/scheduler.py` | Agendamento interno (o disparo diário real vem do cron externo — `docs/05` §1) |

### 2.2 Routers (`backend/routers/` — 21 arquivos)

19 routers + `common.py` (helpers compartilhados) + `__init__.py`:

| Router | Domínio |
| --- | --- |
| `auth.py` | Login/sessão (cookie HMAC), roles `admin`/`supervisor` |
| `audit.py` | Auditoria manual (`POST /api/audit`, reavaliação, áudio/PDF) |
| `classifier.py` | Triagem/classificação de lotes e fila de revisão |
| `telefonia.py` + `telefonia_routes/` | Integração Huawei: orquestrador (estado/helpers) + subrouters `sync`, `cron_d1`, `recordings`, `audit_actions` (ver §5) |
| `automation.py` | Motor de automação: status, run-now, controles |
| `saved_files.py` | Arquivos Salvos (gate humano) |
| `supervisor.py` | Portal do supervisor: aprovação, contestação, exportações |
| `review.py` | Revisão técnica de contestações (veredito) |
| `fechamento.py` | Fechamento mensal (layout + overrides + export Excel) |
| `analytics.py` | Dashboard/indicadores |
| `admin.py`, `admin_criteria.py`, `admin_sector_aliases.py`, `admin_ai_prompts.py` | Administração: usuários e colaboradores; catálogo de critérios/setores; aliases de setor; prompts editáveis |
| `operadores.py`, `supervisores.py` | Colaboradores e supervisores |
| `ai_feedback.py` | Feedback IA (calibração com exemplos) |
| `golden_dataset.py` | Exemplos-gabarito de treinamento (arquivos JSON em `backend/data/rag_training/`) |
| `system.py` | Health (`/api/health`), configurações dinâmicas (`/api/configuracoes` + audit-log), stats de dashboard, client-logs |

### 2.3 `backend/core/` por subsistema

**Transcrição + selector + judge**

- `transcription.py` — pipeline de transcrição (engine default `fast`, cadeia de fallback fast → whisper → gpt4o_diarize → sdk)
- `transcription_orchestrator.py`, `transcription_candidates.py` — orquestra geração de candidatos
- `transcription_selector.py` — candidate selector: gates determinísticos (qualidade de áudio, segmentos, conflito numérico/token) decidem `accepted`/`needs_review`/`manual_review`/`rejected`
- `transcription_judge.py` — judge LLM para desempate do selector (v1.3.80)
- `transcription_quality.py`, `transcription_cross_signals.py`, `quality_analyzer.py`, `quality_observability.py` — heurísticas de qualidade pré/pós transcrição

**Classificação + guardrails**

- `classification.py` — classificação GPT-4o (setor/alerta/operador) + guardrails determinísticos (`canonicalize_alert_id` é a API pública para resolver aliases de alerta)
- `llm_triage.py` — triagem LLM das candidatas (até 2 aprovadas por setor)
- `automation_guardrails.py` — `AutomationGatekeeper.check_eligibility`: fonte única das regras de elegibilidade (usada pelo sync E pela automação)
- `evidence_validation.py`, `huawei_direction.py` — validação de evidência e inferência de direção da chamada

**Avaliação / auditoria**

- `audit.py`, `audit_pipeline.py`, `audit_evaluator.py`, `audit_rules.py`, `evaluation.py` — avaliação GPT-4o contra o catálogo de critérios + score determinístico + zeragem 3 camadas
- `document_parsing.py` — parser de PDF de chat Service Cloud (auditoria documental, v1.3.105)
- `qualification_audit.py`, `sentiment.py`, `summary_regeneration.py` — apoios

**Automação (esteira binária)**

- `automation.py` — auditoria em lote dos itens prontos da fila de triagem
- `automation_engine.py` — ciclo do motor: lock, heartbeat, health snapshot, reconciliação de ciclos stale (`automation_cycle_runs`)
- `automation_disposition.py` — estados terminais: `PROCEED`/`DISCARD_IMPOSSIBLE` (tombstone)/`DISCARD_RECOVERABLE` (anti-loop)/`RETRY`
- `automation_cache.py` — contexto/cache do pipeline de auditoria automática
- `automation_rules.py`, `automation_operator.py` — regras por setor e resolução de operador
- `cost_guard.py` — guardrails de custo: tetos diários + kill-switch (`docs/07` §4)

**Huawei (detalhe em `docs/06-integracao-huawei.md`)**

- `huawei_client.py`, `huawei_obs_client.py`, `huawei_http_session.py`, `huawei_events.py` — clientes CMS/FS/OBS
- `huawei_discovery.py`, `huawei_d_minus_1.py`, `huawei_sync.py`, `huawei_sync_gatekeeper.py`, `huawei_download_chain.py` — descoberta, pipeline D-1, sync (Fases 1/2), cadeia de download
- `huawei/` (pacote) — `download_candidates`, `sync_classification`, `sync_enqueue`, `sync_triagem`, `telemetry`, `protocols`

**Export / fechamento**

- `export.py`, `report_exports.py`, `pdf_generator.py` — exportações de auditoria (Excel/PDF/DOCX)
- `export_fechamento.py`, `fechamento_service.py` — fechamento mensal em Excel (formato é contrato com o BI — não alterar labels)
- `export_gestores*.py`, `export_planejamento*.py`, `export_technical_incidents.py`, `gestores_mapping.py` — relatórios gerenciais

**RAG**

- `procedimentos_rag.py`, `rag_triagem.py` — busca semântica nos POPs curados (`procedimento_chunks` + pgvector); fontes em `rag/sources/procedimentos_operacionais/`

**Infra transversal**: `config.py` (envs/credenciais), `media_storage.py`
(backends de mídia `local`/`gcs`/`azure_blob`), `logging_config.py`,
`network_utils.py`, `runtime_flags.py`, `email_utils.py`.

### 2.4 Demais camadas do backend

| Diretório | Papel |
| --- | --- |
| `repositories/` | Acesso a dados por agregado (audits, telefonia, operators, saved_files, configuration, auth_users, transcript_candidates, ...) — SQL fica aqui, não nos routers |
| `db/` | `connection.py` (pool psycopg2, semáforo, timeouts de sessão, `sslmode=require` p/ hosts remotos); `database.py` (fachada: `init_db()` = migrations + seeds); `migrations.py` (runner); `migration_steps/` (53 steps); `seeds/` (catálogo oficial — `docs/03` §3); `runtime_schema.py` (schema base + views); `domain_constants.py` (status canônicos) |
| `transcription_providers/` | `azure.py` (Fast Transcription + Whisper), `openai_diarize.py` (GPT-4o diarize), `speech_sdk_transcriber.py` (Speech SDK — last-resort VIVO da cadeia de fallback, não remover) |
| `audio/` | Diarização: heurísticas, identificação e normalização de falantes, qualidade de diarização |
| `storage/` | `audit_storage.py` + diretórios de mídia local (`classified_audio/`, `audits/`) quando `MEDIA_STORAGE_BACKEND=local` |
| `config/` | `prompts.json` (prompts externalizados), `text_corrections.json` (correções fonéticas), `audit_rules.yaml`, `fechamento_qualidade_final_layout.json` |
| `utils/` | `text_processing.py` (anti-alucinação, normalizações), `http_session.py` |
| `scripts/` | Diagnósticos pontuais (não fazem parte do runtime) |

## 3. Frontend (`src/`)

Organização por domínio funcional — features novas vão em
`src/features/<dominio>/`, não em pasta genérica de componentes.

| Feature | Tela/fluxo |
| --- | --- |
| `classifier/` | Triagem (entrada do fluxo; inclui `RemoteTriageQueue` — fila de retidos do sync) |
| `audit/` | Auditoria manual: upload, configuração, resultado, edição, reauditoria |
| `saved-files/` | Arquivos Salvos (gate humano; lazy-load do detalhe) |
| `supervisor/` | Portal do supervisor (aprovação/contestação/exportações) |
| `review/` | Revisão técnica de contestações |
| `fechamento/` | Fechamento mensal |
| `dashboard/` | Indicadores e histórico |
| `automacao/` | Painel do motor híbrido (D-1 + engine + health) |
| `telefonia/` | Sync Huawei (status, disparo manual, diagnósticos) |
| `admin/` | Critérios, setores, prompts |
| `colaboradores/` | Cadastro de operadores (campo ID Huawei controla o sync) |
| `ai-feedback/` | Calibração da IA |
| `settings/` | Configurações operacionais |

Transversais: `src/App.tsx` (shell: sessão, tema, roteamento por view, lazy
pages), `src/shared/` (`components/` ex.: Sidebar, player autenticado;
`hooks/`; `lib/` ex.: `apiClient.ts`, telemetria; `types/`),
`src/contexts/AuditCriteriaContext.tsx` (catálogo de critérios em memória).
Os 8 maiores componentes/hooks têm JSDoc PT-BR de topo explicando papel e
endpoints (v1.3.126).

## 4. O que é legado (não usar como referência atual)

| Item | Situação |
| --- | --- |
| `hybrid_dual` (engine de transcrição) | **DESCONTINUADO** — só roda com `AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL`; foi a engine do incidente de custo (`docs/07` §2) |
| `scripts/` e `backend/scripts/` | Diagnósticos pontuais acumulados; nada disso roda em produção |
| `../sentinel` (projeto irmão, fora deste repo) | Referência histórica de onde alguns conceitos foram portados (v1.2.1); NÃO é dependência |
| Docs antigos em `docs/` (architecture/, arquitetura/, database/, reviews/, GUIA_DE_SOBREVIVENCIA, SYSTEM_DOCUMENTATION.md, ...) | Material histórico/complementar — índice canônico em `docs/README.md` |
| Restos de Gemini/AssemblyAI no código | Compatibilidade antiga; caminho validado é 100% Azure |

## 5. Decisões de arquitetura registradas (handover)

- **Divisão dos maiores arquivos (v1.3.133)** — revertendo a decisão
  conservadora anterior, com a suíte verde como rede de segurança:
  - `routers/telefonia.py` virou orquestrador (~1,2k linhas: estado, helpers
    e montagem) + 4 subrouters em `routers/telefonia_routes/` (`sync`,
    `cron_d1`, `recordings`, `audit_actions`). Prova: snapshot das 27 rotas
    idêntico antes/depois. Os subrouters acessam helpers/estado via
    `tf.<nome>` (resolução em runtime — preserva monkeypatch e estado único).
  - `db/database.py` (~1,7k linhas) delega os blocos de lógica real para
    `db/saved_audits.py` (espelho de Arquivos Salvos) e `db/audit_media.py`
    (anexo/recuperação de áudio + `persist_audit_artifacts`), com reexports —
    nenhum caller mudou.
  - `core/classification.py` exporta agora de `classification_lexicon.py`
    (constantes de keywords/pesos) e `classification_audio.py`
    (`truncate_audio`, `get_mime_type`), com reimport explícito.
- **Schema do banco evolui só por `migration_steps/`** (runner com
  `schema_migrations`, commit por step — `docs/03` §2). Não editar
  `runtime_schema.py` para mudanças novas.
- **Regras de elegibilidade têm fonte única** (`AutomationGatekeeper`):
  sync e automação usam a mesma função — não duplicar filtro em outro lugar.
- **Histórico de mudanças** vive em `logs/versions/x.y.z.md` (changelog
  técnico do projeto, uma entrada por versão). Consultar antes de
  alterar comportamento.
