# Revisao de Codigo — Claude Opus 4.6

**Data:** 2026-03-12
**Escopo:** Todo codigo novo/modificado nos commits `aafe07d` e `b4e90a1` + alteracoes externas do linter/GPT 5.4
**Baseline de testes:** 175 passed, 1 skipped (37.24s)

---

## Sumario executivo

A reestruturacao `operadores_rh -> colaboradores` esta funcionalmente completa e os testes
passam. No entanto, a revisao profunda encontrou **21 issues** distribuidas em 4 areas:
import_funcionarios_rh.py (refatorado pelo GPT 5.4), database.py, migrations/schema e
routers/repositories. Nenhuma e um crash em producao imediato, mas 5 sao de alta prioridade.

| Severidade | Qtd | Descricao resumida |
|------------|-----|--------------------|
| Alta       |   5 | Dados inconsistentes, crash em matricula, setor matching incompleto, dead code perigoso, connection leak |
| Media      |   8 | Backfill nao-deterministico, auditavel stale no UPDATE, duplicatas por nome, senha em response, JOIN cartesiano |
| Baixa      |   8 | Dead code inofensivo, obs nao persistido, cache in-memory stale, format do prompt, aliases nao usados |

---

## Findings detalhados

### ALTA PRIORIDADE

#### A1. `UTI_BASE` inconsistente entre SETOR_MAPPING e _resolve_sector_id
**Arquivos:** `import_funcionarios_rh.py:51` vs `import_funcionarios_rh.py:269-270`
**Impacto:** Dados de setor inconsistentes no banco (UTI vs UTI_BASE para o mesmo setor logico)

`SETOR_MAPPING["UTI"]` produz `id: "UTI_BASE"`, mas `_resolve_sector_id` retorna `"UTI"`
quando a planilha tem coluna setor com valor GRS/UTI. Operadores do mesmo setor ficam com
valores diferentes dependendo de se o setor veio do nome do arquivo ou da coluna interna.

**Correcao:** Alterar `SETOR_MAPPING["UTI"]["id"]` para `"UTI"` (alinhar com `_resolve_sector_id`).

---

#### A2. Crash em matricula nao-numerica
**Arquivo:** `import_funcionarios_rh.py:369`
**Impacto:** `ValueError` nao tratado aborta o processamento do arquivo inteiro

```python
"matricula": str(int(matricula)) if pd.notna(matricula) else None,
```

Se `matricula` for `"ABC123"` ou `"N/A"`, `int()` levanta `ValueError`.

**Correcao:** Envolver em try/except com `int(float(matricula))` e skip da linha em caso de erro.

---

#### A3. `_matches_operador_sector` nao trata aliases de setor
**Arquivo:** `repositories/operators.py:124-157`
**Impacto:** Lookup por setor retorna vazio para `grs`, `rastreamento`, `rast`, `dist`, `sinistro`, `unilever`

A funcao so trata os IDs canonicos (`uti`, `transferencia`, `distribuicao`, etc.) mas nao
os aliases usados em `core/config.py` e `audit_evaluator.py`. Se a API ou frontend enviar
`sector_id=grs`, nenhum colaborador e retornado.

**Correcao:** Adicionar mapeamento de aliases antes do switch:
```python
SECTOR_ALIASES = {"grs": "uti", "rastreamento": "transferencia", "rast": "transferencia",
                  "dist": "distribuicao", "sinistro": "bas", "sinistros": "bas",
                  "longo_percurso": "transferencia", "unilever": "logistica_unilever"}
normalized_sector_id = SECTOR_ALIASES.get(normalized_sector_id, normalized_sector_id)
```

---

#### A4. `repositories/operator_learning.py` faz queries na tabela `operators` (removida)
**Arquivo:** `repositories/operator_learning.py` (inteiro)
**Impacto:** Se qualquer code path desviar dos stubs em database.py, crash com `OperationalError: no such table: operators`

O arquivo inteiro referencia uma tabela que a migration 006 remove. Os stubs em database.py
interceptam, mas o repositorio continua importavel e suas funcoes referenciam uma tabela
inexistente.

