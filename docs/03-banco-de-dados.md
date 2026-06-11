# Banco de dados — dicionário do schema

> Inventário gerado em 2026-06-11 consultando `information_schema` de um banco
> criado do zero por `init_db()` (migrations + seeds) — o banco local
> `auditoria_test`. **38 tabelas** no schema `public`, 4 views, 53 migrations.
> O Neon de produção reporta 44 tabelas (`docs/10-migracao-banco.md` §2): as
> extras são artefatos antigos não recriados pelas migrations — o conjunto
> abaixo é o que o CÓDIGO atual cria e usa.
> Migração para outro servidor: `docs/10-migracao-banco.md`.

## 1. Requisitos de engine

PostgreSQL >= 17 com extensão **pgvector** (`vector`). Sem pgvector as
migrations toleram a ausência com warning, mas as colunas de embedding não são
criadas e o RAG fica degradado. Detalhe e justificativas em `docs/10` §1.

## 2. Mecânica de migrations

- Runner: `backend/db/migrations.py` — descobre os steps de
  `backend/db/migration_steps/` (ordenação lexicográfica por
  `MIGRATION_NAME`), aplica os pendentes e registra em **`schema_migrations`**.
- **Commit por step** (desde v1.3.113): cada migration é atômica, padrão
  Alembic; necessário porque algumas migrations escrevem via `repositories.*`
  (conexão própria do pool).
- `init_db()` (`backend/db/database.py`) roda no boot (`prestart.py`):
  migrations + seeds, tudo idempotente. Banco vazio sobe completo sozinho.
- Mudança de schema nova = um arquivo novo em `migration_steps/`
  (`mYYYYMMDD_NNN_descricao.py` com `MIGRATION_NAME` e `apply(cursor)`).

## 3. Seeds (aplicados por `init_db()` em banco vazio)

| Seed | Conteúdo | Guarda |
| --- | --- | --- |
| `_seed_audit_criteria` | Catálogo bootstrap legado do YAML (`scoring_rules.bootstrap.yaml` — só setor `logistica`) | Pula se já há catálogo |
| `_seed_official_catalog` (v1.3.120) | **Catálogo oficial completo**: `backend/db/seeds/audit_catalog_oficial.sql` (dump de produção: 12 setores, 71 alertas, 1051 critérios; ground truth mantido pela auditora oficial) | Só roda com `audit_sectors <= 1` linha (banco novo); remove o seed legado antes e realinha a sequence |
| `_seed_sector_aliases` | Aliases de setor iniciais | Só em tabela vazia (edições de UI são permanentes) |
| `_seed_users` | Usuários iniciais via `AUTH_USERS_JSON`/`AUTH_USERS_FILE` (obrigatório em produção) | Só em tabela vazia |
| `seed_operadores_from_json` | Colaboradores de `operadores_seed.json` | Só em tabela vazia; desativado em bancos de teste |

## 4. Dicionário de tabelas

### 4.1 Núcleo de auditoria

| Tabela | Propósito | Colunas-chave |
| --- | --- | --- |
| `audits` | Tabela central: uma linha por auditoria (manual ou automática) com resultado, transcrição e estado do workflow | `status` (`awaiting_pair` → `pending_approval` → `approved`/`contestation_*`/`discarded`), `score`/`max_score`, `details_json` (critérios avaliados), `transcription_json`, `input_hash`, `sector_id`/`alert_id`/`operator_name`, `colaborador_id` (FK), `audio_storage_path`+`audio_mime_type` (mídia), `selected_candidate_id`/`selection_reason`/`selection_gates` (selector), `discarded_*`, `contestation_*`/`review_*` (contestação) |
| `audit_drafts` | Rascunho de edição de auditoria por (`input_hash`, `user_id`) antes de salvar | `details_json`, `transcription_json` |
| `arquivos_salvos` | Espelho operacional do módulo Arquivos Salvos (gate humano); aponta para a auditoria principal | `audit_id`, `tipo`, `criado_por` (`automacao` marca origem), `metadata_json`, `score` |
| `gestor_feedbacks` | Feedback de gestor vinculado a uma auditoria (relatórios gerenciais) | `audit_id`, `gestor_nome`, `feedback_texto`, `pontos_melhoria` |
| `report_exports` | Histórico de toda exportação gerada (rastreabilidade) | `report_kind`, `file_format`, `generated_by`, `operator_name`, `sector_id`, `file_size_bytes` |

