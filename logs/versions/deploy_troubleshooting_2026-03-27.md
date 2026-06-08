# Deploy Troubleshooting Log — 2026-03-27

## Problema 1: ContainerImageImportFailed (Artifact Registry)

**Sintoma**: Todas as revisões (16+) falhavam com `ContainerImageImportFailed` ao usar
`gcloud run deploy --source .` que builda via Artifact Registry
(`southamerica-east1-docker.pkg.dev/auditoria-nstech/cloud-run-source-deploy/auditoria`).

**Investigação**:
- IAM: Concedido `roles/artifactregistry.reader` ao Compute Engine SA e ao Cloud Run Service Agent — não resolveu
- Execution environment: Tentado gen1 e gen2 — ambos falhavam
- Serviço deletado e recriado — mesmo erro
- Teste com `gcr.io/cloudrun/hello` — funcionou (projeto GCP OK)
- Conclusão: problema específico do path Artifact Registry em `southamerica-east1`

**Solução**: Usar GCR (`gcr.io`) ao invés de Artifact Registry:
```bash
gcloud builds submit --tag gcr.io/auditoria-nstech/auditoria --region southamerica-east1
gcloud run deploy auditoria --image gcr.io/auditoria-nstech/auditoria --region southamerica-east1 --allow-unauthenticated --port 8080 --memory 1Gi
```

---

## Problema 2: Container crash no startup (_seed_users)

**Sintoma**: Após resolver o import, container crashava com:
```
RuntimeError: Em produção, seed de usuários exige AUTH_USERS_JSON ou AUTH_USERS_FILE.
```

**Causa**: O serviço foi deletado/recriado e perdeu todas as env vars configuradas.

**Solução**: Configurar via `--env-vars-file env.yaml`:
```yaml
AUTH_USERS_JSON: '[{"username":"...","password":"...","role":"..."}]'
ENVIRONMENT: production
```

---

## Problema 3: Python 3.14 local incompatível

**Sintoma**: `pip install` falha para `pydantic-core`, `numpy`, `pandas` — wheels binários
não disponíveis para Python 3.14. Compilação do source exige Rust (pydantic-core).

**Solução**: Criar venv com Python 3.12:
```bash
py -3.12 -m venv .venv
.venv\Scripts\pip install --no-cache-dir --only-binary :all: -r requirements.txt
```

**Nota**: No outro PC do Lucas funciona com 3.14 porque tem Rust instalado via `rustup`.

---

## Comandos de deploy (referência rápida)

```bash
# Build
gcloud builds submit --tag gcr.io/auditoria-nstech/auditoria --region southamerica-east1

# Deploy
gcloud run deploy auditoria \
  --image gcr.io/auditoria-nstech/auditoria \
  --region southamerica-east1 \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi

# Verificar
gcloud run services describe auditoria --region southamerica-east1 --format="value(status.url)"
```
