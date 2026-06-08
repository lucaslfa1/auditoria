# Migração BBM → Distribuição

**Data:** 2026-05-18
**Autor:** Lucas Afonso / Claude Opus 4.7
**Status:** Aprovado para implementação (v1.3.74)

## Contexto

O setor **BBM** foi absorvido operacionalmente por **Distribuição**. O sistema é o único lugar que ainda mantém BBM como entidade separada. Esta migração reflete a realidade organizacional no software.

### Estado atual no banco (verificado em 2026-05-18)

| Métrica | BBM | DISTRIBUICAO |
|---|---|---|
| Auditorias com `sector_id` | **0** | (preservadas) |
| Colaboradores com `setor` | **0** | (preservados) |
| Linha em `audit_sectors` | 1 (`id=bbm`, `label=BBM`) | 1 |
| Alertas em `audit_alerts` | 10 (`BBM-*`) | 10 (`DISTRIBUICAO-*`) |
| Critérios em `audit_criteria` | 156 | 156 |

**Paridade verificada:** cada `BBM-X` tem gêmeo `DISTRIBUICAO-X` com **mesmo `pop_ref` e mesmos labels/pesos** de critérios. A migração não perde regra de negócio.

## Estratégia (decidida em brainstorming)

**Hard remove operacional + alias de garantia + snapshot recuperável.**

Três camadas independentes que se complementam:

1. **DELETE** dos dados BBM (audit_log automático preserva snapshots em `audit_*_audit_log`).
2. **Alias** em `sector_aliases` redireciona qualquer fonte externa que ainda envie "bbm".
3. **Snapshot JSON** versionado em git permite reverter em 1 comando se a decisão for revertida.

## Arquitetura

```
                 ┌──────────────────────────────────────────────┐
                 │  Fonte externa (Huawei sync, RH, telefonia)  │
                 │  envia setor "bbm"                           │
                 └────────────────────┬─────────────────────────┘
                                      │
                                      ▼
                 ┌──────────────────────────────────────────────┐
                 │  sector_aliases (DB)                         │
                 │  pattern_value='bbm' setor_exact             │
                 │  canonical_sector_id='distribuicao'          │
                 └────────────────────┬─────────────────────────┘
                                      │
                                      ▼  (resolução transparente)
                 ┌──────────────────────────────────────────────┐
                 │  Sistema vê apenas "distribuicao"            │
                 │  audit_sectors / audit_alerts / criteria     │
                 │  só têm linhas DISTRIBUICAO-*                │
                 └──────────────────────────────────────────────┘

Em paralelo (defense-in-depth a nível de alert_id):
                 ┌──────────────────────────────────────────────┐
                 │  classification._ALERT_ID_ALIASES            │
                 │  BBM-PARADA-MOT → DISTRIBUICAO-PARADA-MOT    │
                 │  (10 entradas; alias simétrico ao BAS-POLI)  │
                 └──────────────────────────────────────────────┘
```

## Componentes

### 1. Migration step (`backend/db/migration_steps/m20260518_002_migrate_bbm_to_distribuicao.py`)

**Responsabilidade:** executar a migração de dados no DB em transação única, idempotente.

**Ordem de operações:**

Fase A — fora da transação DB:

1. **Pre-flight checks** — aborta se houver `audits.sector_id='bbm'` ou `colaboradores.setor ILIKE 'bbm'` (defensivo contra deploy fora de sincronia).
2. **Snapshot dump** — escreve `db/seeds/_archived/2026-05-18-bbm-sector.json` se não existir ainda (idempotente; lê dados ANTES de qualquer DELETE).

Fase B — DML via repositories (cada chamada faz seu próprio commit):

> **Nota arquitetural:** `repositories.admin_criteria.delete_*` e `repositories.sector_aliases.create_alias` **commitam internamente** (cada chamada é sua própria transação). Não é possível agrupar tudo em uma transação Postgres sem reescrever os repositories. O design aceita "múltiplas transações em ordem segura" porque (a) cada commit deixa o sistema em estado FK-consistente; (b) `audit_*_audit_log` registra cada passo, permitindo replay/rollback; (c) execução é idempotente — re-rodar após falha parcial completa o que faltou.

3. **Insert alias** via `repositories.sector_aliases.create_alias()`. Antes de chamar, verificar com `list_aliases()` se já existe entrada com `(pattern_type='setor_exact', pattern_value='bbm')` — `sector_aliases` não tem UNIQUE constraint nesse par; idempotência é garantida pelo SELECT prévio.
   - Parâmetros: `pattern_type='setor_exact'`, `pattern_value='bbm'`, `canonical_sector_id='distribuicao'`, `priority=100`, `descricao='Migração BBM → Distribuição em 2026-05-18'`, `ativo=True`, `alterado_por='system_migration_v1.3.74'`, `motivo='BBM absorvido por Distribuição'`, `origem='migration'`.