**Correcao:** Deletar `repositories/operator_learning.py` ou adicionar guarda no topo:
```python
raise ImportError("Legacy module — operators table has been removed. Use colaboradores.")
```

---

#### A5. Connection leak no import_funcionarios_rh.py
**Arquivo:** `import_funcionarios_rh.py:401-501`
**Impacto:** Se migration ou import falhar, connection fica aberta e DB fica locked

O `conn` nao esta em `try/finally`. Qualquer excecao deixa a conexao aberta.

**Correcao:** Envolver corpo da funcao em `try: ... finally: conn.close()`.

---

### MEDIA PRIORIDADE

#### M1. UPDATE no import nao atualiza coluna `auditavel`
**Arquivo:** `import_funcionarios_rh.py:140-168`
**Impacto:** Colaborador que muda de ATIVO para INATIVO mantem `auditavel=1`

O INSERT calcula `auditavel = 1 if status == "ATIVO" else 0`, mas o UPDATE nao recalcula.

**Correcao:** Adicionar `auditavel = ?` ao SET do UPDATE com o mesmo calculo.

---

#### M2. Backfill da migration 006 usa `LIMIT 1` sem `ORDER BY`
**Arquivo:** `m20260312_006:25-37`
**Impacto:** Se existem colaboradores com mesmo nome normalizado, o FK aponta para um arbitrario

**Correcao:** Adicionar `ORDER BY c.id ASC` para determinismo.

---

#### M3. Migration 005 descarta dados ao encontrar ambas as tabelas com dados
**Arquivo:** `m20260312_005:26-40`
**Impacto:** Se `colaboradores` ja tem dados e `operadores_rh` tambem, os dados de `operadores_rh` sao descartados sem merge

**Observacao:** Este cenario so ocorre em DBs parcialmente migrados. Risco baixo em producao
atual, mas o comportamento e silencioso.

---

#### M4. Index `idx_colaboradores_status_auditavel` so existe em runtime_schema.py
**Arquivo:** `runtime_schema.py:200`
**Impacto:** Em DBs existentes que passaram por migracao sequencial, este index nunca e criado

**Correcao:** Criar migration dedicada ou adicionar ao final da migration 008.

---

#### M5. Connection leak em `repositories/audits.py:update_audit_status`
**Arquivo:** `repositories/audits.py:440-480`
**Impacto:** Excecao durante commit deixa conexao aberta

**Correcao:** Envolver em `try/finally`.

---

#### M6. JOIN OR-based em audits.py pode produzir linhas duplicadas
**Arquivo:** `repositories/audits.py:366-377, 567-576`
**Impacto:** Se `operator_id` e `operator_name` casam com colaboradores diferentes, resultado e nao-deterministico

**Correcao:** Priorizar match por `operator_id` (telefonia) e so usar `operator_name` como fallback.

---

#### M7. Duplicatas por nome no import quando nomes normalizados colidem
**Arquivo:** `import_funcionarios_rh.py:111-113`
**Impacto:** Se 2+ colaboradores tem mesmo nome normalizado, matching por nome e desabilitado e novos registros sao inseridos como duplicatas

**Observacao:** Mitigado pela dedup por matricula. Risco baixo com dados reais.

---

#### M8. Senhas temporarias retornadas no corpo HTTP
**Arquivo:** `routers/admin.py:114-121`
**Impacto:** Credenciais podem ser logadas por proxies/WAF

**Observacao:** Endpoint protegido por `require_admin`. Risco baixo mas nao ideal.

---

### BAIXA PRIORIDADE

#### B1. Dead code: `_build_learned_operator_payload` em classifier.py
**Arquivo:** `routers/classifier.py:27-43`
**Correcao:** Deletar funcao.

---

#### B2. Campo `obs` extraido do Excel mas nunca persistido
**Arquivo:** `import_funcionarios_rh.py:365`
**Correcao:** Remover extracao ou adicionar coluna se desejado.

---

#### B3. Cache in-memory de nomes nao atualizado ao mudar nome no UPDATE
**Arquivo:** `import_funcionarios_rh.py:169-177`
**Impacto:** Matching incorreto para linhas subsequentes no mesmo arquivo (improvavel)

---

