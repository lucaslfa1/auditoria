# Fluxo de Processos — Auditoria NSTECH

**Última validação:** 2026-05-27 (versão `1.3.85`, branch `main`)
**Método:** leitura direta do código-fonte (routers, motor, repositórios). A doc anterior só descrevia o caminho manual `/api/audit` e estava desatualizada quanto a Telefonia, Triagem e Automação.

> **Para quem está confuso:** Telefonia, Triagem, Automação e Auditoria parecem fluxos separados na sidebar, mas não são. **A Automação USA a Telefonia e a Triagem internamente.** A sidebar mostra a mesma fila por ângulos diferentes. Este documento descreve os fluxos reais.

---

## 1. Glossário das 4 entidades

| Entidade | É um... | O que faz | Onde mora |
|---|---|---|---|
| **Telefonia** | Conector | Baixa gravações da Huawei (OBS / VDN) e abastece a fila de triagem | `backend/routers/telefonia.py`, `backend/core/huawei_sync.py`, `backend/core/huawei_d_minus_1.py`, `src/features/telefonia/` |
| **Triagem** | Fila central | Persiste 1 row por chamada com estado de classificação (setor/alerta/operador previstos) | tabela `fila_revisao_classificacao`, `backend/repositories/classification_review.py`, `src/features/classifier/` |
| **Automação** | Orquestrador | Encadeia Telefonia → Classificação IA → Auditoria IA em um único ciclo | `backend/core/automation_engine.py`, `backend/core/automation.py`, `backend/routers/automation.py`, `src/features/automacao/` |
| **Auditoria** | Resultado + ação | Cria/edita uma `audits` row, gera score, sincroniza para arquivos salvos | `backend/routers/audit.py`, `backend/core/audit.py`, `backend/db/database.py:persist_audit_artifacts`, `src/features/audit/` |

---

## 2. Fluxo automatizado (ciclo completo)

Este é o que roda sozinho via Cloud Scheduler ou via botão **"Rodar agora"** na tela Automação.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  GATILHO                                                                │
│   • Cloud Scheduler → POST /api/automation/cron/run (com Bearer token)  │
│   • Admin clica "Rodar agora" → POST /api/automation/run-now            │
│   • Loop residente em processo (opcional, ENABLE_IN_PROCESS_AUTOMATION) │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
       core/automation_engine.py :: run_automation_cycle(source)
                              │
                              ├─── adquire row-lock automation_engine_lock
                              │    (TTL 30 min; "skipped" se outro ciclo já roda)
                              │
                              ├─── reconcilia ciclos "stale" (heartbeat > 300s)
                              │
                              ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │  FASE 1 — SYNC D-1 (Huawei OBS)                                    │
   │  core/huawei_d_minus_1.py :: executar_d_minus_1_pipeline()         │
   │   • Lock próprio: huawei_d1_run_lock                               │
   │   • Lookback configurável (default 3 dias)                         │
   │   • Para cada date_str: lista manifesto OBS, baixa áudio, monta    │
   │     metadata (huawei_begin_time, operator_id, sector_id previsto)  │
   │   • Insere/atualiza `fila_revisao_classificacao` com origem=       │
   │     huawei_sync, status=downloaded                                 │
   │   • Atualiza `huawei_d_minus_1_runs` (status, attempts, coverage)  │
   │  RESULTADO: N gravações novas na fila + áudios em                  │
   │             storage/classified_audio/yyyy/mm/<hash>.wav             │
   └────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │  FASE 2 — CLASSIFICAÇÃO IA                                         │
   │  core/huawei_sync.py :: _classificar_audio_huawei() +              │
   │                         _aplicar_auto_classificacao()              │
   │   • Roda para cada item ainda sem setor/alerta                     │
   │   • Whisper transcreve + GPT-4o classifica (setor + alerta)        │
   │   • Confiança ≥ threshold → status='auto_resolved'                 │
   │   • Confiança baixa OU motivos_revisao → status='pending'          │
   │     (vai parar na tela Triagem aguardando humano)                  │
   │   • Operador Huawei sem cadastro → status='blocked_operator'       │
   │   • Setor não-telefonia / direção inválida → ignorado no insert    │
   │     (filtrado já no D-1; documentado em                            │
   │     core/huawei_direction.py)                                      │
   └────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │  FASE 3 — AUDITORIA IA (em lote)                                   │
   │  core/automation.py :: audit_all_pending()                         │
   │   • Lê fila com status='ready_for_audit' (filtro virtual que       │
   │     inclui auto_resolved + reviewed)                               │
   │   • Batch size configurável (default 3, máx 50)                    │
   │   • Time budget configurável (default 480s, máx 540s)              │
   │   • Por item:                                                      │
   │       ├─ resolve operador (OperatorGatekeeper)                     │
   │       ├─ checa cota mensal (QuotaGatekeeper) → monthly_capped      │
   │       ├─ valida direção (AutomationGatekeeper)                    │
   │       ├─ chama core/audit.py :: process_audit_with_ai()            │
   │       │   (transcreve + avalia critérios + calcula score)          │
   │       ├─ persist_audit_artifacts() → cria audits row +            │
   │       │   _attach_audio_to_audit_record() (GCS read-back v1.3.85)  │
   │       └─ atualiza fila status='audited' + sincroniza               │
   │          arquivos_salvos                                           │
   └────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │  FASE 4 — ARQUIVOS SALVOS (revisão admin)                          │
   │  core/saved_files_sync_queue.py → repositories/saved_files.py      │
   │   • Auditorias entram com status='awaiting_pair'                   │
   │   • Aparecem na sidebar "Arquivos Salvos" como rascunho editável   │
   │   • Admin revisa e clica "Enviar ao supervisor"                    │
   │     → POST /api/audit/{audit_id}/promote-to-pending-approval       │
   │     → status='pending_approval', supervisor passa a enxergar       │
   └────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │  FASE 5 — SUPERVISOR (humano)                                      │
   │   Portal do Supervisor (/supervisor)                               │
   │    • approve  → status='approved'                                  │
   │    • contest  → status='contestation_pending_review'               │
   │       (admin avalia → contestation_accepted ou rejected)           │
   └────────────────────────────────────────────────────────────────────┘
