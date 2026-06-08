# Continuacao da Revisao de Codigo

**Data:** 2026-03-12
**Escopo:** Validacao dos findings remanescentes apos as correcoes mais recentes
**Base validada:** `175 passed, 1 skipped` no backend e `Frontend regression checks passed`

## Findings ainda validos

### 1. Alta — importador grava so `id_huawei`, mas auditorias continuam buscando por `id_telefonia`
**Arquivos:** `backend/import_funcionarios_rh.py:151-177`, `backend/import_funcionarios_rh.py:191-209`, `backend/repositories/audits.py:366-377`, `backend/repositories/audits.py:569-578`

O importador atualizado faz `UPDATE` e `INSERT` em `colaboradores` preenchendo `id_huawei`, mas nao sincroniza `id_telefonia`. Ao mesmo tempo, o enriquecimento de auditorias e exportacoes continua priorizando `o.id_telefonia = a.operator_id`.

**Reproducao em banco temporario:**
- colaborador salvo com `id_huawei='HW-777'` e `id_telefonia=NULL`
- auditoria salva com `operator_id='HW-777'` e `operator_name` divergente
- `get_audit_by_id()` retornou `supervisor=None`
- `get_audits_for_export()` retornou `supervisor=''`

**Impacto:** auditorias geradas para IDs Huawei importados podem perder supervisor, escala e contexto de exportacao.

### 2. Alta — join por `operator_id OR operator_name` continua ambiguo e pode vincular a auditoria ao colaborador errado
**Arquivos:** `backend/repositories/audits.py:366-377`, `backend/repositories/audits.py:569-578`, `backend/repositories/audits.py:624-629`

Os joins de auditoria continuam usando `OR` entre `id_telefonia` e `nome`, sem priorizacao. Se o `operator_id` casar um colaborador e o `operator_name` casar outro, a mesma auditoria gera duas linhas no join e o codigo depois elimina duplicatas por `audit.id`, ficando com o primeiro match que o SQLite entregar.

**Reproducao em banco temporario:**
- colaborador A: `nome='Nome Pelo Nome'`, `supervisor='Supervisor Nome'`, `id_telefonia='ID-2'`
- colaborador B: `nome='Outro Nome'`, `supervisor='Supervisor ID'`, `id_telefonia='ID-1'`
- auditoria: `operator_id='ID-1'`, `operator_name='Nome Pelo Nome'`
- o join bruto retornou 2 linhas para a mesma auditoria
- `get_audit_by_id()` e `get_audits_for_export()` ficaram com `Supervisor ID`, descartando o match por nome

**Impacto:** supervisor e escala podem sair incorretos em detalhe de auditoria, exportacao e filtros do portal.

### 3. Media — migration 006 continua fazendo backfill nao deterministico de `colaborador_id`
**Arquivo:** `backend/db/migration_steps/m20260312_006_restructure_drop_operators_add_colaborador_fk.py:25-36`

O backfill de `audits.colaborador_id` continua usando:

`SELECT c.id FROM colaboradores c WHERE LOWER(TRIM(audits.operator_name)) = LOWER(TRIM(c.nome)) LIMIT 1`

Sem `ORDER BY`, bases com nomes duplicados normalizados continuam dependendo da ordem fisica da tabela.

**Impacto:** migracoes em bases reais podem ligar auditorias antigas ao colaborador errado.

### 4. Media — migration 008 nao cria o indice `idx_colaboradores_status_auditavel` em bases ja existentes
**Arquivos:** `backend/db/runtime_schema.py:193-200`, `backend/db/migration_steps/m20260312_008_add_auditavel_and_normalize_fenix.py:17-76`

O indice existe apenas no bootstrap do `runtime_schema`. Em bases que ja tinham passado por `20260306_002_runtime_schema`, a migration 008 adiciona `auditavel`, mas nao cria `idx_colaboradores_status_auditavel`.

**Impacto:** inconsistencia entre banco novo e banco migrado, com piora de performance nas consultas de colaboradores ativos/auditaveis.

### 5. Media — endpoint admin continua retornando senhas temporarias no corpo HTTP
**Arquivo:** `backend/routers/admin.py:82-121`

`generate_supervisor_accounts()` ainda devolve:

`"credentials": [{"username": ..., "temporary_password": ...}]`

**Impacto:** as credenciais podem parar em logs de API, proxy reverso ou ferramentas de observabilidade. O endpoint e protegido por admin, mas a exposicao continua desnecessaria.

### 6. Baixa — caminho de prompt ainda ignora pista de Fenix por `organizacao_telefonia`
**Arquivo:** `backend/repositories/operators.py:839-846`

Em `get_colaboradores_para_prompt()`, `_coerce_fenix_sector()` continua sendo chamado com apenas `setor` e `escala`. Em outros fluxos ele recebe tambem `organizacao_telefonia`.

**Impacto:** nomes usados no prompt podem deixar de cair em `FENIX` quando a pista vier apenas da organizacao de telefonia.

## Validacao executada

- `python -m pytest backend/tests -q` -> `175 passed, 1 skipped in 30.36s`
- `npm run test:frontend` -> `Frontend regression checks passed.`
- reproducao dirigida do caso `id_huawei sem id_telefonia`
- reproducao dirigida do join ambiguo `operator_id OR operator_name`

## Observacao

Parte relevante do relatorio original do Claude ja foi corrigida. Os pontos acima sao os que ainda consegui confirmar no codigo atual.
