# Plano de Migração — GCP/Neon → Azure Corporativo

**Status:** rascunho técnico v1 — 2026-05-28
**Autor:** Claude (assistido)
**Validação:** baseada na stack documentada em `process-flow.md` (versão 1.3.99)
**Decisão de hosting:** Azure Container Apps (ACA) — alinhada com o modelo serverless do Cloud Run atual

Este plano descreve o caminho de saída do GCP (Cloud Run + GCS + Neon) para um tenant Azure corporativo. Os serviços de IA (Azure OpenAI, Speech, Whisper, Text Analytics) já são Azure — só mudam de subscription. O código muda em **3 arquivos críticos** + **CI/CD**.

---

## 1. Inventário do que migrar

### 1.1 Recursos GCP em uso hoje

| Recurso | Identificação atual | Onde é referenciado no código |
|---|---|---|
| Cloud Run | service `auditoria`, região `southamerica-east1` | `.github/workflows/deploy-cloudrun.yml`, `Dockerfile` (CMD final) |
| GCS bucket | `auditoria-nstech-audios` | `backend/core/media_storage.py` (linhas 71-75, 186-196, 261-271, 326-337, 381-404), `backend/storage/audit_storage.py` (linhas 33-68, 70-75, 125-160, 219-221) |
| Artifact Registry | `southamerica-east1-docker.pkg.dev/auditoria-nstech/cloud-run-source-deploy/auditoria` | workflow GH |
| Cloud Scheduler | dispara `POST /api/automation/cron/run` com Bearer | infra GCP (fora do repo) |
| GitHub OIDC → GCP | `github-actions-deploy@auditoria-nstech.iam.gserviceaccount.com` via `workloadIdentityPools/github-pool` | workflow |
| Secret Manager (provável) | secrets injetados como env no Cloud Run | infra GCP |
| Cloud Logging | logs estruturados do Uvicorn | automático |

### 1.2 Recurso externo a manter (não muda)

- **Neon PostgreSQL** (`auditoria-nstech-2`, host `ep-aged-river-acr5e219`) — **vai sair**, migra para Azure DB for PostgreSQL Flexible Server
- **Sentry SaaS** — pode continuar ou trocar por Application Insights (decisão DevOps)
- **Huawei AICC** (CMS/FS em `brazilsaas.aicccloud.com:28443`) — externo, segue igual
- **Azure OpenAI / Speech / Whisper / Text Analytics** — já é Azure, **muda só a subscription**

### 1.3 Mapeamento direto Azure

| Componente | Serviço Azure | SKU sugerido | Região |
|---|---|---|---|
| Banco | Azure Database for PostgreSQL — Flexible Server | `Standard_D2ds_v5` (2 vCPU / 8GB) + 64GB storage, PG 16 | Brazil South |
| Storage áudios | Azure Storage Account v2 (Blob) | StorageV2, Hot tier, LRS, soft-delete 7d, versioning off | Brazil South |
| Hosting | Azure Container Apps Environment + App | Consumption profile, scale-to-zero, min=0/max=10 | Brazil South |
| Container registry | Azure Container Registry | Standard | Brazil South |
| Cron | Azure Container Apps **Job** (scheduled) | Consumption | Brazil South |
| Secrets | Azure Key Vault | Standard | Brazil South |
| Observabilidade | Log Analytics Workspace + Application Insights | Pay-as-you-go | Brazil South |
| IA (já existe, nova sub) | Azure OpenAI (GPT-4o + Whisper + transcribe-diarize), Speech S0, Language S0 | Mesmo modelos | East US 2 (GPT-4o/Whisper); Brazil South se Speech tiver capacidade |
| Identidade GH Actions → Azure | App Registration + Federated Credential | n/a | n/a |

---

## 2. Fase 1 — Provisionamento (TI corp executa)

### 2.1 Pacote de solicitação para a TI

```text
RESOURCE GROUP:  rg-auditoria-nstech-prod   (Brazil South)
RESOURCE GROUP:  rg-auditoria-nstech-ai     (East US 2 — só para Azure OpenAI/Whisper)

Subscription:    <a definir pela TI>
Tags obrigatórias: env=prod, app=auditoria-nstech, owner=lucas.afonso
```

Recursos pedidos:

1. **PostgreSQL Flexible Server**
   - Nome: `pg-auditoria-prod`
   - Versão: PG 16
   - SKU: `Standard_D2ds_v5` (2 vCPU, 8 GiB RAM) — provisionar com 64 GiB de storage (auto-grow ON)
   - Backup: 7 dias retenção (point-in-time)
   - Extensões a habilitar via `azure.extensions`: `uuid-ossp`, `pgcrypto`, `pg_stat_statements`
   - High Availability: zone-redundant OFF na fase 1 (custo); reavaliar depois
   - Networking: **Public access com firewall** (libera IPs do ACA Environment + IP do Lucas para migração) **ou** Private Endpoint em VNet (preferível se corp exigir)
   - Admin user: `pgadmin` (senha no Key Vault)

2. **Storage Account**
   - Nome: `stauditoriaprod<sufixo>` (precisa ser globalmente único, sem hífen)
   - Kind: StorageV2, Performance: Standard, Replication: LRS
   - Containers a criar: `audios` (acesso privado), `backups` (acesso privado)
   - Soft delete blobs: 7 dias
   - Versionamento: desligado (não usamos hoje no GCS)

3. **Container Registry**
   - Nome: `cracrauditoriaprod` (globalmente único)
   - SKU: Standard
   - Admin user: desligado (usar managed identity)

4. **Container Apps Environment + App + Job**
   - Environment: `cae-auditoria-prod`
   - App: `aca-auditoria-api` (ingress externo, porta 8080, scale 0..10, min replicas=0)
   - Job: `acaj-cron-automation` — cron `0,30 * * * *` (a cada 30min, igual ao Cloud Scheduler de hoje) executando script que faz `curl POST $INTERNAL_API_URL/api/automation/cron/run -H "Authorization: Bearer $CRON_TOKEN"`

5. **Key Vault**
   - Nome: `kv-auditoria-prod`
   - SKU: Standard
   - Acesso: RBAC (não policies)
   - Segredos a criar (ver §5.3): `database-url`, `azure-openai-key`, `azure-speech-key`, `azure-whisper-key`, `azure-text-analytics-key`, `huawei-ak`, `huawei-sk`, `huawei-direct-app-key`, `huawei-direct-app-secret`, `session-secret`, `gemini-api-key`, `sentry-dsn`, `cron-bearer-token`

6. **Log Analytics + Application Insights**
   - Workspace `log-auditoria-prod`
   - AppInsights `appi-auditoria-prod` apontado para o workspace

7. **Azure OpenAI** (no RG `rg-auditoria-nstech-ai`, East US 2)
   - Resource: `oai-auditoria-prod`
   - Deployments necessários:
     - `gpt-4o` (modelo `gpt-4o` versão atual) — cota mínima: ~200k TPM (avaliação principal)
     - `whisper` — cota mínima: ~5 audios/min concorrentes
     - `gpt-4o-transcribe-diarize` (se disponível na região; senão manter East US 2)

8. **Azure AI Speech**
   - Resource: `speech-auditoria-prod`, SKU S0, Brazil South ou East US 2 (Fast Transcription disponível em ambas)

9. **Azure AI Language (Text Analytics)**
   - Resource: `lang-auditoria-prod`, SKU S0

10. **Identidades**
    - **Managed Identity** atribuída ao ACA App: papéis `AcrPull` no ACR, `Key Vault Secrets User` no Key Vault, `Storage Blob Data Contributor` no Storage Account, `Cognitive Services User` em cada recurso de IA. Para conectar ao Postgres via Entra ID (preferível), adicionar como **Azure AD admin** do Flexible Server.
    - **App Registration** (`sp-github-deploy-auditoria`) com **Federated Credential** apontando para `repo:lucaslfa84/auditoria:ref:refs/heads/main`. Papel `Contributor` no RG de prod (escopo restrito a `aca-auditoria-api` + `cracrauditoriaprod`).

### 2.2 Cotas a confirmar antes de pedir

- Azure OpenAI **GPT-4o**: o tenant corp já tem aprovação de uso responsável? Se não, abrir solicitação **antes** (process de aprovação leva 3-5 dias úteis em alguns tenants).
- Azure OpenAI **Whisper**: disponibilidade regional limitada — confirmar se East US 2 tem capacity no tenant corp.
- PostgreSQL Flexible Server `Standard_D2ds_v5` em Brazil South: confirmar quota.

