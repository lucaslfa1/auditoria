# Migração do banco de dados — Neon → Azure Database for PostgreSQL

> Runbook de handover. Move o banco completo (schema + dados) do Neon para o
> Azure Database for PostgreSQL Flexible Server da empresa. Scripts prontos em
> `scripts/migration/`. Validado por ensaio de dump/restore (ver §6).

## 1. Fatos da origem (verificados em 2026-06-11)

| Item | Valor |
| --- | --- |
| Projeto Neon | `auditoria-nstech-2` (região `aws-sa-east-1`) |
| Versão PostgreSQL | **17.10** |
| Tamanho do banco | **46 MB** (migração leva minutos, não horas) |
| Tabelas (schema public) | 44 |
| Migrations aplicadas | 52 (53 após deploy da v1.3.114, que cria `api_usage_daily`) |
| Extensões | `vector 0.8.0` (**obrigatória** — RAG/`procedimento_chunks`), `pg_stat_statements` (opcional, observabilidade), `plpgsql` (builtin) |

## 2. Pré-requisitos no Azure

1. **Flexible Server com PostgreSQL 17** (origem é 17; não usar versão menor).
2. **pgvector habilitado**: parâmetro de servidor `azure.extensions` deve
   incluir `VECTOR` *antes* do restore:
   ```bash
   az postgres flexible-server parameter set \
     --resource-group <rg> --server-name <servidor> \
     --name azure.extensions --value 'VECTOR,PG_STAT_STATEMENTS'
   ```
   (`PG_STAT_STATEMENTS` é opcional; sem ele, ignore o erro correspondente no
   restore.)
3. Banco criado: `CREATE DATABASE auditoria;` (ou nome de preferência do time).
4. Usuário de aplicação com owner do banco (o restore usa `--no-owner`: os
   objetos ficam do usuário da conexão).
5. Cliente `pg_dump`/`pg_restore` **versão >= 17** na máquina que executa.
6. Rede: firewall do Flexible Server liberado para a máquina executora;
   `sslmode=require` nas duas pontas.

## 3. Janela de migração (passo a passo)

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
3. **Restore**: `AZURE_DATABASE_URL=... ./scripts/migration/02_restore_azure.sh <arquivo.dump>`.
4. **Validar**: `SOURCE_DATABASE_URL=... TARGET_DATABASE_URL=... python scripts/migration/03_validate.py`
   — compara tabelas, contagens, migrations, sequences e pgvector. Só
   prosseguir com `RESULTADO: MIGRACAO VALIDADA`.
5. **Apontar o app**: trocar `DATABASE_URL` do backend para o Azure
   (connection string completa com `sslmode=require`) e reiniciar.
6. **Smoke**: `GET /api/health` → 200; login na UI; abrir Arquivos Salvos;
   disparar 1 ciclo manual de automação e acompanhar.
7. **Descongelar**: reativar cron/automação **já apontando para o Azure**.

## 4. Rollback

O Neon permanece intocado durante toda a janela. Rollback = voltar a
`DATABASE_URL` antiga e reativar o cron. Não desprovisionar o Neon antes de
alguns dias de operação validada no Azure.

## 5. Particularidades que merecem atenção

- **Pooler**: a connection string de produção atual usa o endpoint
  `*-pooler*` do Neon. No Azure, o equivalente é o PgBouncer embutido do
  Flexible Server (porta 6432) — opcional com o pool interno do app
  (`DB_POOL_MAX_CONN=20`); começar SEM PgBouncer e avaliar.
- **sslmode**: o backend força `sslmode=require` para hosts não-locais
  (`backend/db/connection.py`) — nada a mudar.
- **Sequences**: o `pg_restore` de dump `-Fc` completo restaura sequences
  corretamente; o `03_validate.py` confere mesmo assim (passo 4).
- **Encoding**: ambos UTF-8. Mensagens de erro do PG em pt-BR no Windows
  podem aparecer com acentuação corrompida em consoles cp1252 — cosmético.
- **Banco NOVO do zero (alternativa sem dados)**: basta rodar o backend com
  `DATABASE_URL` apontando para um banco vazio — `init_db()` aplica as
  migrations e os seeds, **incluindo o catálogo oficial completo de
  critérios** (`backend/db/seeds/audit_catalog_oficial.sql`, 12 setores / 71
  alertas / 1051 critérios — adicionado na v1.3.120). Requer pgvector
  habilitado antes (as migrations de RAG toleram ausência com warning, mas a
  feature fica degradada).

## 6. Ensaio executado (prova dos scripts — 2026-06-11)

Os scripts foram ensaiados contra um PostgreSQL 16 local: dump do banco de
teste (38 tabelas, 53 migrations) → restore em banco vazio → `03_validate.py`:

- ✅ [1/5] Tabelas: 38 = 38
- ✅ [2/5] Contagem de linhas por tabela: idênticas
- ✅ [3/5] Migrations aplicadas: 53 = 53
- ✅ [4/5] Sequences alinhadas
- ❌ [5/5] pgvector ausente no destino → **falha proposital**: o PG local não
  tem a extensão, provando que o check pega exatamente a configuração que
  faltaria no Azure sem o §2.2. Na migração real, habilite `VECTOR` em
  `azure.extensions` antes do restore e o check passa.

Avisos vistos no ensaio e que NÃO ocorrem na migração real: `SET
transaction_timeout` rejeitado (artefato de cliente PG18 contra servidor
PG16; Neon e Azure serão ambos PG17).