4. **DELETE cascata por nível** (respeita FK; ordem children → parent):
   - 4a. Iterar critérios via `repositories.admin_criteria.get_criteria(alert_id=...)` para cada alerta `BBM-*` e chamar `delete_criterion()` (156 chamadas; cada uma faz seu commit e grava `audit_criteria_audit_log`).
   - 4b. Para cada alerta `BBM-*`, chamar `delete_alert()` (10 chamadas; idem `audit_alerts_audit_log`).
   - 4c. Chamar `delete_sector(id='bbm', ...)` (1 chamada; idem `audit_sectors_audit_log`).
   - Cada chamada passa `alterado_por='system_migration_v1.3.74'`, `motivo='Migração BBM → Distribuição (v1.3.74)'`, `origem='migration'`.

Fase C — pós-commit (Python):

5. **Invalidar caches** `lru_cache` de `classification.load_audit_criteria_catalog`, `build_sectors_and_alerts_prompt`, `get_alert_lookup_by_id`, e `sector_aliases.clear_cache()`.

**Idempotência:** Cada etapa verifica existência antes do DELETE. Se a migration for interrompida no meio (ex: deploy reiniciado), próxima execução retoma do ponto exato — passos já concluídos viram no-op. O snapshot da Fase A fica órfão se nada foi deletado (benigno; será reusado na próxima tentativa).

**Garantia de consistência:** Mesmo com múltiplas transações, a ordem children → parent garante que o DB nunca fica em estado FK-inválido. Caso o processo morra entre 4a e 4b, o sistema fica com "alguns critérios BBM ainda existentes apontando para alertas BBM ainda existentes" — estado válido, apenas parcialmente migrado.

### 2. Snapshot arquivado (`backend/db/seeds/_archived/2026-05-18-bbm-sector.json`)

**Estrutura:**

```json
{
  "snapshot_date": "2026-05-18",
  "reason": "BBM absorvido por Distribuição. Snapshot para revert eventual.",
  "version_log": "logs/versions/1.3.74-migracao-bbm-distribuicao.md",
  "sector": { "id": "bbm", "label": "BBM" },
  "alerts": [ /* 10 linhas de audit_alerts */ ],
  "criteria": [ /* 156 linhas de audit_criteria */ ]
}
```

### 3. Restore script (`backend/db/seeds/_archived/restore_bbm.py`)

**Uso (se mudarem de ideia):**

```bash
python backend/db/seeds/_archived/restore_bbm.py
```

Script lê o JSON, faz UPSERT no DB, remove o alias, invalida caches. Idempotente. Documenta em audit_log com `motivo='Restore BBM via snapshot 2026-05-18'`.

### 4. Refactor cirúrgico do código backend

| Arquivo | Mudança |
|---|---|
| `backend/classification.py` | Remove `"bbm"` de `_OPERATIONAL_SIBLINGS` (linha ~263), `_OPERATIONAL_SECTORS` (linha ~448), `_OPERATIONAL_ALERT_PREFIXES` (linha ~454), mapa `_OPERATIONAL_ALERT_BY_KIND` (linhas 808-824). Adiciona 10 entradas em `_ALERT_ID_ALIASES` com comentário de origem. |
| `backend/core/config.py` | Remove linha `"bbm": "distribuicao"` do `sector_mapping` (linha 196) — agora resolvido via DB alias. |
| `backend/core/evaluation.py` | Procura tabela de pesos por setor BBM se existir; remove. |
| `backend/audit_evaluator.py` | Idem. |
| `backend/core/operator_filters.py` | Remove regras BBM-específicas. |
| `backend/core/gestores_mapping.py` | Remove entradas BBM. |
| `backend/transcription_providers/common.py` | Remove keywords BBM-específicas (se houver). |

**Aliases em `_ALERT_ID_ALIASES`** (10 entradas, simétrico ao alias `BAS-POLICIAL → BAS-PRIORITARIO-POLICIA` que já existe; com comentário de origem):

