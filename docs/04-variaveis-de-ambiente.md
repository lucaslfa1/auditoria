# Variáveis de ambiente

> A referência canônica e SEMPRE atualizada é **`backend/.env.example`**
> (179 variáveis, comentadas uma a uma em PT-BR, agrupadas em 17 seções).
> Este documento só explica as convenções e destaca o subconjunto crítico.

## Convenções (do .env.example)

- **`[CUSTO]`** — variável que gera ou controla custo de API paga (31 no total;
  visão de conjunto em `docs/07-custos-e-guardrails.md`).
- **`(env>DB)`** — também configurável na tabela `configuracoes` do banco;
  a env tem precedência quando definida e não-vazia.
- O valor mostrado no template é o **default do código** (vazio = obrigatória
  ou sem default).
- Ordem de carga do dotenv (`override=False`): ambiente do SO → `<raiz>/.env`
  → `backend/.env`.

## Mínimo para subir em produção

| Variável | Observação |
| --- | --- |
| `ENVIRONMENT=production` | Liga validação estrita, HSTS, rate limits, cookie secure |
| `DATABASE_URL` | PostgreSQL com `sslmode=require`; sem fallback em produção |
| `SESSION_SECRET` | Sem ela em produção o app NÃO inicia (por design) |
| `SESSION_COOKIE_SECURE=true` | Explícito em produção |
| `ALLOWED_ORIGINS` | Origens exatas do frontend; `*` é recusado no startup |
| `AZURE_OPENAI_*`, `AZURE_SPEECH_*` | Endpoints + keys (rotacionadas!) dos recursos de IA |
| `CRON_SECRET_TOKEN` | Bearer dos endpoints de cron (fail-closed sem ele) |
| `HUAWEI_*` | Credenciais AICC (AK/SK + app key/secret OAuth) |
| `HUAWEI_SYNC_ENABLE_CLASSIFY=true` | Sync manual Huawei roda a Fase 2 e nao deixa itens automaticos pendurados na triagem |
| `MEDIA_STORAGE_BACKEND` | `local` / `gcs` / `azure_blob` |

## Frontend

Única variável: `VITE_API_URL` (ver `.env.example` da raiz). Em produção o
FastAPI serve o build estático do Vite — não precisa dela no container.

## Segredos

Nunca em arquivo no servidor: usar o vault da empresa com injeção por
referência (tabela env→secret pronta em `docs/08-seguranca.md` §3).
