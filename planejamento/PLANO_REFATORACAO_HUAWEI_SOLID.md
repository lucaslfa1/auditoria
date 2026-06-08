# Plano de Refatoração SOLID de `backend/core/huawei_sync.py`

## Status Atual (24/05/2026)
- [x] **Etapa 0 — Preparação:** Criada estrutura `backend/core/huawei/`. Branch de backup criada.
- [x] **Etapa 1 — Helpers puros:** Extraídas funções sem efeitos colaterais para `download_candidates.py` e `telemetry.py`.
- [ ] **Etapa 2 — Configuração & lock**
- [ ] **Etapa 3 — Identidades & skip rules**
- [ ] **Etapa 4 — Discovery**
- [ ] **Etapa 5 — Download**
- [ ] **Etapa 6 — Pré-triagem & triagem & enqueue**
- [ ] **Etapa 7 — Classificação automática (opt-in)**
- [ ] **Etapa 8 — Orquestrador**
- [ ] **Etapa 9 — Shim & limpeza**

---

## Arquitetura alvo (SOLID)

```text
backend/core/huawei/
├── __init__.py
├── protocols.py            # interfaces (Protocol classes)
├── config.py               # [grupo 1] HuaweiConfigLoader
├── execution_lock.py       # [grupo 2] HuaweiSyncLock
├── discovery.py            # [grupo 3] (mover huawei_discovery.py para cá)
├── identity_resolver.py    # [grupo 4] OperatorIdentityResolver
├── skip_rules.py           # [grupo 5] CallSkipPolicy (+ subclasses por setor)
├── download_candidates.py  # [grupo 6] DownloadCandidateBuilder (CONCLUÍDO)
├── download_chain.py       # [grupo 7] (mover huawei_download_chain.py)
├── direction_pretriage.py  # [grupo 8] AudioDirectionPretriage
├── sector_triage.py        # [grupo 9] SectorTriageService
├── enqueue.py              # [grupo 10] CallEnqueueService
├── auto_classifier.py      # [grupo 11] AutoClassifierService (opcional)
├── telemetry.py            # [grupo 12] SyncCounters + ProgressNotifier (CONCLUÍDO)
└── orchestrator.py         # [grupo 14] HuaweiSyncOrchestrator + executar_sync_huawei
```

## Plano de execução detalhado

### Etapa 2 — Configuração & lock
- Criar `config.py` com classe `HuaweiConfigLoader` (encapsula `_load_config`, `_missing_credentials`, `_ensure_enabled`, `_env_flag`, `_runtime_int_config`).
- Criar `execution_lock.py` movendo `_HuaweiSyncExecutionLock` como `HuaweiSyncLock` (público). Receber `conn_factory` no construtor.

### Etapa 3 — Identidades & skip rules
- Criar `identity_resolver.py` com `OperatorIdentityResolver` agregando funções de resolução de identidade e setor.
- Criar `skip_rules.py` com `SkipPolicy` Protocol + 6 implementações concretas + `CompositeSkipPolicy`. Migrar `_should_skip_call`.

### Etapa 4 — Discovery (já extraído, só consolidar)
- Mover `huawei_discovery.py` para `huawei/discovery.py`.
- Mover `_buscar_chamadas_por_regra`, `_buscar_chamadas_globais`, etc., para `discovery.py` como métodos do serviço.

### Etapa 5 — Download (já extraído, só consolidar)
- Mover `huawei_download_chain.py` para `huawei/download_chain.py`. Sem mudança de API.

### Etapa 6 — Pré-triagem & triagem & enqueue
- Criar `direction_pretriage.py` com `AudioDirectionPretriage`.
- Criar `sector_triage.py` com `SectorTriageService`.
- Criar `enqueue.py` com `CallEnqueueService`.

### Etapa 7 — Classificação automática (opt-in)
- Criar `auto_classifier.py` com `AutoClassifierService` movendo lógicas do Whisper/GPT.

### Etapa 8 — Orquestrador
- Criar `orchestrator.py` com `HuaweiSyncOrchestrator` recebendo todos os serviços via construtor.
- Migrar `_processar_candidato` para método privado do orquestrador.
- Migrar `executar_sync_huawei` para método `run(...)`.

### Etapa 9 — Shim & limpeza
- Reduzir `backend/core/huawei_sync.py` a um shim que re-exporta `executar_sync_huawei` (mantém compatibilidade com 30 consumidores).
- Rodar testes completos: `pytest backend/tests/`.