```python
# Migração BBM → Distribuição em 2026-05-18 (v1.3.74) — manter por
# defense-in-depth caso IA ou fonte externa devolva alert_id antigo.
"BBM-PARADA-MOT": "DISTRIBUICAO-PARADA-MOT",
"BBM-PARADA-CLI": "DISTRIBUICAO-PARADA-CLI",
"BBM-DESVIO-MOT": "DISTRIBUICAO-DESVIO-MOT",
"BBM-DESVIO-CLI": "DISTRIBUICAO-DESVIO-CLI",
"BBM-POSICAO-MOT": "DISTRIBUICAO-POSICAO-MOT",
"BBM-POSICAO-CLI": "DISTRIBUICAO-POSICAO-CLI",
"BBM-PRIORITARIO-MOT": "DISTRIBUICAO-PRIORITARIO-MOT",
"BBM-PRIORITARIO-CLI": "DISTRIBUICAO-PRIORITARIO-CLI",
"BBM-PRIORITARIO-POLICIA": "DISTRIBUICAO-PRIORITARIO-POLICIA",
"BBM-PONTO-APOIO": "DISTRIBUICAO-PONTO-APOIO",
```

### 5. Refactor cirúrgico de YAMLs

| Arquivo | Mudança |
|---|---|
| `backend/db/scoring_rules_final.yaml` | Remove o bloco `id: bbm` (setor) + 10 alertas `BBM-*` |
| `backend/db/seeds/scoring_rules.bootstrap.yaml` | Idem |
| `backend/db/scoring_rules_updated.yaml` | Idem (se aplicável) |

### 6. Refactor cirúrgico do frontend

| Arquivo | Mudança |
|---|---|
| `src/features/settings/components/OperadorManagement.tsx` | Remove "BBM" da lista de setores |
| `src/features/saved-files/components/SavedFiles.tsx` | Idem |
| `src/features/automacao/components/AuditModal.tsx` | Idem |
| `src/features/audit/hooks/useAuditResultEditor.ts` | Remove BBM-específico se houver |
| `src/features/audit/hooks/useAuditFlow.ts` | Idem |
| `src/shared/lib/operationalLabels.ts` | Remove label `bbm` |
| `src/data/criteria.json` | Remove "BBM" da string de label combinada (`"Transferência / Distribuição / Fênix / BBM / UTI / BAS"`). Observação: este arquivo é dead code (`AUDIT_CRITERIA_DB` não é consumido em lugar nenhum desde a migração para `/api/criteria/export`); limpeza é higiene apenas. |

### 7. Intactos (decisão "B - surgical")

- `backend/data/rag_training/*.md` — material de treinamento, contexto histórico útil
- `backend/data/operadores_seed.json` — seed antigo, não roda mais
- `backend/db/migration_steps/m20260518_001_*` — migration histórica
- `backend/db/backup_criteria_20260429_173506/` — backup pré-existente
- Testes — atualizam só os que quebrarem após o refactor (não há varredura proativa)

## Fluxo de dados

### Cenário 1: Sistema externo envia "bbm"
```
Huawei sync recebe organizacao="bbm"
  → resolve_canonical_sector("bbm") em sector_aliases
  → retorna "distribuicao"
  → audit é criada com sector_id="distribuicao"
```

### Cenário 2: IA classifica como sector_id="bbm" (legado)
```
classification.classify_audio() devolve {"sector_id": "bbm", "alert_id": "BBM-PARADA-MOT"}
  → enforce_operator_and_direction_guardrails normaliza
  → align_classification_with_catalog: sector "bbm" não existe no catálogo
    → _resolve_db_sector_alias("bbm") via sector_aliases → "distribuicao"
  → _canonicalize_alert_id("BBM-PARADA-MOT") → "DISTRIBUICAO-PARADA-MOT"
  → resultado final: sector_id="distribuicao", alert_id="DISTRIBUICAO-PARADA-MOT"
```

### Cenário 3: Tentativa de leitura direta de `audit_sectors WHERE id='bbm'`
```
Query retorna 0 linhas.
Código que dependia disso deve consultar via `resolve_canonical_sector` ou
usar `_canonicalize_alert_id` (alert level).
```

## Tratamento de erros

| Cenário | Comportamento |
|---|---|
| Pre-flight check encontra audits/colaboradores em BBM | Migration aborta com `RuntimeError` claro: "Dados em BBM encontrados; rodar limpeza manual antes da migração". |
| Snapshot JSON já existe | Skip da escrita (idempotente). |
| Alias já existe em `sector_aliases` (mesmo `pattern_type` + `pattern_value`) | `list_aliases()` prévio detecta; skip do `create_alias`. |
| `delete_criterion`/`delete_alert`/`delete_sector` retorna `False` (linha não existia) | Log `info` "já removido" e continua. |
| Exceção durante `delete_*` | Repository faz rollback local + raise. Migration propaga RuntimeError com `entity_id` que falhou. Próxima execução retoma idempotentemente do ponto anterior. |
| Falha entre Fase A e B | Snapshot existe mas DB intacto. Re-rodar é seguro. |
| Falha no meio da Fase B | Estado parcial mas FK-consistente (ordem children → parent). Re-rodar conclui. |

