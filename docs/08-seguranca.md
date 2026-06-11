# Segurança — Sistema de Auditoria NSTECH

> Documento de handover para o time de engenharia. Descreve o estado de segurança real do código (verificado no repositório em 2026-06-11), o incidente conhecido de segredos no histórico git e as ações obrigatórias antes do deploy em Azure.

## 1. Resumo executivo

O backend (FastAPI) já implementa os controles essenciais: autenticação por cookie de sessão assinado com HMAC-SHA256, senhas com bcrypt em tabela `users` (Neon PostgreSQL), roles `admin`/`supervisor`, CORS restritivo, security headers, rate limiting global e de login, e endpoints de cron protegidos por Bearer token. Existe um **incidente conhecido**: arquivos `.env` com chaves reais foram commitados no histórico do git (commits `81818b66`, `b8b7e1da`, `df3878f8`); como o repositório migrou para o GitHub (`lucaslfa1/auditoria`), **todas as chaves do inventário devem ser tratadas como comprometidas e rotacionadas** antes/na migração. A decisão tomada é **rotacionar, não reescrever o histórico**. Adicionalmente, o sistema possui guardrails de custo (kill-switch + tetos diários, v1.3.114) como controle de segurança financeira contra abuso ou regressão de pipeline.

## 2. Segredos e credenciais

### 2.1 Inventário de segredos

Todos definidos via variáveis de ambiente (template: `backend/.env.example`). Nenhum segredo é hardcoded no código.

| Variável | O que é | Sensibilidade |
| --- | --- | --- |
| `AZURE_OPENAI_KEY` | Azure OpenAI GPT-4o (avaliação/auditoria) — `azure-openai-opentech` | Alta (custo por uso) |
| `AZURE_SPEECH_KEY` | Azure Speech-to-Text / Fast Transcription (eastus) | Alta (custo por uso) |
| `AZURE_GPT4O_DIARIZE_KEY` | Diarização premium — recurso `adml-mobl85rw-eastus2` | Alta (custo por uso) |
| `AZURE_WHISPER_KEY` | Whisper (fallback de triagem) — **mesmo recurso eastus2 da diarização**; rotação de um rotaciona o outro | Alta (custo por uso) |
| `AZURE_TEXT_ANALYTICS_KEY` | Azure Language Service | Alta |
| `DATABASE_URL` | Connection string Neon PostgreSQL (contém usuário+senha) | Crítica (todos os dados) |
| `SESSION_SECRET` | Chave HMAC dos tokens de sessão; quem a possui forja sessões válidas de qualquer usuário | Crítica |
| `CRON_SECRET_TOKEN` | Bearer token dos endpoints de cron (Cloud Scheduler hoje) | Alta |
| `HUAWEI_AK` / `HUAWEI_SK` | Access/Secret Key Huawei AICC (gravações de telefonia) | Alta |
| `HUAWEI_DIRECT_APP_KEY` / `HUAWEI_DIRECT_APP_SECRET` | OAuth direto Huawei AICC | Alta |
| `SENTRY_DSN` | Ingestão de eventos no Sentry | Baixa (permite poluir o projeto Sentry) |
| `GEMINI_API_KEY` | Google Gemini (legado/opcional — provedor primário é Azure) | Média |

### 2.2 ⚠️ Incidente conhecido: segredos no histórico do git

Arquivos `.env` e `backend/.env` **com chaves reais** entraram no histórico do repositório nos commits (verificados via `git log --all --diff-filter=A -- .env backend/.env`):

- `81818b66` — "Initial backup commit"
- `b8b7e1da` — "Update project state"
- `df3878f8` — "feat: adicionar módulo de configurações globais e documentação de automação"

Hoje os arquivos não são mais rastreados (`git ls-files` retorna apenas `.env.example` e `backend/.env.example`), mas **continuam recuperáveis no histórico** de qualquer clone. Como o repositório foi migrado para o GitHub (`lucaslfa1/auditoria`), as chaves expostas devem ser consideradas **comprometidas**.