---

## 3. Fase 2 — Migração de dados

### 3.1 Banco de dados (Neon → Flexible Server)

**Janela:** ~30 min (depende do tamanho do dump; estimo < 5 GB hoje)

Pré-requisitos no host de migração (laptop Lucas ou VM efêmera):
- `pg_dump` e `pg_restore` versão ≥ 16 (mesma major version do destino)
- Credenciais Neon (read-only suficiente)
- Credenciais admin do Flexible Server

**Passo 1 — Dump paralelo do Neon:**

```bash
# Variáveis
export NEON_HOST="ep-aged-river-acr5e219.sa-east-1.aws.neon.tech"
export NEON_DB="auditoria-nstech-2"
export NEON_USER="<user>"
export PGPASSWORD="<senha-neon>"

# Dump em directory format com 4 cores (ajustar -j conforme CPUs disponíveis)
pg_dump \
  -h "$NEON_HOST" \
  -U "$NEON_USER" \
  -d "$NEON_DB" \
  -Fd -j 4 \
  --no-owner --no-acl \
  --verbose \
  -f neon_dump_$(date +%Y%m%d_%H%M).dir 2> dump.log
```

> `--no-owner --no-acl` evita conflitos com roles que existem no Neon mas não no Flexible Server.

**Passo 2 — Criar banco no destino:**

```bash
export AZ_HOST="pg-auditoria-prod.postgres.database.azure.com"
export AZ_USER="pgadmin"
export PGPASSWORD="<senha-azure>"

createdb -h "$AZ_HOST" -U "$AZ_USER" auditoria
```

**Passo 3 — Restore paralelo:**

```bash
pg_restore \
  -h "$AZ_HOST" \
  -U "$AZ_USER" \
  -d auditoria \
  -j 4 \
  --no-owner --no-acl \
  --verbose \
  neon_dump_*.dir 2> restore.log
```

**Passo 4 — Validação de integridade:**

Rodar contra os dois bancos e comparar:

```sql
-- Row count por tabela crítica
SELECT 'audits' AS t, COUNT(*) FROM audits
UNION ALL SELECT 'fila_revisao_classificacao', COUNT(*) FROM fila_revisao_classificacao
UNION ALL SELECT 'audit_media_files', COUNT(*) FROM audit_media_files
UNION ALL SELECT 'media_files', COUNT(*) FROM media_files
UNION ALL SELECT 'colaboradores', COUNT(*) FROM colaboradores
UNION ALL SELECT 'audit_sectors', COUNT(*) FROM audit_sectors
UNION ALL SELECT 'audit_alerts', COUNT(*) FROM audit_alerts
UNION ALL SELECT 'audit_criteria', COUNT(*) FROM audit_criteria
UNION ALL SELECT 'configuracoes', COUNT(*) FROM configuracoes
UNION ALL SELECT 'arquivos_salvos', COUNT(*) FROM arquivos_salvos
UNION ALL SELECT 'users', COUNT(*) FROM users;

-- Max IDs (sanity check pra sequences)
SELECT MAX(id) FROM audits;
SELECT MAX(id) FROM fila_revisao_classificacao;

-- Last activity por tabela hot
SELECT MAX(created_at) FROM audits;
SELECT MAX(updated_at) FROM fila_revisao_classificacao;
```

**Passo 5 — Reset de sequences (necessário se `pg_restore` não importou):**

```sql
SELECT setval(
  pg_get_serial_sequence('audits', 'id'),
  COALESCE((SELECT MAX(id) FROM audits), 1)
);
-- Repetir para cada tabela com SERIAL
```

### 3.2 Áudios (GCS → Azure Blob)

**Janela:** ~1-2h (depende do volume; AzCopy roda server-side, não consome banda local)

**Passo 1 — Service account key do GCP** com role `roles/storage.objectViewer` no bucket:

```bash
gcloud iam service-accounts create azcopy-migrator \
  --display-name="Azure migration"
gcloud projects add-iam-policy-binding auditoria-nstech \
  --member="serviceAccount:azcopy-migrator@auditoria-nstech.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
gcloud iam service-accounts keys create gcs-key.json \
  --iam-account=azcopy-migrator@auditoria-nstech.iam.gserviceaccount.com
```