```

**Status finais persistidos:**
- `audits.status`: `awaiting_pair` → `pending_approval` → `approved` (ou `contestation_*` / `discarded`)
- `fila_revisao_classificacao.status`: `audited` (terminal) ou `monthly_capped` / `blocked_operator` / `needs_manual_triage`

---

## 3. Fluxo manual — upload avulso

Caminho usado quando o auditor pega um áudio à mão (não veio da Huawei).

```
┌─────────────────────────────────────────────────────────────────────────┐
│  UI: /auditoria (raiz) — AuditWorkspace                                 │
│   1. Seleciona setor + alerta + operador                                │
│   2. Faz upload de áudio (mp3/wav, máx 50MB) ou PDF                     │
│   3. Submit → POST /api/audit (FormData)                                │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
       routers/audit.py :: run_audit()
                              │
                              ├─── valida operador (resolve_auditable_colaborador)
                              ├─── checa cota mensal do operador (HTTP 429 se exceder,
                              │    a menos que force_override=true)
                              ├─── revalida critérios oficiais do alerta no DB
                              │
                              ▼
       core/audit.py :: process_audit_with_ai()
        • Hash SHA-256 da entrada (mime + audio + alert + operador + setor)
        • Cache: get_audit_by_hash() (DETERMINISTIC_MODE)
        • Transcrição: core/transcription.py + transcription_orchestrator.py
            engine default = "fast" (Azure Fast Transcription)
            fallback: fast → whisper → gpt4o_diarize → sdk
            seleção entre candidatos: transcription_judge.py (LLM tiebreak)
        • Análise de qualidade: audio/diarization_quality.py
        • Avaliação IA: core/evaluation.py :: evaluate_with_ai_priority()
            Azure GPT-4o (primary) → Google Gemini (fallback)
            Prompts: backend/config/prompts.json
        • Score = Σ(obtidos pass=1 / partial=0.5 / fail=0) / Σ(máx)
                              │
                              ▼
       database.persist_audit_artifacts() — background thread
        • save_audit() insere row em `audits` (status='awaiting_pair')
        • _attach_audio_to_audit_record() faz upload GCS + read-back
          (v1.3.85: AudioUploadVerificationError se size mismatch)
        • _sync_arquivo_salvo_for_audit() enfileira sincronização
          assíncrona com `arquivos_salvos`
                              │
                              ▼
                  AuditResult devolvido ao frontend
                  (já com score, summary, transcrição, audio_quality)
