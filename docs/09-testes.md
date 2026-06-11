# Testes — como rodar e o que esperar

> A suite é o gate de regressão do projeto: **0 falhas toleradas** desde a
> v1.3.124 (847 passed, 47 skipped).

## 1. Estrutura

| Onde | O quê |
| --- | --- |
| `tests/backend/` | Suite Python (pytest + unittest), ~110 arquivos. `tests/backend/__init__.py` injeta `backend/` no `sys.path`. |
| `tests/frontend/` | Testes Node do frontend. |
| `backend/tests/` | NÃO existe mais (removido em 2026-05-27). |

## 2. Banco de teste (obrigatório)

Vários testes ESCREVEM no banco. O `tests/backend/conftest.py` tem um guard
que **bloqueia a suite contra o banco de produção** (host `ep-aged-river`);
o escape consciente `ALLOW_TESTS_ON_PROD_DB=1` existe, mas não use.

Setup local (PostgreSQL >= 16 com usuário `postgres:postgres`):

```bash
# 1. criar o banco
psql -U postgres -c "CREATE DATABASE auditoria_test"

# 2. aplicar schema + seeds (migrations + catálogo oficial completo)
cd backend
DATABASE_URL='postgresql://postgres:postgres@localhost:5432/auditoria_test' \
  python -c "from db.database import init_db; init_db()"
```

O `init_db()` aplica as 53+ migrations e os seeds — incluindo o **catálogo
oficial de critérios** (12 setores / 71 alertas / 1051 critérios, seed da
v1.3.120). Sem o catálogo completo, ~15 testes de guardrail de classificação
falham.

Observação: sem a extensão pgvector instalada localmente, as migrations de
RAG emitem warning e seguem (feature RAG degradada — não afeta a suite).

## 3. Rodando

```bash
# suite completa (na raiz do repo; ~3 min)
DATABASE_URL='postgresql://postgres:postgres@localhost:5432/auditoria_test' \
  python -m pytest tests/backend -q

# frontend: type-check + build
npx tsc -b && npm run build
```

Resultado esperado: **0 failed**. Os ~47 skips são testes marcados
`skipUnless` para dependências opcionais — normais.

## 4. Convenções

- Teste novo acompanha toda mudança de comportamento; o docstring referencia
  a versão (`logs/versions/x.y.z.md`) que define o contrato.
- Testes que tocam o banco limpam o que criam (setUp/tearDown).
- Mocks de resultado de transcrição PRECISAM de
  `audio_quality={"transcription_provider": {"selected_strategy": "fast"}}` —
  sem isso a política do candidate selector descarta o item antes do ponto
  testado (lição da v1.3.124).
- Falhou na suite? Primeiro confira se o contrato mudou de propósito em
  `logs/versions/` antes de "consertar" o código.