### 4.2 Catálogo de critérios (ground truth da auditoria)

| Tabela | Propósito | Colunas-chave |
| --- | --- | --- |
| `audit_sectors` | Setores auditáveis (id interno fixo; label editável na UI) | `id` (text), `label` |
| `audit_alerts` | Alertas (motivos de ligação) por setor; direção esperada alimenta o guardrail EFETUADA×RECEPTIVA | `id` (text), `sector_id` (FK), `label`, `context`, `pop_ref`, `expected_direction` |
| `audit_criteria` | Critérios de avaliação por alerta (o que a IA pontua) | `alert_id` (FK), `chave`, `label`, `weight`, `deflator`, `type`, `evaluation_type` (`auto`/manual), `referencia`, `exemplo` |
| `sector_aliases` | Mapeia nomes de setor vindos de RH/telefonia para o id canônico (vínculo sobrevive a renames) | `pattern_type`, `pattern_value`, `canonical_sector_id`, `priority`, `ativo` |

### 4.3 Pipeline Huawei / triagem

| Tabela | Propósito | Colunas-chave |
| --- | --- | --- |
| `fila_revisao_classificacao` | Fila de triagem: cada áudio baixado/enviado aguardando classificação, revisão ou auditoria | `input_hash`, `status` (`pending`/`auto_resolved`/`reviewed`/`audited`/`needs_manual_triage`/`monthly_capped`/`blocked_operator`/`downloaded`), `setor_previsto`/`alerta_previsto`/`operador_previsto`, `confianca`, `prioridade`, `metadata_json` (payload Huawei) |
| `huawei_sync_logs` | Registro por `call_id` baixado OU descartado — **descartes são tombstones permanentes** (não reaparecem em syncs futuros) | `call_id`, `status`, `failure_reason` (motivo do descarte), `discard_attempts` (anti-loop), `agent_id`, `operator_name` |
| `huawei_d_minus_1_runs` | Controle do pipeline D-1 por data (tentativas, retries, contadores) | `date_str` (PK), `status`, `attempts`, `manifest_rows_count`, `downloaded_count`, `skipped_quota_count`, `last_error` |
| `telefonia_sync_history` | Histórico de execuções do sync (manual e cron) com controle de pausa/cancelamento | `status`, `trigger_type`, `baixadas`, `enfileiradas`, `pause_requested`, `cancel_requested`, `last_heartbeat_at` |
| `automation_cycle_runs` | Execuções do motor de automação (ciclo, estágio, heartbeat — base da reconciliação de ciclos presos) | `source`, `status`, `stage`, `last_heartbeat_at`, `baixadas`, `auditadas`, `sync_result`/`audit_result` (jsonb) |

### 4.4 Transcrição

| Tabela | Propósito | Colunas-chave |
| --- | --- | --- |
| `transcript_candidates` | Candidatos de transcrição gerados pelo candidate selector, com scores e decisão | `audit_id`/`input_hash`, `provider`, `segments` (jsonb), `deterministic_score`, `judge_score`/`judge_reason` (LLM de desempate), `status`, `quality_flags`, `cross_signals` |
| `media_files` | Registro de mídia no storage (hash → backend físico + chave) | `file_hash`, `storage_backend` (`local`/`gcs`/`azure_blob`), `storage_key`, `content_type`, `size_bytes` |

### 4.5 Pessoas e acesso

| Tabela | Propósito | Colunas-chave |
| --- | --- | --- |
| `users` | Logins do sistema (bcrypt) | `username`, `password_hash`, `role` (`admin`/`supervisor`), `supervisor_name` (filtra o portal do supervisor) |
| `colaboradores` | Cadastro de operadores (RH + telefonia) — **`id_huawei` + `auditavel` controlam o que o sync baixa** (regra de negócio) | `nome`, `supervisor`, `setor`, `escala`/`tipo_escala`, `matricula`, `id_huawei`, `auditavel`, `status`, campos `*_telefonia` |

### 4.6 IA: calibração e RAG

| Tabela | Propósito | Colunas-chave |
| --- | --- | --- |
| `ai_feedback` | Correções/exemplos de calibração da IA (módulo Feedback IA); com pgvector ganha `transcricao_embedding vector(1536)` para busca semântica | `tipo`, `setor`, `criterio_id`, `situacao`, `correcao`, `justificativa`, `ativo` |
| `ai_prompts` | Prompts editáveis pela UI sem deploy (chave → JSON) | `chave` (PK), `valor` (jsonb) |
| `procedimento_chunks` | Chunks curados dos POPs para RAG; com pgvector ganha `embedding vector(1536)` | `source_path`, `setor`, `alert_id`, `section_title`, `chunk_index`, `content` |