**Ação obrigatória — rotação de TODAS as chaves do inventário (responsável: Lucas/Gemini, no portal Azure e no console Neon), antes/na migração para o ambiente da empresa:**

1. Regenerar as keys dos 4 recursos Azure (OpenAI, Speech, eastus2 diarize/whisper, Text Analytics).
2. Resetar a senha do role no Neon (gera novo `DATABASE_URL`).
3. Gerar novos `SESSION_SECRET` e `CRON_SECRET_TOKEN` (ex.: `openssl rand -hex 32`).
4. Rotacionar AK/SK e App Key/Secret no console Huawei AICC.
5. Recriar o DSN no Sentry (ou aceitar o risco, dado o baixo impacto).

**Decisão já tomada: NÃO reescrever o histórico git.** A rotação das chaves elimina o risco real (as chaves antigas viram lixo); reescrita de histórico (`filter-repo`/BFG) quebraria todos os clones e o trabalho dos agentes em andamento, sem benefício adicional após a rotação.

### 2.3 Higiene atual do repositório

- `.gitignore` exclui `.env`, `.env.backup`, `.env.local`, `backend/.env`, `backend/.env.backup`, `backend/gcp-key.json`, `auth_users.json` e demais artefatos sensíveis.
- `.dockerignore` exclui `.env`, `.env.*`, `backend/.env`, `backend/.env.*`, `backend/gcp-key.json` — segredos não entram na imagem de container.
- Apenas `*.env.example` (sem valores) é versionado.

## 3. Mapeamento env → Azure Key Vault

Padrão recomendado para Azure Container Apps: cada segredo vira um secret no Key Vault; o Container App referencia o Key Vault via managed identity e expõe o valor como variável de ambiente via `secretRef`. Nomes de secret usam apenas minúsculas e hífens (restrição do Key Vault/Container Apps).

| Variável de ambiente | Secret no Key Vault | Injeção no Container App |
| --- | --- | --- |
| `AZURE_OPENAI_KEY` | `azure-openai-key` | `env: AZURE_OPENAI_KEY` → `secretRef: azure-openai-key` |
| `AZURE_SPEECH_KEY` | `azure-speech-key` | `secretRef: azure-speech-key` |
| `AZURE_GPT4O_DIARIZE_KEY` | `azure-gpt4o-diarize-key` | `secretRef: azure-gpt4o-diarize-key` |
| `AZURE_WHISPER_KEY` | `azure-whisper-key` | `secretRef: azure-whisper-key` |
| `AZURE_TEXT_ANALYTICS_KEY` | `azure-text-analytics-key` | `secretRef: azure-text-analytics-key` |
| `DATABASE_URL` | `neon-database-url` | `secretRef: neon-database-url` |
| `SESSION_SECRET` | `session-secret` | `secretRef: session-secret` |
| `CRON_SECRET_TOKEN` | `cron-secret-token` | `secretRef: cron-secret-token` |
| `HUAWEI_AK` | `huawei-ak` | `secretRef: huawei-ak` |
| `HUAWEI_SK` | `huawei-sk` | `secretRef: huawei-sk` |
| `HUAWEI_DIRECT_APP_KEY` | `huawei-direct-app-key` | `secretRef: huawei-direct-app-key` |
| `HUAWEI_DIRECT_APP_SECRET` | `huawei-direct-app-secret` | `secretRef: huawei-direct-app-secret` |
| `SENTRY_DSN` | `sentry-dsn` | `secretRef: sentry-dsn` |
| `GEMINI_API_KEY` (se mantido) | `gemini-api-key` | `secretRef: gemini-api-key` |

Exemplo (CLI):