**Passo 2 — Autorizar AzCopy:**

```bash
# Linux/Mac
export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/gcs-key.json"
azcopy login   # Entra ID para o destino Azure
```

**Passo 3 — Cópia em massa (server-to-server, não passa pelo laptop):**

```bash
azcopy copy \
  'https://storage.cloud.google.com/auditoria-nstech-audios' \
  'https://stauditoriaprod<sufixo>.blob.core.windows.net/audios' \
  --recursive=true \
  --s2s-handle-invalid-metadata=RenameIfInvalid \
  --log-level=INFO
```

> Salvar o `JobID` retornado para retomar caso haja interrupção: `azcopy jobs resume <JobID>`.

**Passo 4 — Validação:**

```bash
# Contagem de blobs Azure
az storage blob list \
  --account-name stauditoriaprod<sufixo> \
  --container-name audios \
  --auth-mode login \
  --query "length(@)" -o tsv

# Contagem de objetos GCS para conferir
gsutil ls -r gs://auditoria-nstech-audios/** | wc -l
```

**Passo 5 — Limpeza:**

Revogar e deletar a service account key após confirmação:

```bash
gcloud iam service-accounts keys delete <KEY_ID> \
  --iam-account=azcopy-migrator@auditoria-nstech.iam.gserviceaccount.com
gcloud iam service-accounts delete \
  azcopy-migrator@auditoria-nstech.iam.gserviceaccount.com
```

### 3.3 Sincronização incremental durante cutover

Se a janela do cutover não for instantânea (improvável para esse volume), rodar:

```bash
# Sync diferencial 1h antes do go-live
azcopy sync \
  'https://storage.cloud.google.com/auditoria-nstech-audios' \
  'https://stauditoriaprod<sufixo>.blob.core.windows.net/audios' \
  --recursive=true
```

---

## 4. Fase 3 — Adaptação de código

Três arquivos críticos + CI/CD + dependências.

### 4.1 `backend/requirements.txt`

**Adicionar** (não remover ainda — manter fallback GCP durante cutover paralelo):

```diff
+azure-storage-blob>=12.19.0
+azure-identity>=1.16.0
```

Após validar Azure em prod por 14 dias, remover:

```diff
-google-cloud-storage>=2.16.0
-google-auth==2.48.0
```

> `google-genai==1.65.0` **permanece** — é a SDK do Gemini (avaliação fallback), não tem a ver com GCS.

### 4.2 `backend/db/connection.py`

**Zero mudança de código.** Trocar apenas a env var:

```diff
# .env / Key Vault secret
-DATABASE_URL=postgresql://user:pass@ep-aged-river-acr5e219...neon.tech/auditoria-nstech-2?sslmode=require
+DATABASE_URL=postgresql://pgadmin:<pwd>@pg-auditoria-prod.postgres.database.azure.com:5432/auditoria?sslmode=require
```

A função `get_database_url()` em `connection.py:79-106` já força `sslmode=require` quando ausente. Pool, keepalive, timeouts continuam idênticos.

**Opcional (recomendado):** passar a usar Entra ID em vez de password. Requer mudar a senha no DSN por um token de curta duração obtido via `DefaultAzureCredential`. Adia para fase 2 pós-migração.

### 4.3 `backend/core/media_storage.py`

Adicionar backend `"azure"` mantendo `"gcs"` e `"local"`. Diff conceitual (não aplicar ainda — só referência para a fase de implementação):

```python
# Adicionar import lazy no topo do arquivo (mesma estratégia do google.cloud)
# Nenhuma mudança de import global; carregamento sob demanda dentro das funções.

def _get_default_backend() -> str:
    env_backend = os.getenv("MEDIA_STORAGE_BACKEND", "").strip().lower()
    if env_backend:
        return env_backend

    # CONTAINER_APP_NAME é a env padrão do Azure Container Apps
    # K_SERVICE é a do Cloud Run (mantido como fallback durante cutover)
    if (
        os.getenv("ENVIRONMENT", "").strip().lower() == "production"
        or os.getenv("CONTAINER_APP_NAME")
        or os.getenv("K_SERVICE")
    ):
        # Preferir Azure quando ambos os env são ausentes (default pós-migração)
        if os.getenv("AZURE_STORAGE_ACCOUNT"):
            return "azure"
        return "gcs"
    return "local"


def _get_azure_account_url() -> str:
    name = os.getenv("AZURE_STORAGE_ACCOUNT", "").strip()
    if not name:
        raise MediaStorageError("AZURE_STORAGE_ACCOUNT nao configurado.")
    return f"https://{name}.blob.core.windows.net"


def _get_azure_container_name() -> str:
    return os.getenv("AZURE_STORAGE_CONTAINER", "audios").strip() or "audios"


def _get_azure_blob_client(storage_key: str):
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    service = BlobServiceClient(
        account_url=_get_azure_account_url(),
        credential=DefaultAzureCredential(),
    )
    return service.get_blob_client(container=_get_azure_container_name(), blob=storage_key)
```