## Testes

### Adicionar (`backend/tests/test_bbm_distribuicao_migration.py`)

1. `test_sector_alias_resolves_bbm_to_distribuicao` — `resolve_canonical_sector("bbm")` retorna `"distribuicao"`.
2. `test_alert_alias_resolves_bbm_to_distribuicao` — `canonicalize_alert_id("BBM-PARADA-MOT")` retorna `"DISTRIBUICAO-PARADA-MOT"` (10 casos).
3. `test_catalog_no_longer_has_bbm` — `load_audit_criteria_catalog()` não retorna chave `"bbm"`.
4. `test_prompt_no_longer_lists_bbm` — `build_sectors_and_alerts_prompt()` não contém substring "BBM".
5. `test_migration_idempotent` — rodar migration 2× não causa erro.
6. `test_snapshot_file_created` — snapshot existe em `db/seeds/_archived/`.

### Atualizar (somente os que quebrarem)

- `test_scoring_determinism.py` — pode referenciar BBM em fixtures.
- `test_operator_auditability.py` — idem.
- `test_fechamento_module.py` — idem.

## Plano de revert

Se a decisão for revertida (BBM volta a operar):

```bash
# 1. Re-inserir setor + alertas + critérios do snapshot
python backend/db/seeds/_archived/restore_bbm.py

# 2. Remover alias (script faz automaticamente)
# 3. git revert do commit de código (refactor)
git revert <hash-do-commit-v1.3.74>
```

O snapshot + audit_log do DB fornecem 2 fontes independentes de recuperação.

## Cobertura de pendências derivadas

Esta migração também resolve:

- **M3 da revisão técnica**: "operational siblings hardcoded; não cobre `uti-BBM` (regra UTI em MG/SP/RJ) — comportamento subdocumentado" — agora não tem mais BBM.
- **MEMORY.md**: linha "BBM = transferencia + uti-BBM (UTI apenas em MG/SP/RJ, LP resto)" — fica obsoleta e é removida.

## Itens fora de escopo

- RAG training (mantido por decisão "B" — contexto histórico para IA).
- Documentação `instrucoes/criterios-auditoria/` (não verificada — pode mencionar BBM mas é referência humana, não código vivo).
- Testes que NÃO quebram após o refactor (não há varredura proativa).
- Métrica/dashboard de auditorias antigas com sector BBM (não existem em produção).
- Refatoração do `src/data/criteria.json` para remover dead code completo (fora do escopo; basta tirar a menção a BBM).

## Verificações já feitas (best practices aplicadas)

1. **Schema confirmado:** `sector_aliases` não tem coluna `origem` (sou redirecionado pelo `_log_change` para `sector_aliases_audit_log.origem`). Spec usa `create_alias()` da repository com `origem='migration'`.
2. **Idempotência sem UNIQUE constraint:** spec faz SELECT/`list_aliases` antes de `create_alias`. Não usa `ON CONFLICT` porque a constraint não existe em `(pattern_type, pattern_value)`.
3. **`src/data/criteria.json` é dead code:** `AUDIT_CRITERIA_DB` exportado em `src/data/index.ts` não é consumido em nenhum lugar do frontend; criteria.json fica como higiene apenas.
4. **`sync_criteria_json_to_db.py`** é misleading no nome — na verdade sincroniza `scoring_rules.yaml` → DB. Sem mudança necessária além do YAML que já está no escopo.
5. **Repositories CRUD preservam audit_log:** usar `repositories.admin_criteria.delete_*` (com `alterado_por`, `motivo`, `origem`) garante trilha de auditoria automática para os DELETEs.

## Critério de "pronto"

1. Migration roda com sucesso em ambiente local + audit_log gravado.
2. Todos os testes novos passam.
3. Testes pré-existentes não quebram (exceto os 9 já pré-existentes de cache pollution, fora de escopo).
4. `frontend tsc --noEmit` limpo.
5. Snapshot JSON existe em `db/seeds/_archived/`.
6. `MEMORY.md`, `PENDENCIAS.md`, `logs/versions/1.3.74-migracao-bbm-distribuicao.md` atualizados.
7. 1 commit atômico, push em `main`.
