# Banco de Dados

## Estado atual
- Engine: PostgreSQL
- Conexao: `DATABASE_URL` (env var) ou fallback `postgresql://postgres:postgres@localhost:5432/auditoria`
- Pool: `psycopg2.pool.ThreadedConnectionPool` em `backend/db/connection.py`
- Inicializacao de schema: `backend/database.py:init_db`
- Papel atual de `backend/database.py`: bootstrap, seeds, fachada publica e compatibilidade com os repositorios
- Papel atual de `backend/persistence.py`: alias de compatibilidade para `backend/database.py`
- Bootstrap registrado em metadata: `init_db_with_migrations`
- Contrato de dominio centralizado em `backend/db/domain_constants.py`

## Fundacao criada
- Conexao e pool centralizados em `backend/db/connection.py`
- Helpers de evolucao de schema em `backend/db/schema_tools.py`
- Metadata basica persistida em `schema_metadata`
- Registro explicito de migracoes em `schema_migrations`
- Cada migracao agora vive em `backend/db/migration_steps/` e eh descoberta automaticamente por `backend/db/migrations.py`
- Repositorios por dominio em `backend/repositories/` para `auth`, `audits`, `classification_review`, `operators`, `saved_files`, `analytics`, `configuration`, `report_exports` e `supervisor_feedback`
- Schema runtime consolidado em `backend/db/runtime_schema.py` e aplicado pela migracao `20260306_002_runtime_schema`
- Indices operacionais por fluxo aplicados na migracao `20260306_003_query_indexes`
- Invariantes de dominio endurecidas na migracao `20260308_004_domain_invariants`

## Metadata registrada no bootstrap
- `db.engine`
- `schema.bootstrap`
- `schema.last_init_at`
- `migration.system`
- `migration.baseline`
- `migration.latest_known`
- `migration.last_applied`
- `schema.source_of_truth`
- `schema.domain_invariants`

## Nova migracao
```powershell
npm run db:new-migration -- ajuste_do_schema
```

## Inspecao local
```powershell
npm run db:info
```

## Bootstrap e migracao local
```powershell
npm run db:migrate
```