Para cada uma das quatro funções, adicionar branch `elif backend == "azure":` espelhando a lógica GCS:

| Função | Operação GCS hoje | Equivalente Azure Blob |
|---|---|---|
| `store_media` (linha 186-196) | `blob.upload_from_string(content_bytes, content_type=...)` | `client.upload_blob(content_bytes, overwrite=True, content_settings=ContentSettings(content_type=...))` |
| `load_media_bytes` (linha 261-271) | `blob.download_as_bytes()` | `client.download_blob().readall()` |
| `delete_media` (linha 326-337) | `blob.exists()` + `blob.delete()` | `client.exists()` + `client.delete_blob()` |
| `open_media_stream` (linha 381-404) | `blob.open("rb")` + chunk iterator | `client.download_blob()` + iterar `chunks(chunk_size=_AUDIO_STREAM_CHUNK_SIZE)` |

> **Detalhe importante:** `_AUDIO_STREAM_CHUNK_SIZE` (linha 18) já está pronto; só passar como `max_chunk_get_size` ao `download_blob()` (parâmetro do BlobClient) ou usar `iter_chunks()`.

### 4.4 `backend/storage/audit_storage.py`

A classe `CloudStorageFile` (linhas 33-68) e a função `store_audit_audio_file` (linhas 116-213) têm read-back obrigatório (v1.3.85, `AudioUploadVerificationError`). Portar:

| Hoje (GCS) | Azure Blob equivalente |
|---|---|
| `blob.reload()` + `blob.size` | `blob_client.get_blob_properties().size` |
| `blob.delete()` para limpar orfão | `blob_client.delete_blob()` |
| `gs://{bucket}/{path}` em logs | `https://{account}.blob.core.windows.net/{container}/{path}` |

Estratégia recomendada: introduzir um **adapter** com a mesma interface de `CloudStorageFile` para Azure e selecionar via env. Diff conceitual:

```python
class AzureBlobFile:
    def __init__(self, container, blob_name):
        self.container = container
        self.blob_name = blob_name
        self.name = Path(blob_name).name

    def _client(self):
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
        return BlobServiceClient(
            account_url=_get_azure_account_url(),
            credential=DefaultAzureCredential(),
        ).get_blob_client(container=self.container, blob=self.blob_name)

    def exists(self):
        try:
            return self._client().exists()
        except Exception as e:
            logger.error("Azure Blob exists error: %s", e)
            return False

    def unlink(self, missing_ok=False):
        try:
            self._client().delete_blob()
        except Exception:
            if not missing_ok:
                raise

    def read_bytes(self):
        return self._client().download_blob().readall()
```

E em `resolve_stored_audit_audio_path` (linha 215-227), selecionar adapter por env (`AZURE_STORAGE_ACCOUNT` → `AzureBlobFile`, `GCS_BUCKET_NAME` → `CloudStorageFile`).

A função `store_audit_audio_file` deve detectar o backend pela mesma lógica e fazer o read-back equivalente. Manter os `AudioUploadVerificationError` com mensagens contendo o URL Azure quando estiver no backend Azure.

### 4.5 `backend/scripts/backfill_media_files.py`

Revisar: provavelmente lê paths `gs://...` e popula `media_files`. Após a migração de áudio, rodar uma vez para converter os paths armazenados:

- `gs://auditoria-nstech-audios/2026/05/audit_123_abc.wav` → `https://stauditoriaprod<sufixo>.blob.core.windows.net/audios/2026/05/audit_123_abc.wav`