```

A partir daí o fluxo converge com a Fase 4 acima (Arquivos Salvos → Supervisor).

---

## 4. Os 3 disparadores de Telefonia/Automação

| Quem dispara | Endpoint | O que faz | Background? |
|---|---|---|---|
| **Cloud Scheduler** (cron) | `POST /api/automation/cron/run` (com Bearer token) | Ciclo **completo** D-1 → classifica → audita | Sim |
| **Admin: "Rodar agora"** (`/automacao`) | `POST /api/automation/run-now` | Mesmo ciclo completo | Foreground (request aguarda) |
| **Admin: "Sync manual"** (`/telefonia`) | `POST /api/telefonia/sync/manual` | **Só Fase 1** (baixa e classifica). NÃO audita. | Sim |

> **Lock importante:** os 3 caminhos compartilham locks. Disparar dois ao mesmo tempo retorna `409 "Automacao ja esta em andamento"`. Lock principal: `automation_engine_lock` em `configuracoes`. Locks secundários: `huawei_d1_run_lock`, `sync_lock`.

Tabela de auditoria de ciclos: `automation_cycle_runs` (id, source, status, stage, started_at, finished_at, last_heartbeat_at, baixadas, auditadas, error_message, sync_result, audit_result, result).

---

## 5. Estados da fila de triagem

`fila_revisao_classificacao.status` (em `db/domain_constants.py`):

| Status | Significado | Quem chega aqui | Quem sai daqui |
|---|---|---|---|
| `downloaded` | Áudio baixado, ainda não classificado | Fase 1 (D-1) | Fase 2 |
| `pending` | Classificação tem baixa confiança → precisa humano | Fase 2 com `needs_review=true` | Auditor reclassifica via Triagem |
| `auto_resolved` | Classificação confiante | Fase 2 com `confianca ≥ threshold` | Fase 3 (auditoria automática) |
| `reviewed` | Humano revisou na Triagem | UI Classifier | Fase 3 |
| `ready_for_audit` | **Filtro virtual** (= `auto_resolved` + `reviewed`) | — | leitura por `audit_all_pending()` |
| `audited` | Auditoria concluída | Fase 3 / Telefonia "Auditar" / `/api/audit` direto | terminal |
| `monthly_capped` | Cota mensal do operador atingida (2/mês default) | Fase 3 ou pre-download | terminal (até novo mês) |
| `needs_manual_triage` | Setor não-telefonia ou direção inválida | Fase 3 ou Telefonia | Auditor decide |
| `blocked_operator` | Operador Huawei sem cadastro em `colaboradores` | Fase 2 ou Fase 3 | Admin cadastra operador |

---

## 6. Estados da auditoria

`audits.status`:

| Status | Significado |
|---|---|
| `awaiting_pair` | Recém-criada, ainda em revisão pelo admin (rascunho em Arquivos Salvos). Não aparece pro supervisor. |
| `pending_approval` | Admin promoveu manualmente; supervisor enxerga e pode aprovar/contestar |
| `approved` | Supervisor aprovou |
| `contestation_pending_review` | Supervisor contestou; admin precisa avaliar |
| `contestation_accepted` | Admin acolheu contestação (alias antigo: `contested`) |
| `discarded` | Soft-delete (sai da cota mensal, do dashboard, do painel do supervisor). Reversível via restore. |

Promoção `awaiting_pair → pending_approval` é **sempre manual** via `POST /api/audit/{audit_id}/promote-to-pending-approval` (acionada pelo botão "Enviar ao supervisor" em Arquivos Salvos).

---

## 7. Mapa UI ↔ Backend (sidebar)

Rotas reais conforme `src/App.tsx`. View default (vazia) = `automacao` (não mais `audit`).

| Sidebar | View | Backend | Quem mostra |
|---|---|---|---|
| Auditoria | `audit` (raiz `/`) | `POST /api/audit` | `AuditWorkspace` — upload manual |
| Triagem | `classifier` | `POST /api/classify`, `repositories/classification_review.py` | `Classifier` — fila com items `pending`/`needs_manual_triage` |
| Telefonia | `telefonia` | `/api/telefonia/*` | `TelefoniaPage` (SyncPanel + RecordingsList + HuaweiCredentialsCard) |
| Automação | `automacao` | `/api/automation/*` | `AutomacaoPage` (Hero + ConfigPanel + HealthPanel + AuditoriasDoMes + RuntimePanel) |
| Arquivos Salvos | `salvos` | `/api/salvos/*` | `SavedFiles` — rascunhos editáveis |
| Supervisor | `supervisor` | `/api/gestores/*` | `SupervisorPortal` |
| Pendentes | `pending-dispatch` | `/api/audit/{id}/promote-...` | `PendingDispatch` — fila awaiting_pair → enviar em lote |
| Fechamento | `fechamento` | `/api/fechamento/*` | `FechamentoPage` |
| Dashboard | `dashboard` | `/api/analytics/*` | `Dashboard` (admin) |
| Performance | `performance` | `/api/analytics/*` | `PerformanceDashboard` |
| Operadores | `colaboradores` | `/api/operadores/*` | `ColaboradoresPage` |
| Configurações | `settings` | configs em `configuracoes` | `Settings` (admin) |
| Contestações | `review` | `/api/gestores/auditorias/.../contest` | `ReviewPage` (admin) |
| IA | `ia` | `/api/ai-feedback/*` + `/api/golden-dataset/*` | `AIFeedbackPage` (admin) |
| Admin → Critérios | `admin` | `repositories/admin_criteria.py` | `AdminCriteriaPage` |
| Admin → Apelidos | `admin-aliases` | `/api/admin/sector-aliases` | `AdminSectorAliasesPage` |
| Admin → Prompts | `admin-prompts` | `/api/admin/ai-prompts/*` | `AdminAIPromptsPage` |

---

## 8. Endpoints por módulo (validados em 2026-05-27)

### `/api/telefonia` — Telefonia
| Método | Rota | Função |
|---|---|---|
| POST | `/sync/manual` | Dispara sync com janela manual ou horas retroativas |
| POST | `/sync/cancel` | Cancela sync em andamento |
| POST | `/sync/clear` | Limpa relatório do último sync |
| GET | `/sync/status` | Estado atual + credenciais + flags |
| GET | `/sync/history` | Histórico de execuções (`telefonia_sync_history`) |
| GET | `/recordings` | Lista gravações Huawei na fila |
| DELETE | `/recordings` | Limpa pendentes (não auditados) |
| DELETE | `/recordings/{hash}` | Remove uma gravação |
| GET | `/recordings/{hash}/audio` | Stream do áudio classificado |
| POST | `/recordings/{hash}/triage` | Envia gravação para triagem manual |
| POST | `/recordings/{hash}/classify` | Roda classificação IA num áudio Huawei |
| POST | `/recordings/{hash}/audit` (202) | Inicia auditoria em background pra um item |
| GET | `/recordings/{hash}/audit-status` | Polling do progresso |
| DELETE | `/recordings/{hash}/audit` | Cancela auditoria em andamento |
| POST | `/sync/d-minus-1` | Dispara pipeline D-1 ad-hoc |
| POST | `/sync/d-minus-1/manual` | Versão manual com data específica |
| GET | `/sync/d-minus-1/status` | Status D-1 |
| GET | `/sync/d-minus-1/summary` | Resumo agregado |
| POST | `/cron/sync` | Gatilho do Cloud Scheduler pro coletor D-1 (1x/dia) |
| POST | `/sync/reset-lock` | Quebra `sync_lock` travado |
| GET | `/debug/obs` + `/debug/obs/search` | Diagnóstico OBS |

### `/api/automation` — Motor de Automação
| Método | Rota | Função |
|---|---|---|
| POST | `/engine/toggle` | Liga/desliga atomicamente (`automacao_hibrida_ativa`, `huawei_d1_enabled`) |
| GET | `/engine/status` | Estado completo + health report + indicadores |
| POST | `/run-now` | Dispara ciclo completo no request (admin) |
| POST | `/cron/run` | Gatilho do Cloud Scheduler (Bearer token) |
| POST | `/audit-all` | Roda só Fase 3 (auditar pendentes) |
| GET | `/status` | Progresso da fase de auditoria |
| POST | `/pause` / `/resume` / `/cancel` | Controles em runtime |
| POST | `/flush-awaiting-pairs` | Promove `awaiting_pair` antigos para `pending_approval` |
| POST | `/huawei-sync/manual` | Shim legado → `/api/telefonia/sync/manual` |

### `/api/audit` — Auditoria (upload manual)
| Método | Rota | Função |
|---|---|---|
| POST | `/api/audit` | Upload de áudio/PDF + critérios → AuditResult |
| GET | `/api/audit/{id}/audio` | Stream do áudio salvo |
| POST | `/api/audit/{id}/discard` | Soft-delete (admin) |
| POST | `/api/audit/{id}/restore` | Reverte soft-delete |
| POST | `/api/audit/{id}/promote-to-pending-approval` | Envia ao supervisor |
| POST | `/api/audit/reevaluate` | Re-avalia com transcrição editada |
| POST | `/api/audit/regenerate-summary` | Regera resumo+feedback |
| PUT/GET | `/api/audit/draft/{hash}` | Salva/lê rascunho do auditor |

### `/api/salvos` — Arquivos Salvos (rascunhos)
| Método | Rota | Função |
|---|---|---|
| POST | `""` | Cria item avulso |
| GET | `""` | Lista (auditorias vinculadas + uploads soltos) |
| GET | `/{id}` | Detalhe |
| PUT | `/{id}` | Atualiza conteúdo/score/metadata (e se vinculado a audit_id, propaga pro `audits`) |
| DELETE | `/{id}` | Remove rascunho |

### Outros (referência)
- `/api/auth/*` — login, logout, /me
- `/api/criteria/*` — catálogo de critérios
- `/api/classify` — classificação em lote (módulo Triagem)
- `/api/gestores/*` — Portal do Supervisor (aprovar, contestar, exportar gestores)
- `/api/operadores`, `/api/supervisores`, `/api/analytics`, `/api/fechamento`, `/api/ai-feedback`, `/api/golden-dataset`, `/api/admin/ai-prompts`, `/api/admin/sector-aliases`

---

## 9. Pontos onde o sistema engana o olhar

1. **Telefonia ≠ tabela própria.** A lista "Gravações" em `/telefonia` é um filtro sobre `fila_revisao_classificacao` com `origem='huawei_sync'`. Sumiu da Telefonia = mudou de status na fila (geralmente `audited` ou `monthly_capped`).
2. **"Auditar" na Telefonia ≠ ciclo automático.** Clicar "Auditar" numa gravação cria uma task isolada em background (`_start_audit_task`), não dispara D-1 nem afeta o lock global da Automação.
3. **3 locks distintos** rodam em paralelo:
   - `automation_engine_lock` — ciclo completo
   - `huawei_d1_run_lock` — Fase 1 isolada
   - `sync_lock` — sync manual da Telefonia
   Daí o status `skipped` aparecer com mensagens diferentes dependendo do gatilho.
4. **Default da view é `automacao`**, não `audit`. Quem cair em `/` vai pra automação direto.
5. **`audits.status='awaiting_pair'` é o estado natural** — qualquer auditoria nova começa nele, manual ou automática. Só vira `pending_approval` por ação humana explícita (botão).
6. **Cota mensal (`huawei_cota_max_por_operador_mes`, default 2)** é checada **três vezes**: no upload manual (`/api/audit`), no pre-download D-1 e dentro de `audit_all_pending`. Promover `awaiting_pair → pending_approval` também valida.
7. **Filtros silenciosos no D-1** (em `core/huawei_direction.py`): setor não-telefonia, receptiva em setor de risco, direção desconhecida. Esses são contados como `ignoradas_*` no relatório, mas não viram row na fila — então parecem "sumir".
8. **Filas paralelas que não aparecem na sidebar:**
   - `automation_cycle_runs` — histórico de ciclos
   - `huawei_d_minus_1_runs` — histórico do pipeline D-1 (1 row por `date_str`)
   - `huawei_sync_logs` — 1 row por `call_id` (anti-redownload)
   - `telefonia_sync_history` — histórico de syncs manuais
9. **`fila_revisao_classificacao.status='ready_for_audit'` não existe na coluna** — é filtro virtual em `listar_fila_revisao_classificacao()` que combina `auto_resolved + reviewed`.

---

## 10. Tabelas principais

| Tabela | Conteúdo | Quem grava | Quem lê |
|---|---|---|---|
| `audits` | Auditorias finalizadas (score, summary, transcrição, metadata) | `save_audit()`, `update_audit_*` | Frontend, supervisor, dashboard, exports |
| `audit_media_files` | Audio paths (GCS ou local) por audit | `_attach_audio_to_audit_record()` | `GET /api/audit/{id}/audio` |
| `arquivos_salvos` | Rascunho editável (espelho de `audits` + uploads avulsos) | `_sync_arquivo_salvo_for_audit()` | Sidebar "Arquivos Salvos" |
| `fila_revisao_classificacao` | Fila central de triagem | Telefonia, Classificação IA, audit_all_pending | Triagem, Telefonia, Automação |
| `automation_cycle_runs` | Histórico de ciclos do motor | `_persist_cycle_update()` | `/api/automation/engine/status`, health panel |
| `huawei_d_minus_1_runs` | Histórico do pipeline D-1 (por data) | `HuaweiDMinus1Tracker` | Telefonia D-1 dashboard |
| `huawei_sync_logs` | Anti-redownload (call_id → status) | sync e D-1 | sync e D-1 |
| `telefonia_sync_history` | Histórico de syncs manuais | `_run_manual_sync()` | `/api/telefonia/sync/history` |
| `colaboradores` | Operadores auditáveis | `/api/operadores` | resolução de operador em todo lugar |
| `audit_sectors` / `audit_alerts` / `audit_criteria` | Catálogo de critérios | `/api/admin/*` | `/api/criteria/export` |
| `configuracoes` | Flags runtime + locks | `database.update_config()` | tudo |
| `configuracoes_audit_log` | Audit-log de mudanças em `configuracoes` | toggle atômico, etc | Settings |

---

## 11. Stack (validação 2026-05-27)

| Camada | Tecnologia |
|---|---|
| Frontend | React 19 + TypeScript + Vite + Tailwind CSS 4 |
| Backend | FastAPI + Python 3.11+ |
| Banco | PostgreSQL via Neon (`auditoria-nstech-2`, host `ep-aged-river-acr5e219`). **Não usa mais Supabase.** Driver: psycopg2 com DictCursor. |
| Transcrição | Default `fast` (Azure Fast Transcription REST). Fallback chain: fast → whisper → gpt4o_diarize → sdk. Engine opcional `hybrid_dual`. |
| Avaliação IA | Azure OpenAI GPT-4o (primary) → Google Gemini (fallback) |
| Storage de áudio | GCS bucket `auditoria-nstech-audios` (region `southamerica-east1`, soft-delete 7d). Fallback local: `backend/storage/audits/audio/`. Áudios classificados pendentes: `backend/storage/classified_audio/`. |
| Hospedagem | Cloud Run `auditoria` (region `southamerica-east1`). URL: `https://auditoria-tqr7bp67na-rj.a.run.app` |
| Auth | Cookie `nstech_session` HMAC-SHA256 (TTL 8h) + bcrypt; roles `admin`/`supervisor` |
| Exportação | openpyxl (XLSX), python-docx (DOCX), reportlab (PDF) |

---

## 12. Quando atualizar esta doc

Atualize sempre que mexer em:
- Estrutura da fila (`fila_revisao_classificacao`) ou seus status (`db/domain_constants.py`)
- Cadeia D-1 / sync Huawei
- Motor de automação ou seus locks
- Rotas em `routers/telefonia.py`, `routers/automation.py`, `routers/audit.py`
- Schema das tabelas centrais (audits, automation_cycle_runs, arquivos_salvos)
- Default da view inicial em `src/App.tsx`

Validação rápida: rode `Grep "@router\.(get|post|put|delete)"` nos routers e compare com a Seção 8.

> Quem alterar o comportamento do sistema deve **atualizar esta doc no mesmo PR** que muda o código.
