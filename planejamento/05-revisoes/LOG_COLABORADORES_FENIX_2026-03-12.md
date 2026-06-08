# Log de Correcao - Colaboradores e Fenix - 2026-03-12

## Objetivo

Tirar o cadastro de funcionarios do bloco escondido em Ajustes, criar controle operacional de auditabilidade e corrigir o tratamento da equipe Fenix para nao continuar achatando registros em setores errados.

## Mudancas aplicadas

### 1. Modulo proprio de colaboradores

- Criado modulo principal de `Colaboradores` no menu lateral.
- Removida a gestao de operadores da tela de Ajustes.
- Reaproveitada e reformulada a tela de cadastro para foco operacional:
  - busca e filtros
  - filtros fortes por supervisor e setor
  - status `ATIVO` e `INATIVO`
  - flag `auditavel`
  - acoes rapidas para ativar, inativar, liberar e bloquear auditoria
  - selecao e acoes em lote para ativacao, inativacao e auditoria

### 1.1. Ajustes de texto e exibicao

- `BAS` passou a permanecer em maiusculo na exibicao.
- `FENIX` passou a ser exibido como `Fenix`.
- Valores operacionais muito gritados em caixa alta foram reduzidos na tela de colaboradores.
- O botao separado de `Bloquear auditoria` foi removido da UI; inativar passa a ser o fluxo principal para tirar alguem da auditoria.
- `Softphone` deixou de aparecer no formulario de edicao, mantendo apenas o registro interno.
- Os textos de apoio da pagina foram encurtados e reescritos de forma mais objetiva.

### 2. Controle de auditabilidade

- Adicionada coluna `auditavel` na tabela `colaboradores`.
- Lookup, prompt e busca nominal agora consideram apenas:
  - `status = ATIVO`
  - `auditavel = 1`
- O cadastro manual permite configurar isso explicitamente.
- Foi adicionada API de acao em lote para aplicar `activate`, `inactivate`, `enable_audit` e `disable_audit`.

### 2.1. Canonicalizacao de ID Huawei

- `id_huawei` passou a ser o identificador principal exibido na interface.
- `id_telefonia` foi mantido apenas por compatibilidade e agora faz espelho para `id_huawei` quando um dos campos vier vazio.
- Lookup e autocomplete passaram a preferir `ID Huawei` como rótulo principal.
- Migration adicional preenche `id_huawei` a partir de `id_telefonia` nas bases existentes.

### 3. Correcao do tratamento de Fenix

- O importador passou a tratar `FENIX` como setor proprio quando a origem do arquivo ou da operacao aponta para Fenix.
- Isso evita continuar classificando a equipe Fenix como `TRANSFERENCIA` por falta de identificacao confiavel dos subsetores internos.
- A camada de cadastro e enriquecimento agora tambem normaliza qualquer registro com pista de `FENIX` para `setor = FENIX`, mesmo quando o dado bruto ainda chega como `TRANSFERENCIA`.
- O arquivo `FUNCIONARIOS_CONSOLIDADO.xlsx` passou a ser ignorado no fluxo de importacao para nao sobrescrever dados ja resolvidos pelas planilhas de origem.
- Migration adicional faz backfill conservador em registros existentes quando `escala` ou `tipo_escala` indicam Fenix.
- Migration complementar reforca essa regra em bases ja atualizadas, considerando tambem `organizacao_telefonia`.

## Arquivos alterados

- `backend/import_funcionarios_rh.py`
- `backend/repositories/operators.py`
- `backend/routers/admin.py`
- `backend/database.py`
- `backend/db/runtime_schema.py`
- `backend/db/migration_steps/m20260312_008_add_auditavel_and_normalize_fenix.py`
- `backend/db/migration_steps/m20260312_009_force_fenix_as_default_sector.py`
- `backend/db/migration_steps/m20260312_010_backfill_huawei_id_from_telefonia.py`
- `backend/tests/test_database_security.py`
- `backend/tests/test_import_funcionarios_rh.py`
- `backend/tests/test_operator_prompt_lookup.py`
- `tests/frontend-regressions.test.mjs`
- `src/App.tsx`
- `src/shared/components/Sidebar.tsx`
- `src/shared/components/OperatorAutocompleteFields.tsx`
- `src/features/audit/components/AuditWorkspace.tsx`
- `src/features/classifier/components/Classifier.tsx`
- `src/features/saved-files/components/SavedFiles.tsx`
- `src/features/settings/components/Settings.tsx`
- `src/features/settings/components/OperadorManagement.tsx`
- `src/features/supervisor/components/SupervisorPortal.tsx`
- `src/features/colaboradores/components/ColaboradoresPage.tsx`

## Validacao executada

### Compilacao Python

```text
python -m py_compile backend/import_funcionarios_rh.py backend/database.py backend/routers/admin.py backend/repositories/operators.py backend/db/runtime_schema.py backend/db/migration_steps/m20260312_008_add_auditavel_and_normalize_fenix.py backend/tests/test_database_security.py backend/tests/test_import_funcionarios_rh.py backend/tests/test_operator_prompt_lookup.py
```

Resultado: OK

### Testes backend focados

```text
python -m pytest backend/tests/test_import_funcionarios_rh.py backend/tests/test_database_security.py backend/tests/test_operator_prompt_lookup.py -q
```

Resultado: `25 passed in 4.45s`

### Suite backend completa

```text
python -m pytest backend/tests -q
```

Resultado: `163 passed, 1 skipped in 41.48s`

### Frontend

```text
npm run build
npm run test:frontend
```

Resultado:

- build OK
- frontend regression checks passed

### Base local apos migration

Checagem executada em `backend/auditoria.db`:

- migration `20260312_009_force_fenix_as_default_sector` registrada
- migration `20260312_010_backfill_huawei_id_from_telefonia` registrada
- coluna `auditavel` presente em `colaboradores`
- `fenix_count = 25`
- `id_huawei_count = 450`
- `telefonia_without_huawei = 0`
- amostra validada com registros persistidos em `setor = fenix`

### Reproducao do importador em banco novo

Checagem executada com importacao completa em banco temporario:

- `FUNCIONARIOS_CONSOLIDADO.xlsx` ignorado
- `2602-FENIX.xlsx` importado sem sobrescrita posterior
- `fenix_count = 10`
- equipe do supervisor `Adryan Celso` persistida em `setor = FENIX`

### Evidencia local da equipe Fenix

Arquivo localizado em `instrucoes/lista-de-funcionarios/2602-FENIX.xlsx`:

- aba unica `FENIX`
- `11` nomes unicos de colaboradores
- supervisor informado: `Adryan Celso`
- `TURNO / OPERACAO = FENIX`
- `SETOR` bruto na planilha aparece como `TRANSFERENCIA`

Esse achado reforca a decisao conservadora: a origem local identifica a operacao Fenix, mas nao separa com seguranca os subsetores internos que voce descreveu.

## Observacoes

- O fluxo de exclusao continua disponivel, mas a UI foi orientada para uso de inativacao como caminho normal.
- O criterio para Fenix foi deliberadamente conservador: na duvida, fica em `FENIX` e nao em um subsetor inferido.
- A camada separada de `auditavel` deixou de aparecer na interface de colaboradores.
- A regra operacional foi simplificada para `ATIVO` = entra na auditoria e `INATIVO` = fica fora.
- O backend passou a espelhar `auditavel` a partir de `status` por compatibilidade, sem manter um segundo controle manual.
- Migration adicional `20260312_014_sync_colaborador_auditavel_with_status` sincroniza bases existentes com essa regra.