### 4.7 Configuração e custo

| Tabela | Propósito | Colunas-chave |
| --- | --- | --- |
| `configuracoes` | Configuração dinâmica chave/valor lida em runtime (flags da automação, credenciais Huawei, cadência D-1, **`cost_kill_switch`**) | `chave` (PK), `valor`, `tipo`, `is_secret` |
| `api_usage_daily` | Telemetria do guardrail de custo (v1.3.114): contador diário de chamadas pagas por provider/categoria — alimenta os tetos de `cost_guard.py` (`docs/07` §4) | `data`+`provider`+`categoria` (chave), `chamadas` |

### 4.8 Trilhas de auditoria de configuração (audit logs)

Sete tabelas com o mesmo formato (`acao`, `entity_id`, `payload_antes/depois`
jsonb, `alterado_por`, `motivo`, `origem`): `audit_sectors_audit_log`,
`audit_alerts_audit_log`, `audit_criteria_audit_log`,
`sector_aliases_audit_log`, `ai_prompts_audit_log`, `colaboradores_audit_log`
e `configuracoes_audit_log` (esta com formato próprio: `chave`,
`valor_antes/depois`).
Toda edição de catálogo/configuração via UI deixa rastro aqui.

### 4.9 Referência/benchmark (legado ativo)

| Tabela | Propósito | Colunas-chave |
| --- | --- | --- |
| `ligacoes_auditadas` | Registro de referência de ligações processadas pela triagem (hash do arquivo + classificação de referência) | `hash_arquivo`, `nome_arquivo`, `setor_referencia`, `alerta_referencia`, `qualidade_referencia` (`boa`/`ruim`/`zerada`/`indefinida`) |
| `resultados_classificacao` | Resultado de cada execução de classificação sobre uma ligação (acurácia de setor/alerta por modelo/prompt) | `ligacao_id` (FK), `setor_previsto`, `alerta_previsto`, `confianca`, `modelo`, `acertou_setor`/`acertou_alerta` |
| `resultados_auditoria` | Resultado de auditoria vinculado a `ligacoes_auditadas` (histórico de benchmark) | `ligacao_id` (FK), `nota`, `detalhes_json` |

### 4.10 Fechamento mensal

| Tabela | Propósito | Colunas-chave |
| --- | --- | --- |
| `fechamento_layout_operadores` | Layout fixo da planilha de fechamento (bloco/posição/linha por operador) | `sequencia_bloco`, `posicao`, `id_visual`, `nome`, `supervisor`, `setor`, `nota_coluna`, `colaborador_id`, `ativo` |
| `fechamento_layout_overrides` | Overrides mensais por linha do layout (notas e campos editados à mão) | `layout_id` (FK), `mes`+`ano`, `nota_mot`/`nota_pa`/`nota_cli`/`nota_policia`, `*_override` |
| `fechamento_cadeia_contatos` | Notas mensais da cadeia de contatos por colaborador (fluxo anterior ao layout fixo) | `colaborador_id`, `mes`+`ano`, notas e `*_override` |

### 4.11 Infra do schema

| Tabela | Propósito |
| --- | --- |
| `schema_migrations` | Migrations aplicadas (`name`, `applied_at`) — controle do runner |
| `schema_metadata` | Metadados chave/valor do bootstrap (engine, último init, última migration) |

## 5. Views

Definidas em `backend/db/runtime_schema.py` (recriadas no init):

| View | Definição |
| --- | --- |
| `audits_com_colaborador` | `audits LEFT JOIN colaboradores` — auditorias com nome/matrícula/supervisor/setor do colaborador (consultas de dashboard/relatórios) |
| `ligacoes_boas` / `ligacoes_ruins` / `ligacoes_zeradas` | Recortes de `ligacoes_auditadas` por `qualidade_referencia` |

## 6. Extensões

| Extensão | Uso | Obrigatória |
| --- | --- | --- |
| `vector` (pgvector 0.8.0 na origem) | Colunas `ai_feedback.transcricao_embedding` e `procedimento_chunks.embedding` (`vector(1536)`) — RAG | Sim (sem ela o RAG degrada) |
| `pg_stat_statements` | Observabilidade de queries | Não |
| `plpgsql` | Builtin do PostgreSQL | — |