Alternativa mais limpa: armazenar apenas o **path relativo** no DB (já é o caso em `audit_storage_path`), e construir a URL completa só no momento da leitura. Verificar se algum lugar armazena URL absoluta com prefixo `gs://`.

```sql
-- Auditoria pré-cutover: quantas linhas têm paths absolutos no formato gs://
SELECT COUNT(*) FROM media_files WHERE storage_key LIKE 'gs://%';
SELECT COUNT(*) FROM audit_media_files WHERE storage_path LIKE 'gs://%';
```

Se a contagem for zero, a migração de paths é trivial (não precisa script). Se > 0, criar script de UPDATE em massa.

### 4.6 Novas env vars

Adicionar a `.env.example` e à configuração do ACA App (vinculando ao Key Vault):

```bash
# Storage Azure Blob (substitui GCS)
AZURE_STORAGE_ACCOUNT=stauditoriaprodxxxx
AZURE_STORAGE_CONTAINER=audios
MEDIA_STORAGE_BACKEND=azure   # ou deixar vazio e auto-detectar

# Manter durante cutover paralelo (depois remover)
GCS_BUCKET_NAME=auditoria-nstech-audios
```

E **remover** após cutover:
- `GCS_BUCKET_NAME`
- Qualquer `GOOGLE_APPLICATION_CREDENTIALS` (não está no `.env.example` atual, mas pode estar setada no Cloud Run via service account vinculada)

### 4.7 `Dockerfile`

**Zero mudança.** Imagem Python 3.11-slim, ffmpeg, uvicorn — roda igual no ACA. A única atenção é garantir que a tag final seja publicada no ACR em vez do Artifact Registry (cuidado é do CI, não do Dockerfile).

---

## 5. Fase 4 — CI/CD, cron e segredos

### 5.1 GitHub Actions: `.github/workflows/deploy-aca.yml`

Substitui `deploy-cloudrun.yml`. Esboço:

```yaml
name: Build and Deploy to Azure Container Apps

on:
  push:
    branches: ["main"]

env:
  AZURE_RG: rg-auditoria-nstech-prod
  ACR_NAME: cracrauditoriaprod
  IMAGE_NAME: auditoria
  ACA_APP: aca-auditoria-api
  AZURE_REGION: brazilsouth

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Azure login (OIDC federado)
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Build + push para o ACR (server-side, sem docker local)
        run: |
          az acr build \
            --registry "$ACR_NAME" \
            --image "$IMAGE_NAME:${{ github.sha }}" \
            --image "$IMAGE_NAME:latest" \
            --file Dockerfile \
            .

      - name: Deploy revisao no Container App
        run: |
          az containerapp update \
            --name "$ACA_APP" \
            --resource-group "$AZURE_RG" \
            --image "${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${{ github.sha }}"

      - name: Mostrar FQDN
        run: |
          az containerapp show \
            --name "$ACA_APP" \
            --resource-group "$AZURE_RG" \
            --query "properties.configuration.ingress.fqdn" -o tsv
```

> O App Registration `sp-github-deploy-auditoria` precisa de **Federated Credential** para o subject `repo:lucaslfa84/auditoria:ref:refs/heads/main` (sem secret estático).

### 5.2 Container Apps Job para o cron (substitui Cloud Scheduler)

Criar via Bicep/CLI no provisionamento. Comando manual de referência:

```bash
az containerapp job create \
  --name acaj-cron-automation \
  --resource-group rg-auditoria-nstech-prod \
  --environment cae-auditoria-prod \
  --trigger-type Schedule \
  --cron-expression "0,30 * * * *" \
  --replica-timeout 300 \
  --replica-retry-limit 1 \
  --parallelism 1 \
  --image mcr.microsoft.com/cbl-mariner/base/core:2.0 \
  --command "/bin/bash" "-c" \
    'curl -sS -X POST "$INTERNAL_API_URL/api/automation/cron/run" \
     -H "Authorization: Bearer $CRON_TOKEN" \
     -H "Content-Type: application/json" \
     -d "{}" || exit 1' \
  --env-vars \
    "INTERNAL_API_URL=https://<aca-fqdn>" \
    "CRON_TOKEN=secretref:cron-bearer-token"
```

### 5.3 Segredos no Key Vault e no ACA

Cada secret do Key Vault é referenciado no ACA App como `secretref:<nome>`. Exemplo via CLI:

```bash
az containerapp secret set \
  --name aca-auditoria-api \
  --resource-group rg-auditoria-nstech-prod \
  --secrets \
    "database-url=keyvaultref:https://kv-auditoria-prod.vault.azure.net/secrets/database-url,identityref:system" \
    "azure-openai-key=keyvaultref:..." \
    "huawei-ak=keyvaultref:..." \
    "huawei-sk=keyvaultref:..." \
    "session-secret=keyvaultref:..."
```

E as env vars do app apontam para os secrets:

```bash
az containerapp update \
  --name aca-auditoria-api \
  --resource-group rg-auditoria-nstech-prod \
  --set-env-vars \
    "DATABASE_URL=secretref:database-url" \
    "AZURE_OPENAI_KEY=secretref:azure-openai-key" \
    "AZURE_SPEECH_KEY=secretref:azure-speech-key" \
    "HUAWEI_AK=secretref:huawei-ak" \
    "HUAWEI_SK=secretref:huawei-sk" \
    "SESSION_SECRET=secretref:session-secret" \
    "GEMINI_API_KEY=secretref:gemini-api-key" \
    "SENTRY_DSN=secretref:sentry-dsn" \
    "ENVIRONMENT=production" \
    "AZURE_STORAGE_ACCOUNT=stauditoriaprodxxxx" \
    "AZURE_STORAGE_CONTAINER=audios" \
    "MEDIA_STORAGE_BACKEND=azure"
```

---

## 6. Cutover paralelo

Janela total: ~3-4h de baby-sitting; sistema fica disponível em GCP até o último switch DNS.

| T | Ação | Sistema servindo tráfego |
|---|---|---|
| T−7d | Recursos Azure provisionados, validados smoke | Cloud Run (GCP) |
| T−2d | Branch `feat/azure-migration` mergeado em `main`, deploy duplo (Cloud Run + ACA via GH Action) | Cloud Run |
| T−1d | `pg_dump` do Neon, `pg_restore` no Flexible Server, validação row counts | Cloud Run |
| T−1d | `azcopy copy` GCS → Blob, validação | Cloud Run |
| T−4h | Smoke test no ACA com `DATABASE_URL` apontando para PG novo + `AZURE_STORAGE_ACCOUNT` setado: upload manual de 1 audio, sync D-1 de 1h, audit completo | Cloud Run |
| T−1h | `azcopy sync` final (delta últimos minutos) | Cloud Run |
| **T0** | Pausar Cloud Scheduler GCP. Pausar ACA Job (precaução). | Cloud Run (read-only de fato — fila estática) |
| T+5min | Validar que automation_cycle_runs está limpo (sem ciclos in_progress) | Cloud Run |
| T+10min | DNS / proxy reverso corporativo: aponta domínio para FQDN do ACA. Cloud Run continua respondendo URL antiga. | ACA (clientes que recarregaram) + Cloud Run (em cache) |
| T+30min | Ativar ACA Job (cron) | ACA |
| T+1h | Validar 1 ciclo automático completo no ACA (Fase 1 → Fase 5) | ACA |
| T+24h | Monitorar dashboards (Application Insights), Sentry, Neon (deve estar zerado de conexões), GCS (sem novos uploads) | ACA |

### 6.1 Rollback (até T+7d)

Se algo der errado em qualquer ponto após T0:

1. Reativar Cloud Scheduler no GCP.
2. Reverter DNS para Cloud Run.
3. Cloud Run ainda está com `DATABASE_URL` apontando para o Neon **original** — Neon não foi tocado. Deltas no Flexible Server pós-T0 são perdidos (aceitar como custo do rollback).
4. Áudios novos gravados no Blob pós-T0: rodar `azcopy copy` reverso para GCS (Blob → GCS via sync), opcional.
5. Investigar root cause antes de tentar segundo cutover.

### 6.2 Decomissionamento (T+14d, após validação)

1. **Cloud Run:** `gcloud run services delete auditoria --region southamerica-east1`
2. **Cloud Scheduler:** deletar job (já desabilitado em T0)
3. **GCS bucket:** confirmar via `gsutil ls` que nada novo foi gravado, então deletar bucket (`gsutil rm -r gs://auditoria-nstech-audios`)
4. **Artifact Registry:** deletar repositório
5. **Workload Identity Pool + Service Account GitHub:** revogar acesso
6. **Neon:** tirar projeto do plano pago (pode manter free tier para histórico se útil)
7. **Remover dependências GCP** de `requirements.txt` (diff §4.1) e código GCP de `media_storage.py` / `audit_storage.py` em um PR `chore/remove-gcp-deps`.