#### B4. `get_operators_summary_for_prompt` perdeu info de setor/frequencia
**Arquivo:** `database.py:657-662`
**Impacto:** Prompt de classificacao recebe nomes sem setor (degradacao leve de qualidade)
**Correcao:** Enriquecer formato: `"- Nome (setor: LOGISTICA)"` usando `get_colaboradores_para_prompt` com dados extras.

---

#### B5. 10 aliases de compatibilidade nao sao usados por nenhum caller
**Arquivo:** `database.py` (multiplas linhas)
**Correcao:** Podem ser removidos quando houver confianca de que nenhum script externo os usa.

---

#### B6. View `audits_com_colaborador` definida em 2 lugares
**Arquivos:** `runtime_schema.py:380-408` e `m20260312_006:45-73`
**Impacto:** Divergencia futura se um for editado sem o outro

---

#### B7. `_coerce_fenix_sector` chamado com 2 args em `get_colaboradores_para_prompt` vs 3 em `get_colaboradores_lookup`
**Arquivo:** `repositories/operators.py:830` vs `736-739`
**Impacto:** Fenix por `organizacao_telefonia` nao e detectado no prompt

---

#### B8. `runtime_schema.py` chamado por migration 002 ja contem schema das migrations 005-013
**Impacto:** Em DB novo, migration 002 aplica tudo de uma vez, mascarando bugs em migrations posteriores. Nao e um bug funcional mas dificulta teste isolado de migrations.

---

## Plano de correcoes

### Fase 1 — Correcoes criticas (imediato)

| # | Acao | Arquivo(s) | Estimativa |
|---|------|-----------|------------|
| A1 | Trocar `UTI_BASE` -> `UTI` no SETOR_MAPPING | import_funcionarios_rh.py | 1 linha |
| A2 | try/except no parse de matricula | import_funcionarios_rh.py | 5 linhas |
| A3 | Adicionar SECTOR_ALIASES ao _matches_operador_sector | repositories/operators.py | 10 linhas |
| A4 | Deletar operator_learning.py | repositories/operator_learning.py | delete file |
| A5 | try/finally na conexao do import | import_funcionarios_rh.py | 3 linhas |
| M1 | Adicionar auditavel ao UPDATE | import_funcionarios_rh.py | 2 linhas |
| B1 | Deletar _build_learned_operator_payload | routers/classifier.py | delete function |

### Fase 2 — Melhorias de robustez (proximo ciclo)

| # | Acao | Arquivo(s) |
|---|------|-----------|
| M2 | Adicionar ORDER BY ao backfill da migration 006 | m20260312_006 (nova migration) |
| M4 | Criar migration para idx_colaboradores_status_auditavel | nova migration |
| M5 | try/finally em update_audit_status | repositories/audits.py |
| M6 | Refatorar JOIN para priorizar operator_id | repositories/audits.py |
| B4 | Enriquecer prompt de operadores com setor | database.py |
| B7 | Passar 3 args em _coerce_fenix_sector no prompt | repositories/operators.py |

### Fase 3 — Limpeza (quando conveniente)

| # | Acao |
|---|------|
| B2 | Remover extracao de `obs` |
| B5 | Remover aliases nao usados |
| B6 | Consolidar definicao da view em um so lugar |

---

## Testes recomendados (novos)

1. **test_import_matricula_nao_numerica** — Verificar que matricula "ABC" nao causa crash
2. **test_import_setor_uti_consistencia** — Verificar que UTI do arquivo e UTI da coluna produzem mesmo valor
3. **test_sector_aliases_in_lookup** — Verificar que `grs`, `rastreamento`, `dist` retornam colaboradores
4. **test_import_connection_cleanup** — Verificar que conexao e fechada mesmo em caso de erro
5. **test_auditavel_atualizado_no_update** — Verificar que mudanca ATIVO->INATIVO atualiza auditavel

---

## Validacao executada

```
python -m pytest backend/tests/ -v -> 175 passed, 1 skipped (37.24s)
Compilacao de todos os arquivos modificados -> OK
Grep por referencias a tabela operators em SQL ativo -> limpo
Grep por referencias a operadores_rh em SQL ativo -> limpo (so aliases e migrations)
```
