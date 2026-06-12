# Checklist de handover — time de engenharia

> Lista executável, em ordem. Cada item aponta o documento com o detalhe.
> Pré-requisito de leitura: `docs/01-visao-geral.md` e o índice
> `docs/README.md`. Responsáveis: [LUCAS] = Lucas (lado atual);
> [ENG] = time de engenharia da empresa.

## Fase A — Segurança (antes de qualquer deploy)

- [ ] [LUCAS] Rotacionar TODAS as chaves comprometidas no histórico git
      (`docs/08-seguranca.md` §2.2): Azure OpenAI, Speech, eastus2
      (diarize+whisper), Text Analytics, senha do Neon, `SESSION_SECRET`,
      `CRON_SECRET_TOKEN`, Huawei AK/SK e App Key/Secret.
- [ ] [ENG] Provisionar vault de segredos (ex.: Azure Key Vault) e cadastrar
      os segredos JÁ rotacionados (tabela env→secret em `docs/08-seguranca.md` §3).
- [ ] [ENG] Garantir que `.env` reais nunca entrem no repositório da empresa
      (manter `.gitignore`/`.dockerignore`; versionar apenas `*.env.example`).

## Fase B — Banco de dados (`docs/10-migracao-banco.md`)

- [ ] [ENG] Escolher e provisionar PostgreSQL >= 17 com pgvector (requisitos §1).
- [ ] [ENG] Habilitar a extensão `vector` ANTES do restore (§3.2).
- [ ] [ENG] Executar `scripts/migration/01_dump_neon` → `02_restore_destino`
      → `03_validate.py` na janela descrita (§4) — só prosseguir com
      `MIGRACAO VALIDADA`. (Alternativa: banco vazio, seeds completos no boot.)
- [ ] [ENG] Manter o Neon intocado até dias de operação validada (rollback §5).

## Fase C — Aplicação (`docs/11-deploy.md`)

- [ ] [ENG] Build da imagem (Dockerfile da raiz, sem mudanças) em registry próprio.
- [ ] [ENG] Deploy do container: porta 8080, probe `/api/health`,
      timeout >= 600s, envs completas (`backend/.env.example` como guia).
- [ ] [ENG] Obrigatórias em produção: `ENVIRONMENT=production`,
      `SESSION_COOKIE_SECURE=true`, `ALLOWED_ORIGINS` explícito (nunca `*`),
      `DATABASE_URL` novo, segredos via vault.
- [ ] [ENG] Storage de mídia: decidir backend (`MEDIA_STORAGE_BACKEND`);
      p/ Azure Blob, descomentar `azure-storage-blob` no requirements e setar
      `AZURE_STORAGE_CONNECTION_STRING`/`AZURE_STORAGE_CONTAINER`.
- [ ] [ENG] Smoke: `/api/health` 200; login; Arquivos Salvos abre; 1 ciclo
      manual de automação completa.

## Fase D — Operação contínua

- [ ] [ENG] Agendar o cron: `POST /api/telefonia/cron/sync` 1x/dia com
      `Authorization: Bearer <CRON_SECRET_TOKEN>` novo.
- [ ] [ENG] Confirmar guardrails de custo ativos (`docs/07-custos-e-guardrails.md`;
      defaults: 1500 chamadas LLM/dia, 200 auditorias/dia) e
      treinar a operação no kill-switch (`cost_kill_switch` na tabela
      `configuracoes` — corta consumo pago sem redeploy).
- [ ] [ENG] Monitorar o consumo do dia em `GET /api/telefonia/sync/diagnostics`
      (bloco `custo_diario`).
- [ ] [ENG] Configurar alerta de orçamento no portal Azure (Cost Management)
      para as assinaturas dos recursos de IA.
- [ ] [ENG] Sentry: criar projeto próprio (ou desativar `SENTRY_ENABLED`).
- [ ] [ENG] CI/CD próprio: adaptar `.github/workflows/deploy-azure.yml.example`
      e DESATIVAR `deploy-cloudrun.yml` (hoje, push na main = deploy GCP).

## Fase E — Descomissionamento do ambiente atual

- [ ] [LUCAS] Desativar cron do Cloud Scheduler e o serviço Cloud Run.
- [ ] [LUCAS] Desprovisionar Neon após validação (manter dump final arquivado).
- [ ] [LUCAS] Revogar as chaves antigas que ainda estiverem ativas.

## Referências rápidas

| Tema | Documento |
| --- | --- |
| Segurança / segredos / Key Vault | `docs/08-seguranca.md` |
| Migração do banco | `docs/10-migracao-banco.md` |
| Deploy / plataforma | `docs/11-deploy.md` |
| Variáveis de ambiente | `backend/.env.example` |
| Testes (banco de teste, guard de prod) | `tests/backend/conftest.py` + logs/versions/1.3.124 |
| Histórico de mudanças | `logs/versions/` |
