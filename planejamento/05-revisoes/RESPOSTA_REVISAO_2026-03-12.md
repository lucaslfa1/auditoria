# Resposta a Revisao de 2026-03-12

**Data:** 2026-03-12
**Revisado por:** Claude Opus 4.6
**Referencia:** `planejamento/REVISAO_ATUALIZACOES_2026-03-12.md` (relatorio GPT 5.4)

## Veredicto geral

Dos 4 findings reportados, 3 eram bugs reais e 1 era parcialmente correto
com impacto superestimado. Todos foram corrigidos.

## Analise e correcoes por finding

### Finding 1 (Alta) - Aprendizado de operadores desativado

**Veredicto: Parcialmente correto. Impacto superestimado.**

O relatorio afirma que o prompt de classificacao perde a base acumulada de
operadores conhecidos. Isso e **incorreto**: `get_operators_summary_for_prompt()`
ja redirecionava para `get_colaboradores_para_prompt()`, que retorna nomes
ativos da tabela `colaboradores`. O prompt de classificacao **continua
funcionando** com dados reais de RH.

O fallback em `classifier.py` (`get_operator_by_name`) tambem ja redirecionava
internamente para `buscar_colaborador_por_nome` — era um wrapper redundante,
nao uma funcionalidade perdida.

O que era real: chamadas a `upsert_operator()` (no-op) e ao fallback
redundante desperdicavam ciclos e confundiam o log.

**Correcoes aplicadas:**

| Arquivo | Acao |
|---------|------|
| `backend/routers/audit.py` | Removida chamada morta a `database.upsert_operator(...)` (linhas 87-95) |
| `backend/routers/classifier.py` | Removido fallback redundante via `get_operator_by_name` e chamada morta a `upsert_operator`. Simplificado para usar apenas `buscar_colaborador_por_nome`. |

### Finding 2 (Alta) - Coluna `tipo_escala` ausente no schema

**Veredicto: Correto. Bug real.**

O script `import_funcionarios_rh.py` fazia INSERT/UPDATE com `tipo_escala`,
mas `runtime_schema.py` nao criava essa coluna em `colaboradores`.

**Correcao aplicada:**

| Arquivo | Acao |
|---------|------|
| `backend/db/runtime_schema.py` | Adicionado `ensure_column(cursor, "colaboradores", "tipo_escala", "TEXT", ...)` |

### Finding 3 (Media) - Caminho de banco divergente

**Veredicto: Correto. Bug real.**

O script usava `backend/db/auditoria.db` como default, enquanto o runtime
resolve `backend/auditoria.db` via `connection.py`.

**Correcoes aplicadas:**

| Arquivo | Acao |
|---------|------|
| `backend/import_funcionarios_rh.py` | Default de `db_path` agora e `None`; quando omitido, chama `db.connection.resolve_db_path()` para usar o mesmo banco do runtime. Caminho de `excel_dir` agora relativo ao proprio script (nao ao cwd). |

### Finding 4 (Media) - Mapeamento de setores incompativel com lookup

**Veredicto: Correto. Bug real.**

O `SETOR_MAPPING` produzia IDs como `LP`, `LOG`, `LOG_UNILEVER`, `LOG_MONDELEZ`
que nao casavam com os valores esperados por `_matches_operador_sector()`.

**Correcoes aplicadas:**

| Arquivo | Acao |
|---------|------|
| `backend/import_funcionarios_rh.py` | `SETOR_MAPPING` atualizado para produzir IDs compativeis: `LP`->`TRANSFERENCIA`, `LOG`->`LOGISTICA`, `DIST`->`DISTRIBUICAO`, `DIST_CELULA`->`CHECKLIST`, `LOG-MONDELEZ/UNILEVER` -> `LOGISTICA` com `escala_override`. |
| `backend/import_funcionarios_rh.py` | `parse_filename()` agora aplica `escala_override` do mapping quando a cor do arquivo e `None` (ex: LOG-MONDELEZ.xlsx sem sufixo de cor). |

## Validacao executada

```
python -m py_compile routers/audit.py        -> OK
python -m py_compile routers/classifier.py   -> OK
python -m py_compile db/runtime_schema.py    -> OK
python -m py_compile import_funcionarios_rh.py -> OK
python -m pytest tests/ -v                   -> 154 passed, 1 skipped (34.10s)
```

### Teste de mapeamento de setores (pos-correcao)

```
2602-LOG-MONDELEZ.xlsx     -> setor=LOGISTICA       escala=MONDELEZ
2602-LOG-UNILEVER.xlsx     -> setor=LOGISTICA       escala=UNILEVER
2602-LOG.xlsx              -> setor=LOGISTICA       escala=None
2602-LP-AMARELA.xlsx       -> setor=TRANSFERENCIA   escala=Amarela
2602-GRS-VERDE.xlsx        -> setor=UTI             escala=Verde
2602-DIST - AZUL.xlsx      -> setor=DISTRIBUICAO    escala=Azul
2602-CHECKLIST E CELULA.xlsx -> setor=CHECKLIST     escala=None
2602-CADASTRO.xlsx         -> setor=CADASTRO        escala=None
2602-FENIX.xlsx            -> setor=FENIX           escala=None
```

### Teste de matching no lookup (pos-correcao)

```
_matches_operador_sector('transferencia', 'TRANSFERENCIA', 'Amarela')    -> True
_matches_operador_sector('logistica', 'LOGISTICA', '')                   -> True
_matches_operador_sector('logistica_unilever', 'LOGISTICA', 'UNILEVER')  -> True
_matches_operador_sector('mondelez', 'LOGISTICA', 'MONDELEZ')           -> True
_matches_operador_sector('uti', 'UTI', 'Verde')                         -> True
_matches_operador_sector('uti', 'UTI_BASE', 'Cinza')                    -> True
_matches_operador_sector('distribuicao', 'DISTRIBUICAO', 'Azul')        -> True
_matches_operador_sector('fenix', 'FENIX', '')                          -> True
_matches_operador_sector('cadastro', 'CADASTRO', '')                    -> True
_matches_operador_sector('checklist', 'CHECKLIST', '')                  -> True
```

Todos os 10 cenarios passaram.

## Arquivos modificados

1. `backend/routers/audit.py` - Finding 1
2. `backend/routers/classifier.py` - Finding 1
3. `backend/db/runtime_schema.py` - Finding 2
4. `backend/import_funcionarios_rh.py` - Findings 3 e 4

## Observacoes adicionais

- O relatorio menciona problemas na `.venv` local (dotenv zerado, ImportError).
  Isso e um problema de ambiente local, nao do codigo. Recriar a venv resolve.
- A decisao de design sobre o fluxo legado de `operators` esta clara: ele foi
  **substituido** por `colaboradores` (dados de RH), nao desativado por acidente.
  As funcoes legadas existem como stubs/redirecionamentos para compatibilidade.