```bash
# 1. Secret no Container App referenciando o Key Vault (managed identity)
az containerapp secret set --name auditoria --resource-group <rg> \
  --secrets "session-secret=keyvaultref:https://<vault>.vault.azure.net/secrets/session-secret,identityref:system"

# 2. Variável de ambiente apontando para o secret
az containerapp update --name auditoria --resource-group <rg> \
  --set-env-vars "SESSION_SECRET=secretref:session-secret"
```

Variáveis **não-secretas** mas obrigatórias em produção (podem ir como env vars normais): `ENVIRONMENT=production`, `SESSION_COOKIE_SECURE=true`, `ALLOWED_ORIGINS=<origens explícitas>`, endpoints Azure (`AZURE_*_ENDPOINT`), flags de engine/automação.

## 4. Autenticação e sessão

Implementação em `backend/routers/auth.py`; usuários em tabela `users` no Neon (`backend/repositories/auth_users.py`).

- **Senhas**: hash bcrypt (`bcrypt.checkpw`); nunca armazenadas em claro. Mensagem de erro única ("Credenciais inválidas") para usuário inexistente e senha errada — não há enumeração de usuários.
- **Sessão**: cookie `nstech_session` contendo payload base64url (`sub`, `exp`, `nonce`) assinado com **HMAC-SHA256** usando `SESSION_SECRET`. Validação com `hmac.compare_digest` (resistente a timing attack). TTL padrão 8h (`SESSION_TTL_SECONDS=28800`).
- **`SESSION_SECRET`**: obrigatório em produção — se `ENVIRONMENT=production` e a variável estiver ausente, a aplicação **falha no startup** (`RuntimeError`), por design. Fora de produção usa um segredo efêmero aleatório por processo.
- **Atributos do cookie**: `HttpOnly=true`, `SameSite=Lax`, `Path=/`. `Secure` vem de `SESSION_COOKIE_SECURE` (default `true` quando `ENVIRONMENT=production`) — **definir explicitamente `SESSION_COOKIE_SECURE=true` em produção**.
- **Roles**: `admin` (acesso total) e `supervisor` (portal restrito). Guards reutilizáveis: `require_authenticated_user`, `require_admin`, `require_supervisor_or_admin` (dependências FastAPI nos routers).
- **Rate limit de login**: dedicado, por chave `IP + username` (IP real via `X-Forwarded-For`). Default: 5 tentativas falhas / 300 s → HTTP 429 com `Retry-After`. Ativo automaticamente em produção; override por `ENABLE_LOGIN_RATE_LIMIT`. Sucesso zera o contador.

## 5. Superfície de rede

Implementação em `backend/main.py`.

### 5.1 CORS

`_resolve_allowed_origins()` lê `ALLOWED_ORIGINS` (CSV). Em produção (`_is_production_environment()`, baseado em `ENVIRONMENT=production`), o valor `*` é **rejeitado com `RuntimeError` no startup** — origens devem ser explícitas. `allow_credentials=True` (cookies), métodos restritos a `GET/POST/PUT/DELETE/OPTIONS`, headers explícitos.

### 5.2 Security headers (middleware global)

Aplicados a todas as respostas:

| Header | Valor |
| --- | --- |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | `microphone=(), camera=(), geolocation=()` |
| `X-Permitted-Cross-Domain-Policies` | `none` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` — **somente em produção** |

### 5.3 Rate limit global

Middleware sobre rotas `/api/*`. Ativo automaticamente em produção; override por `ENABLE_GLOBAL_RATE_LIMIT`. Default: 200 req / 60 s por chave (`GLOBAL_RATE_LIMIT_MAX_REQUESTS` / `GLOBAL_RATE_LIMIT_WINDOW_SECONDS`). A chave é o hash do cookie de sessão (usuários atrás do mesmo proxy não se penalizam) ou, sem sessão, o IP de `X-Forwarded-For`. Excedido → HTTP 429 + `Retry-After`. Isentos: `/docs`, `/openapi.json`, `/redoc`, `/api/health`, `/api/ui/theme` e `/api/auth/{me,login,logout}` (login tem limiter próprio, ver §4).

### 5.4 Endpoints públicos vs autenticados

- **Públicos (sem sessão)**: `POST /api/auth/login`, `GET /api/auth/me` (retorna `authenticated: false`), `POST /api/auth/logout`, `GET /api/health`, `GET /api/ui/theme`.
- **Autenticados**: todo o restante da API exige cookie de sessão válido via guards (`Depends(require_admin)` etc.).
- **Webhooks de cron (scheduler → backend)**: `POST /api/telefonia/cron/sync`, `POST /api/internal/cron/knowledge-agent` e rotas de automação — exigem header `Authorization: Bearer <CRON_SECRET_TOKEN>`. Comportamento **fail-closed**: token não configurado → 503/403; token errado → 403. Na migração, apontar o scheduler da empresa (ex.: Azure Logic Apps / Container Apps Jobs) com o novo token.

## 6. Segurança financeira (guardrails de custo — v1.3.114)

Módulo `backend/core/cost_guard.py` (commit `037ea6e4`). Controle estrutural contra abuso, loop de retry ou regressão de configuração que dispare consumo descontrolado das APIs pagas (Azure OpenAI / Speech) — motivado por estouro real de orçamento em jun/2026.

1. **Teto diário de chamadas LLM** — `COST_MAX_LLM_CALLS_PER_DAY` (default 1500). Conta toda chamada paga ao Azure OpenAI. Atingido o teto, o pipeline para de processar itens novos (nada é descartado; itens aguardam o dia seguinte).
2. **Teto diário de auditorias completas** — `COST_MAX_AUDITS_PER_DAY` (default 200). Limita o pior caso mesmo se contadores por chamada falharem.
3. **Kill-switch** — env `COST_KILL_SWITCH` **ou** chave `cost_kill_switch` na tabela `configuracoes`: corta o consumo pago imediatamente **sem redeploy** (um `UPDATE` no banco basta). Útil como resposta a incidente (chave vazada sendo abusada, loop de custo).

Telemetria na tabela `api_usage_daily` (UPSERT por provider/categoria/dia). Filosofia **fail-open**: indisponibilidade do banco não derruba a operação — é proteção de custo, não controle de acesso.

## 7. Checklist de segurança do handover

Executar **antes** de colocar o ambiente da empresa em produção:

- [ ] Rotacionar as keys Azure: OpenAI (`azure-openai-opentech`), Speech (eastus), recurso eastus2 (diarize + whisper — mesma key) e Text Analytics (§2.2).
- [ ] Resetar a senha do banco Neon e atualizar `DATABASE_URL`.
- [ ] Gerar novo `SESSION_SECRET` (`openssl rand -hex 32`) — invalida todas as sessões antigas, comportamento desejado.
- [ ] Gerar novo `CRON_SECRET_TOKEN` e atualizar o scheduler que chama os endpoints de cron.
- [ ] Rotacionar credenciais Huawei (AK/SK e App Key/Secret).
- [ ] Provisionar Azure Key Vault e cadastrar todos os secrets da tabela do §3; injetar via `secretRef` (managed identity, sem keys de acesso ao vault).
- [ ] Definir `ENVIRONMENT=production` (habilita HSTS, rate limits, validações de startup).
- [ ] Definir `SESSION_COOKIE_SECURE=true` explicitamente.
- [ ] Definir `ALLOWED_ORIGINS` com as origens exatas do frontend (nunca `*` — o app recusa iniciar).
- [ ] Revisar a tabela `users` no banco: remover/desativar contas de teste e redefinir senhas de contas que permanecerem.
- [ ] Confirmar que nenhum `.env` real entra no repositório da empresa (manter `.gitignore`/`.dockerignore` atuais; versionar apenas `.env.example`).
- [ ] Confirmar guardrails de custo ativos (tetos default) e documentar para a operação como acionar o kill-switch (§6).
