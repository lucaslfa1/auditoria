# Revisao das Ultimas Atualizacoes

**Data:** 2026-03-12
**Escopo:** backend local, refactors recentes e importacao de colaboradores
**Status da verificacao:** revisao concluida com reproducao local dos achados

## Link local

- Backend: `http://localhost:8080/`
- Docs da API: `http://localhost:8080/docs`

## Resumo executivo

O backend foi iniciado localmente e respondeu com status `200` em `/` e `/docs`.

A suite completa do backend passou:

- `python -m pytest backend/tests -q`
- Resultado: `154 passed, 1 skipped in 36.48s`

Apesar disso, a revisao encontrou regressoes reais sem cobertura de teste, concentradas em:

- fluxo legado de aprendizado de operadores;
- importador de RH;
- compatibilidade entre mapeamento de setores e filtros de lookup;
- divergencia entre caminho de banco do script e caminho de banco do runtime.

## Findings

### 1. Alta - aprendizado de operadores foi desativado na pratica

O refactor removeu o comportamento efetivo do fluxo legado de `operators`, mas partes ativas do sistema ainda dependem dele.

Evidencias:

- `backend/database.py`
  - `upsert_operator(...)` virou `pass`
  - `get_all_operators()` retorna `[]`
  - `get_operators_summary_for_prompt()` deixou de usar historico aprendido
- `backend/routers/audit.py` ainda chama `database.upsert_operator(...)`
- `backend/routers/classifier.py` ainda usa `database.get_operator_by_name(...)` como fallback
- `backend/classification.py` ainda injeta `known_operators` no prompt
- `backend/db/migration_steps/m20260312_006_restructure_drop_operators_add_colaborador_fk.py` remove a tabela `operators`

Reproducao local:

- chamada de `database.upsert_operator('Maria Teste', ...)`
- leitura posterior com `database.get_operator_by_name('Maria Teste')`
- resultado: `None`
- `database.get_all_operators()` retornou `[]`

Impacto:

- novos nomes deixam de ser aprendidos;
- fallback de classificacao perde memoria historica;
- prompt da classificacao perde base acumulada de operadores conhecidos.

### 2. Alta - importador de RH quebra contra o schema atual

O script `backend/import_funcionarios_rh.py` tenta gravar a coluna `tipo_escala`, mas a tabela `colaboradores` criada em runtime nao possui essa coluna.

Evidencias:

- `backend/import_funcionarios_rh.py` faz `UPDATE` e `INSERT` com `tipo_escala`
- `backend/db/runtime_schema.py` nao cria `tipo_escala` em `colaboradores`

Reproducao local:

- banco temporario inicializado com `database.init_db()`
- execucao de `import_funcionarios(...)`
- resultado:
  - `198` erros
  - mensagem recorrente: `table colaboradores has no column named tipo_escala`
  - `0` colaboradores importados

Impacto:

- importacao falha silenciosamente em lote;
- relatorio final do script aparenta concluir com sucesso, mas sem dados persistidos.

### 3. Media - script de importacao usa banco diferente do runtime

O importador usa por padrao `backend/db/auditoria.db`, mas a aplicacao resolve o banco local em `backend/auditoria.db`.

Evidencias:

- `backend/import_funcionarios_rh.py`
  - default: `backend/db/auditoria.db`
- `backend/db/connection.py`
  - runtime local: `backend/auditoria.db`

Impacto:

- mesmo com o schema corrigido, o script pode importar para o arquivo errado;
- a aplicacao sobe normalmente sem refletir o que foi importado no script.

### 4. Media - mapeamento do importador nao conversa com o lookup atual

O importador grava setores como `LP`, `LOG`, `LOG_UNILEVER` e `LOG_MONDELEZ`, mas os filtros atuais de lookup esperam semanticamente `transferencia`, `logistica` e variacoes inferidas por escala/organizacao.

Evidencias:

- `backend/import_funcionarios_rh.py`
  - `SETOR_MAPPING` produz ids como `LP`, `LOG`, `LOG_UNILEVER`, `LOG_MONDELEZ`
- `backend/repositories/operators.py`
  - `_matches_operador_sector(...)` nao trata essas siglas como equivalentes

Reproducao local:

- `_matches_operador_sector('transferencia', 'LP', '')` -> `False`
- `_matches_operador_sector('logistica', 'LOG', '')` -> `False`
- `_matches_operador_sector('logistica_unilever', 'LOG_UNILEVER', '')` -> `False`
- `_matches_operador_sector('mondelez', 'LOG_MONDELEZ', '')` -> `False`

Impacto:

- colaboradores importados podem nao aparecer em filtros por setor;
- autocomplete e lookup administrativo podem parecer incompletos.

## Observacoes de ambiente

- o backend subiu com `python main.py` usando o Python global;
- a `backend/.venv` local esta inconsistente:
  - `dotenv` da venv estava com arquivos zerados;
  - houve erro de `_distutils_hack` e `ImportError` para `load_dotenv`.

## Validacao executada

- `Invoke-WebRequest http://localhost:8080/` -> `200`
- `Invoke-WebRequest http://localhost:8080/docs` -> `200`
- `python -m pytest backend/tests -q` -> `154 passed, 1 skipped`
- execucoes locais adicionais para reproduzir:
  - regressao do fluxo legado de operadores;
  - falha do importador RH;
  - incompatibilidade do matching por setor.

## Recomendacoes objetivas

1. Decidir se o aprendizado legado de `operators` sera mantido ou removido de vez.
2. Se mantido, restaurar persistencia e cobertura de teste desse fluxo.
3. Corrigir `import_funcionarios_rh.py` para usar schema e caminho de banco alinhados ao runtime.
4. Unificar ids de setor entre importacao, lookup administrativo e classificacao.
5. Adicionar testes para:
   - fluxo de aprendizado de operador;
   - importacao de RH;
   - compatibilidade de setor no lookup.

## Referencias principais

- `backend/database.py`
- `backend/import_funcionarios_rh.py`
- `backend/db/runtime_schema.py`
- `backend/db/connection.py`
- `backend/db/migration_steps/m20260312_006_restructure_drop_operators_add_colaborador_fk.py`
- `backend/repositories/operators.py`
- `backend/routers/audit.py`
- `backend/routers/classifier.py`
- `backend/classification.py`
