# SQLite Coupling Inventory

Data de referencia: 2026-03-06

## Leitura geral
O sistema ainda e SQLite-first. Isso nao impede integracao read-only com SQL Server, mas impede migracao do banco principal sem adaptacao.

## Acoplamentos fortes

### Conexao e pragmas
- `backend/db/connection.py`
- Uso de `sqlite3.connect`
- Uso de `PRAGMA foreign_keys`
- Uso de `PRAGMA busy_timeout`
- Uso de `PRAGMA journal_mode = WAL`
- Uso de `PRAGMA synchronous = NORMAL`

### Inspecao de schema
- `backend/db/schema_tools.py`
- Uso de `PRAGMA table_info`
- Uso de `ALTER TABLE ... ADD COLUMN` no formato assumido para SQLite

### Metadados e introspecao do banco
- `backend/database.py`
- Uso de `sqlite_master`
- Leitura direta de `schema_migrations`

### Definicao de schema
- `backend/db/runtime_schema.py`
- Uso de `INTEGER PRIMARY KEY AUTOINCREMENT`
- Uso de `TEXT DEFAULT CURRENT_TIMESTAMP`
- Uso de `CREATE VIEW IF NOT EXISTS`

### DML e semantica especifica
- `backend/repositories/classification_review.py`
- Uso de `ON CONFLICT(hash_arquivo) DO UPDATE`
- Uso de `IFNULL`
- Uso de `datetime(atualizado_em)`
- Uso de `lastrowid`

## Acoplamentos medios

### Repositorios com SQL portavel, mas ainda tipados em sqlite
- `backend/repositories/audits.py`
- `backend/repositories/auth_users.py`
- `backend/repositories/operators.py`
- `backend/repositories/report_exports.py`
- `backend/repositories/saved_files.py`
- `backend/repositories/supervisor_feedback.py`
- `backend/repositories/analytics.py`

Pontos comuns:
- `sqlite3.Row`
- `lastrowid`
- convencao de placeholders `?`

## Acoplamentos em testes e scripts
- `backend/tests/test_database_security.py`
- `scripts/check_db.py`
- `scripts/find_denise.py`
- `scripts/migrate_criteria_to_sql.py`
- `scripts/rpa_download_ligacoes.py`

## O que isso significa na pratica

### Para integracao read-only com SQL Server
- Nao e problema estrutural.
- Basta criar um adaptador novo, sem tocar na camada transacional local.

### Para migrar o banco principal para SQL Server
- Seria necessario adaptar conexao, migracoes, introspecao, placeholders, upserts, retorno de IDs e parte dos testes.

## Ordem correta se um dia houver migracao do banco principal
1. Criar interface de conexao por provider.
2. Isolar SQL especifico em adaptadores.
3. Reescrever migracoes para dialeto suportado.
4. Readequar testes que hoje assumem SQLite.
