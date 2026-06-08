# Log de Reconciliação de Supervisores - 2026-03-12

## Problema
- A base local mostrava apenas `Larissa Cristina` como supervisora disponível.
- O RH de origem continha `17` supervisores distintos, mas a maior parte dos registros legados em `colaboradores` estava sem `matrícula` e sem `supervisor`.
- O importador atualizava apenas por `matrícula`, então não conseguia reconciliar a base antiga.

## Correção aplicada
- Adicionado lookup de colaboradores existentes por:
  - `matrícula`
  - `nome normalizado`, apenas quando houver correspondência única e o registro antigo estiver sem `matrícula`
- O importador agora reconcilia registros legados por nome de forma conservadora, evitando casar nomes ambíguos.
- O `upsert` passou a atualizar por `id` interno, não mais apenas por `matrícula`.

## Arquivos
- `backend/import_funcionarios_rh.py`
- `backend/tests/test_import_funcionarios_rh.py`

## Validação
- `python -m py_compile backend/import_funcionarios_rh.py backend/tests/test_import_funcionarios_rh.py`
- `python -m pytest backend/tests/test_import_funcionarios_rh.py -q`
- `python -m pytest backend/tests -q`

## Aplicação na base local
- Importação executada em `backend/auditoria.db`
- Resumo da execução:
  - Arquivos processados: `18`
  - Funcionários processados: `198`
  - Atualizados por matrícula: `24`
  - Reconciliados por nome: `157`
  - Novos inseridos: `17`

## Resultado final
- Total de registros em `colaboradores`: `491`
- Registros com supervisor preenchido: `184`
- Supervisores ativos e auditáveis disponíveis: `17`

## Supervisores disponíveis após a correção
- `Geovana Meurer`
- `Gabryelle Marcilio`
- `Rodrigo Barros`
- `Amanda Carla`
- `Gustavo Miralha`
- `Ana Caroline`
- `Geniffer Maciel`
- `Adryan Celso`
- `Larissa Cristina`
- `Thayssa de Almeida`
- `Josiane Ceccon`
- `Tanara Vigentin`
- `Carlos Eduardo`
- `Gustavo Montanari`
- `Hervert Moreira`
- `Giulia Machado`
- `Kayque Lima`
