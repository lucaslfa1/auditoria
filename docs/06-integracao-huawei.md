# Integração Huawei AICC

> Como o sistema coleta gravações da telefonia Huawei AICC (SaaS Brasil,
> operado via Teledata/OPENTECH). Código em `backend/core/huawei_*.py` e
> `backend/core/huawei/`. Rede/whitelist/IPs:
> `docs/infra/HUAWEI_NETWORK_MANIFEST.md`. Operação e troubleshooting:
> `docs/05-operacao-runbook.md`.

## 1. Autenticação (`huawei_client.py`)

Três modos, selecionados por `HUAWEI_AUTH_MODE` (env ou chave
`huawei_auth_mode` em `configuracoes`):

| Modo | Como funciona | Quando usar |
| --- | --- | --- |
| `proxy` (**padrão e em uso em produção**) | A assinatura SDK-HMAC-SHA256 é delegada ao endpoint `c2Authorization.php` da Teledata, que devolve o header `Authorization` pronto; a chamada final ainda sai deste host (IP precisa estar na whitelist) | Ambiente sem AK/SK direto da Huawei |
| `oauth_direct` (alias `token`) | `POST {auth_base}/apigovernance/api/oauth/tokenByAkSk` com `HUAWEI_DIRECT_APP_KEY`/`HUAWEI_DIRECT_APP_SECRET` → `Authorization: Bearer <token>` (cache até expirar, default 55 min) | Com app key/secret direto e IP liberado no WAF |
| `direct` | Assinatura HMAC-SHA256 local (stdlib) com AK/SK, conforme doc oficial CEC | Com AK/SK direto e IP liberado |

O OBS usa assinatura própria (HMAC-SHA1 + Base64, padrão OBS v2) com
`huawei_obs_ak`/`huawei_obs_sk`.

Credenciais vivem na tabela `configuracoes` (chaves `huawei_*`) com fallback
para env — inventário de segredos em `docs/08-seguranca.md` §2.1.

## 2. Endpoints usados

Host AICC: `https://brazilsaas.aicccloud.com:28443`. Bucket OBS:
`https://<bucket>.obs.sa-brazil-1.myhuaweicloud.com` (default
`obs-nstech-opentech`).

| Endpoint | Uso no sistema |
| --- | --- |
| CMS `POST /rest/cmsapp/v2/openapi/vdn/querycalls` | Descoberta de chamadas por VDN e janela de tempo (sem filtro por operador/mídia — filtros são feitos aqui) |
| CMS `GET /rest/cmsapp/v1/openapi/calldata/querydetailcallinfo` e `querybasiccallinfo` | `consultar_direcao_chamada(call_id)` — direção real da chamada (ativa×receptiva), gate de custo zero (v1.3.115) |
| OBS `Contact_Record/contact-record/10-minutes/{YYYYMMDD}/*.csv` | **Manifesto** de chamadas do dia — complementa a descoberta da VDN |
| OBS `Voice/{YYYYMMDD}/{callerNo\|calleeNo\|agentId}/...-{callId}.V3` | Gravação direta (`.V3` é WAV G.711 A-law com header RIFF — não precisa converter) |
| CCFS `POST /CCFS/resource/ccfs/downloadRecord` | Download binário por callId |
| CCFS `POST /CCFS/resource/ccfs/downloadRecordFile` | Download binário por fileName |
| CCFS `POST /CCFS/resource/ccfs/getRecordFileUrlFromObs` | URL OBS pré-assinada (assíncrono) |

403/429/502 do WAF viram `WafRateLimitError` com retry exponencial (tenacity).

## 3. Pipeline D-1 (`huawei_d_minus_1.py`)

Coleta as ligações do dia anterior, disparada pelo cron diário
(`POST /api/telefonia/cron/sync`). Configuração no banco (`configuracoes`),
defaults:

| Chave | Default | Significado |
| --- | --- | --- |
| `huawei_d1_enabled` | `true` | Liga o pipeline |
| `huawei_d1_horario_execucao` | `06:00` | Horário-alvo (America/Sao_Paulo) |
| `huawei_d1_max_retries` | `8` | Tentativas quando o OBS ainda não tem o dia (Huawei pode demorar horas para subir D-1) |
| `huawei_d1_retry_intervalo_minutos` | `60` | Intervalo entre tentativas |
| `huawei_d1_lookback_dias` | `3` | Dias para trás verificados (recupera lotes perdidos) |
| `huawei_d1_limite_ligacoes` | `20` | Teto de downloads por execução |
| `huawei_cota_max_por_operador_mes` | `2` | Cota mensal por operador |

Estado por data em `huawei_d_minus_1_runs` (status, tentativas, contadores,
último erro). Não confundir o retry de COLETA (este, barato — espera o OBS
ter os arquivos) com retry de AUDITORIA (limitado a 1 — `docs/07` §3).

## 4. Sync (`huawei_sync.py` — `executar_sync_huawei`)

Protegido por advisory lock do PostgreSQL (sync concorrente é recusado;
destrava via `POST /api/telefonia/sync/reset-lock` ou expira em 30 min).

