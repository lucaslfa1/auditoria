# Migração do banco de dados — Neon → PostgreSQL gerenciado da empresa

> Runbook de handover. Move o banco completo (schema + dados) do Neon para o
> PostgreSQL que o time de engenharia escolher. **O serviço de destino ainda
> não está definido** — este documento fixa os REQUISITOS que qualquer escolha
> precisa atender e usa o Azure Database for PostgreSQL apenas como exemplo
> anotado. Scripts prontos em `scripts/migration/`. Ninguém deste lado executa
> a migração: os scripts são entregues prontos para o time rodar.

## 1. Requisitos do destino (inegociáveis sem reescrita)

| Requisito | Por quê |
| --- | --- |
| **PostgreSQL** (engine) | Todo o backend usa psycopg2, `information_schema`, placeholders `%s`, views PG. Trocar de engine (ex.: SQL Server) = reescrever a camada de dados inteira. |
| **Versão >= 17** | A origem (Neon) é PostgreSQL 17.10; `pg_restore` de dump 17 em servidor mais antigo não é suportado. |
| **Extensão `vector` (pgvector)** | Tabelas de RAG (`procedimento_chunks`, embeddings). Obrigatória. |
| **TLS (`sslmode=require`)** | O backend força SSL para hosts não-locais (`backend/db/connection.py`). |
| Extensão `pg_stat_statements` | Opcional (observabilidade). |

Qualquer PostgreSQL gerenciado que atenda a isso serve: Azure Database for
PostgreSQL Flexible Server, AWS RDS/Aurora PostgreSQL, Cloud SQL, ou
PostgreSQL auto-hospedado pela empresa.

## 2. Fatos da origem (verificados em 2026-06-11)

| Item | Valor |
| --- | --- |
| Projeto Neon | `auditoria-nstech-2` (região `aws-sa-east-1`) |
| Versão PostgreSQL | **17.10** |
| Tamanho do banco | **46 MB** (migração leva minutos, não horas) |
| Tabelas (schema public) | 44 |
| Migrations aplicadas | 52 (53 após deploy da v1.3.114, que cria `api_usage_daily`) |
| Extensões | `vector 0.8.0` (**obrigatória**), `pg_stat_statements` (opcional), `plpgsql` (builtin) |

## 3. Preparação do destino

1. Provisionar PostgreSQL >= 17 (responsável: time de engenharia, na infra deles).
2. Habilitar **pgvector** ANTES do restore. Exemplo no Azure Flexible Server:
   ```bash
   az postgres flexible-server parameter set \
     --resource-group <rg> --server-name <servidor> \
     --name azure.extensions --value 'VECTOR,PG_STAT_STATEMENTS'
   ```
   (Em RDS: disponível direto via `CREATE EXTENSION`; em Cloud SQL: flag
   `cloudsql.enable_pgvector`.)
3. Criar o banco vazio (ex.: `CREATE DATABASE auditoria;`).
4. Usuário de aplicação com owner do banco (o restore usa `--no-owner`: os
   objetos ficam do usuário da conexão).
5. Cliente `pg_dump`/`pg_restore` **>= 17** na máquina que executa.
6. Rede/firewall liberado para a máquina executora; `sslmode=require`.

## 4. Janela de migração (passo a passo)

A ordem congela escrita → copia → valida → aponta → descongela. Com 46 MB, a
janela inteira cabe em ~15 minutos.

1. **Congelar escrita** (nenhum dado novo durante a cópia):
   - Desabilitar o agendamento do cron (`/api/telefonia/cron/sync` — hoje
     Cloud Scheduler, 1x/dia).
   - Desligar a automação: config `automacao_hibrida_ativa=false` (ou
     kill-switch de custo `cost_kill_switch=true` na tabela `configuracoes`).
   - Avisar usuários (auditoria manual também escreve).
2. **Dump**: `NEON_DATABASE_URL=... ./scripts/migration/01_dump_neon.sh`
   (usa endpoint direto, sem `-pooler`).
3. **Restore**: `TARGET_DATABASE_URL=... ./scripts/migration/02_restore_destino.sh <arquivo.dump>`.
4. **Validar**: `SOURCE_DATABASE_URL=... TARGET_DATABASE_URL=... python scripts/migration/03_validate.py`
   — compara tabelas, contagens, migrations, sequences e pgvector. Só
   prosseguir com `RESULTADO: MIGRACAO VALIDADA`.
5. **Apontar o app**: trocar `DATABASE_URL` do backend para o novo servidor
   (connection string completa com `sslmode=require`) e reiniciar.
6. **Smoke**: `GET /api/health` → 200; login na UI; abrir Arquivos Salvos;
   disparar 1 ciclo manual de automação e acompanhar.
7. **Descongelar**: reativar cron/automação **já apontando para o novo banco**.

## 5. Rollback

O Neon permanece intocado durante toda a janela. Rollback = voltar a
`DATABASE_URL` antiga e reativar o cron. Não desprovisionar o Neon antes de
alguns dias de operação validada no destino.

## 6. Particularidades que merecem atenção

- **Pooler**: a connection string de produção atual usa o endpoint
  `*-pooler*` do Neon. O app tem pool interno (`DB_POOL_MAX_CONN=20`);
  começar SEM pooler externo (PgBouncer etc.) no destino e avaliar.
- **sslmode**: o backend força `sslmode=require` para hosts não-locais —
  nada a mudar.
- **Sequences**: o `pg_restore` de dump `-Fc` completo restaura sequences
  corretamente; o `03_validate.py` confere mesmo assim.
- **Encoding**: ambos UTF-8. Mensagens de erro do PG em pt-BR no Windows
  podem aparecer com acentuação corrompida em consoles cp1252 — cosmético.
- **Banco NOVO do zero (alternativa sem histórico)**: basta rodar o backend
  com `DATABASE_URL` apontando para um banco vazio — `init_db()` aplica as
  migrations e os seeds, **incluindo o catálogo oficial completo de
  critérios** (`backend/db/seeds/audit_catalog_oficial.sql`, 12 setores / 71
  alertas / 1051 critérios — v1.3.120). Requer pgvector habilitado antes
  (as migrations de RAG toleram ausência com warning, mas a feature fica
  degradada).

## 7. Ensaio executado (prova dos scripts — 2026-06-11)

Os scripts foram ensaiados localmente (PostgreSQL 16 local; **nenhum serviço
externo foi criado**): dump do banco de teste (38 tabelas, 53 migrations) →
restore em banco vazio → `03_validate.py`:

- ✅ [1/5] Tabelas: 38 = 38
- ✅ [2/5] Contagem de linhas por tabela: idênticas
- ✅ [3/5] Migrations aplicadas: 53 = 53
- ✅ [4/5] Sequences alinhadas
- ❌ [5/5] pgvector ausente no destino → **falha proposital**: o PG local não
  tem a extensão, provando que o check pega exatamente a configuração que
  faltaria no destino real sem o §3.2.

Aviso visto no ensaio e que NÃO ocorre na migração real: `SET
transaction_timeout` rejeitado (artefato de cliente PG18 contra servidor
PG16; origem e destino reais serão ambos PG17+).