---

## 7. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Latência Brazil South para Azure OpenAI East US 2 piora SLA da auditoria | Média | Médio | Já é o caso hoje (Azure OpenAI está em East US 2 / Sweden) — não muda. Monitorar p95. |
| Cota Azure OpenAI corp não comporta produção | Baixa | Alto | Pedir cota igual à atual ANTES de migrar; rodar 7d em sub corp em ambiente shadow se possível |
| `pg_dump` paralelo trava em locks longos do Neon | Baixa | Médio | Rodar em janela de baixa atividade; aceitar `pg_dump` single-thread (`-Fc` sem `-j`) como fallback |
| `azcopy` falha em paths com caracteres especiais | Baixa | Baixo | Usar `--s2s-handle-invalid-metadata=RenameIfInvalid`; AzCopy gera log com os pulados |
| Cron Job do ACA não dispara igual ao Cloud Scheduler (timezone, expressão) | Média | Médio | ACA cron usa UTC; Cloud Scheduler hoje provavelmente também — confirmar. Testar com expressão `*/2 * * * *` em staging por 1h antes do go-live. |
| Read-back v1.3.85 quebra em Azure Blob por diferença de propagação | Baixa | Alto | Implementar tests unitários equivalentes aos do GCS antes de promover; manter `AudioUploadVerificationError` igual |
| Conexão Postgres Flexible com `sslmode=require` rejeitada por algum driver | Baixa | Baixo | psycopg2 já força SSL desde sempre (`connection.py:102-104`); só validar com `psql -h ... 'sslmode=require'` no smoke |
| GitHub OIDC federado não autentica no tenant corp | Média | Médio | Configurar e testar **antes** do dia da migração, com um workflow `hello-world.yml` |

---

## 8. Checklist final pré-cutover

- [ ] Todos os recursos Azure provisionados e em **Running**
- [ ] Smoke test em staging ACA: login, upload manual, sync D-1, audit completo, supervisor approve
- [ ] Row counts do Neon batem com Flexible Server (±0 tolerância em todas as tabelas críticas)
- [ ] Contagem de blobs Azure == contagem de objetos GCS
- [ ] 1 áudio aleatório baixado do Blob via app abre corretamente (verifica path translation)
- [ ] App Insights mostrando logs estruturados do FastAPI
- [ ] Sentry (se mantido) recebendo eventos com `SENTRY_ENVIRONMENT=production`
- [ ] Federated Credential do GitHub testado com workflow dummy
- [ ] Container Apps Job rodou ao menos 1 vez sozinho e retornou 200 do `/api/automation/cron/run`
- [ ] Key Vault: todos os secrets referenciados pelo ACA estão presentes
- [ ] Plano de rollback escrito e impresso (sem depender do laptop online)

---

## 9. Próximos passos imediatos

1. **Solicitar à TI corp** os recursos do §2.1 (criar ticket com este documento anexo)
2. Em paralelo, **abrir branch `feat/azure-migration`** e:
   - Aplicar §4.1 (deps), §4.3 (media_storage), §4.4 (audit_storage), §4.6 (env)
   - Adicionar testes unitários espelhando os do GCS para o backend Azure
   - Adicionar `deploy-aca.yml` ao lado do `deploy-cloudrun.yml` (não remover ainda)
3. **Antes do cutover:** validar `pg_dump` em ambiente local apontando para o Neon (read-only) para conferir tamanho real do dump e ajustar janela
4. **Confirmar com TI corp:** região Brazil South vs East US 2 para Azure OpenAI; capacity de Whisper

---

> **Notas para outros agentes (Gemini, Codex):** este plano foi escrito assumindo a versão 1.3.99. Se mudanças subsequentes alterarem o schema de `media_files`, `audit_media_files` ou o pipeline em `core/audit.py:process_audit_with_ai`, revisar §4.3-§4.5. Não rodar `pg_dump` em produção sem coordenar via canal Lucas (lock no Neon pode afetar leituras concorrentes).