**Fase 1 — descoberta e download:**

1. **Descoberta** (`huawei_discovery.py`): VDN `querycalls` em janelas de 60
   min (`HUAWEI_QUERYCALLS_WINDOW_MINUTES`) + manifesto CSV do OBS; merge e
   dedup por `callId`.
2. **Filtros nativos** (sem custo de IA — ver §5).
3. **Triagem LLM** (`llm_triage.py`): GPT-4o recebe metadados de até 10
   candidatas por setor e aprova no máximo 2 (descarta "lixo": chamadas
   curtas demais, URA, etc.).
4. **Download** (`huawei_download_chain.py`), cadeia com fallback:
   - modo `manual_interval`: **OBS direto → CC-FS downloadRecord → URL
     pré-assinada**;
   - modo `retroactive`: CC-FS → URL (nunca OBS).
5. Mídia salva no storage (`media_files`) e item enfileirado em
   `fila_revisao_classificacao` (status `pending`).

**Fase 2 — classificação:**

- `_classificar_pendentes_async`: classifica os pendentes em paralelo com
  GPT-4o + guardrails.
- **Gates nativos ANTES do GPT** (v1.3.116): `AutomationGatekeeper.
  check_eligibility` (a MESMA regra da automação) roda primeiro — item
  inelegível (setor fora da telefonia, receptiva em setor de risco) é
  descartado/marcado **sem carregar o áudio nem gastar GPT**.
- Resultado: `auto_resolved` (segue para automação) ou `needs_manual_triage`
  (revisão humana na Triagem).

## 5. Filtros de negócio (intencionais — não são bugs)

| Filtro | Regra | Onde |
| --- | --- | --- |
| **Operador auditável** | Só baixa ligação de operador cadastrado em `colaboradores` com `id_huawei` preenchido e flag `auditavel`; sem cadastro = ignorado (regra de negócio confirmada) | `_should_skip_call` / `operator_filters` |
| **Direção** | Setores de risco OUTBOUND-only (`uti`, `bas`, `distribuicao`, `fenix`, `transferencia`): receptiva descarta. Resolução: 1º consulta VDN por callId (evidência real, custo zero — v1.3.115); fallback metadados da interação; indeterminada descarta (na dúvida, não audita) | `huawei_direction.py` + `consultar_direcao_chamada` |
| **Duração** | Mínimo 120s por default (`HUAWEI_SYNC_MIN_DURATION_SECONDS`) | `huawei_sync.py` |
| **Cota 2/operador/mês** | Aplicada PRÉ-DOWNLOAD no sync (não desperdiça download/IA em operador já coberto; registra `skipped_quota`) e novamente no ENVIO ao supervisor (gate final — `docs/05` §4) | `huawei_sync.py` + `promote_audit_to_pending_approval` |

## 6. Tombstones e esteira binária

Todo `call_id` processado deixa rastro em **`huawei_sync_logs`**
(status + `failure_reason`):

- **Descarte permanente (tombstone)**: o call_id NÃO reaparece em syncs
  futuros (ex.: receptiva em setor de risco, setor não-telefonia, lixo da
  triagem LLM).
- **Falha técnica reversível**: apenas estados de coleta/pre-filtro que ainda
  não são decisão de descarte (`failed`, `skipped_quota`, `skipped_direction`)
  podem ser tentados novamente se a regra ou a configuração mudar.
- **Descarte operacional**: quando um item é removido/descartado pela
  automação, Triagem ou Telefonia, o tombstone é permanente. Não promover
  `discarded_*` de volta para `success`/`failed`/`skipped`.

Semântica central em `core/automation_disposition.py`. Resultado: nada fica
preso — todo item termina auditado ou descartado com motivo consultável.

## 7. Timezone (NÃO mexer)

- O **CSV manifesto do OBS envia `beginTime`/`endTime` como ISO em UTC** (sem
  fuso explícito); a API VDN envia epoch numérico já em UTC. O parse correto
  está em `HuaweiDiscoveryService._coerce_huawei_time_ms` (v1.3.93 — assumir
  BRT ali somava +3h e causava `audio_not_found`).
- O discriminador de qualquer suspeita de bug de horário é o campo
  `huawei_source` no metadata (`vdn` / `obs_contact_record` /
  `obs_contact_record+vdn`), **não** `is_manual`.
- `routers/telefonia.py` (`_parse_iso_to_ms`) interpreta input
  `datetime-local` do navegador em BRT — é intencional, não "corrigir".
- **Decisão registrada: não propor conversões/ajustes de timezone** nos dados
  gravados; scripts de fix ±3h foram removidos de propósito.

## 8. Referências

- Rede, whitelist de IPs e chaves no banco: `docs/infra/HUAWEI_NETWORK_MANIFEST.md`
- Capacidades da API: `backend/config/huawei_capabilities.md`
- Histórico: `logs/versions/1.3.93` (timezone CSV), `1.3.115` (direção via
  VDN), `1.3.116` (gates antes do GPT)
- Nota: houve um plano antigo de integração via scraping (Playwright) que
  nunca foi implementado — a integração real é 100% API REST
