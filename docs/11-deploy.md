# Deploy do sistema — requisitos e mapeamento para a infra da empresa

> Runbook de handover. Descreve o que o sistema PRECISA de qualquer
> plataforma de containers e mapeia o deploy atual (Google Cloud Run) para o
> equivalente na infra da empresa — com Azure Container Apps como exemplo
> anotado, já que o destino indicado é o Azure do time de engenharia.
> **Nenhum recurso é criado por este lado**: este documento e o workflow
> `.example` são entregues prontos para o time executar.

## 1. O que o sistema exige da plataforma (qualquer uma)

| Requisito | Valor / observação |
| --- | --- |
| Runtime | 1 container Docker (imagem multi-stage já pronta: build do front Vite + Python 3.11-slim + ffmpeg) |
| Porta | `8080` (env `PORT` respeitada) |
| Health check | `GET /api/health` → 200 |
| Banco | PostgreSQL >= 17 com pgvector (ver `docs/10-migracao-banco.md`) |
| Migrations | Automáticas no boot (`prestart.py` → `init_db()`); idempotentes |
| Variáveis de ambiente | Template completo em `backend/.env.example` (179 vars, segredos via vault — ver `docs/08-seguranca.md` §3) |
| Agendador externo | 1 chamada/dia: `POST /api/telefonia/cron/sync` com header `Authorization: Bearer <CRON_SECRET_TOKEN>` |
| Storage de mídia | `MEDIA_STORAGE_BACKEND`: `local` (volume), `gcs` (atual) ou `azure_blob` (adapter pronto, dormente — habilitar `azure-storage-blob` no requirements) |
| Timeout de request | Auditoria manual pode levar minutos — timeout do serviço >= 600s (Cloud Run usa 3600s) |
| Escala | 1 instância atende a operação atual; `min instances = 0` funciona (cold start ~15s) |
| Egress | Azure OpenAI/Speech (HTTPS), Huawei AICC (`brazilsaas.aicccloud.com:28443`), banco PostgreSQL |

## 2. Deploy atual (referência — Google Cloud Run)

- Imagem buildada do `Dockerfile` da raiz (multi-stage Node 20 → Python 3.11).
- `--cpu-throttling --min-instances=0 --timeout=3600`, porta 8080.
- Cron: Google Cloud Scheduler → `POST /api/telefonia/cron/sync` 1x/dia.
- Workflow `.github/workflows/deploy-cloudrun.yml` (push na `main` =
  deploy em produção — **cuidado ao fazer merge**).
- Segredos: variáveis de ambiente do serviço Cloud Run.

## 3. Mapeamento para Azure (exemplo a executar pelo time)

| Hoje (GCP) | Equivalente Azure |
| --- | --- |
| Cloud Run | **Azure Container Apps** (ou App Service for Containers) |
| Artifact Registry | Azure Container Registry (ACR) |
| Cloud Scheduler | Container Apps **Job agendado** (ou Logic App) chamando o endpoint de cron |
| Env vars no serviço | Key Vault + `secretRef` (tabela pronta em `docs/08-seguranca.md` §3) |
| GCS (mídia) | Azure Blob Storage via `MEDIA_STORAGE_BACKEND=azure_blob` |
| Neon PostgreSQL | PostgreSQL gerenciado da empresa (ver `docs/10-migracao-banco.md`) |

Parâmetros recomendados no Container Apps: porta 8080; probe de liveness
`/api/health`; `minReplicas: 0`, `maxReplicas: 1`; CPU 1 / memória 2 GiB
(transcrição usa ffmpeg + pydub em memória); timeout de ingress >= 600s.

## 4. CI/CD

`.github/workflows/deploy-azure.yml.example` espelha o pipeline atual
(build da imagem + deploy) para o time adaptar: é um ARQUIVO EXEMPLO, com
sufixo `.example`, **inativo por design** — renomear e preencher os secrets
só quando a infra deles existir. Se o time usa Azure DevOps, o Dockerfile é
o mesmo; só o YAML de pipeline muda.

## 5. Ordem de migração sugerida (sistema + banco)

1. Provisionar banco (requisitos em `docs/10` §1) e rodar a migração de
   dados (`scripts/migration/`), OU subir banco vazio (seeds completos no boot).
2. Provisionar Key Vault e cadastrar os segredos JÁ ROTACIONADOS
   (`docs/08-seguranca.md` §2.2 — as chaves atuais estão comprometidas no
   histórico do git e NÃO devem ser reaproveitadas).
3. Build da imagem + deploy do container com env completo
   (`backend/.env.example` como guia; `ENVIRONMENT=production`).
4. Smoke: `/api/health`, login, abrir Arquivos Salvos, 1 ciclo manual.
5. Agendar o cron (1x/dia) com o novo `CRON_SECRET_TOKEN`.
6. Desativar o ambiente GCP somente após dias de operação validada.

Checklist executável item a item: `docs/12-checklist-handover.md`.
