# Log de Correcao - 2026-03-12

## Contexto

Correcao de 3 bugs remanescentes identificados na validacao posterior das mudancas do commit `b4e90a1`.

## Bugs corrigidos

### 1. Banco legado sem coluna `tipo_escala`

- Adicionada migration nova:
  - `backend/db/migration_steps/m20260312_007_add_tipo_escala_to_colaboradores.py`
- Objetivo:
  - garantir a coluna em bases que ja tinham passado pelas migrations anteriores

### 2. Importador ignorava o `SETOR` real de cada linha

- Ajustado `backend/import_funcionarios_rh.py`
- O importador agora:
  - resolve setor por linha quando o `SETOR` da planilha estiver presente
  - usa o setor do nome do arquivo apenas como fallback
- Resultado:
  - `CHECKLIST` e `RECEPTIVO` deixam de ser achatados para um unico setor
  - arquivos `DIST E CELULA` nao sobrescrevem `TRANSFERENCIA` quando a linha indica esse setor

### 3. `tipo_escala` era criado mas ficava vazio

- Ajustado `backend/import_funcionarios_rh.py`
- O leitor agora normaliza cabecalhos e aceita variacoes corrompidas sem depender de strings quebradas no codigo:
  - `TURNO / OPERACAO`
  - variacao com acentos
  - variacao corrompida por mojibake

### 4. Script standalone nao aplicava migrations antes de importar

- Ajustado `backend/import_funcionarios_rh.py`
- O script agora executa migrations pendentes no banco alvo antes da importacao
- Isso corrige o caso de uso em que o importador e rodado isoladamente

## Arquivos alterados

- `backend/db/migration_steps/m20260312_007_add_tipo_escala_to_colaboradores.py`
- `backend/import_funcionarios_rh.py`
- `backend/tests/test_database_security.py`
- `backend/tests/test_import_funcionarios_rh.py`

## Validacao executada

### Compilacao

```text
python -m py_compile backend/import_funcionarios_rh.py
python -m py_compile backend/db/migration_steps/m20260312_007_add_tipo_escala_to_colaboradores.py
```

Resultado: OK

### Testes focados

```text
python -m pytest backend/tests/test_import_funcionarios_rh.py backend/tests/test_database_security.py -q
```

Resultado: `15 passed`

### Suite completa

```text
python -m pytest backend/tests -q
```

Resultado: `158 passed, 1 skipped in 35.56s`

### Reproducao do importador em banco novo

Resultado observado:

- `198` funcionarios processados
- `183` colaboradores finais
- `tipo_escala_count = 183`
- `receptivo_count = 4`

### Reproducao do importador em copia de banco legado

Resultado observado:

- migration aplicada pelo proprio script
- `has_tipo_escala = True`
- `receptivo_count = 4`
- importacao concluida sem erro de coluna ausente

## Observacoes

- O arquivo `FUNCIONARIOS_CONSOLIDADO.xlsx` continua sendo varrido pela pasta e e ignorado por nao conter linhas importaveis nesse fluxo.
- A copia do banco legado usada na reproducao ainda preserva setores e escalas antigos ja existentes no historico; isso nao impediu a validacao da correcao da migration e da importacao.
