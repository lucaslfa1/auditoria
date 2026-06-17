# Custos de API e guardrails de orçamento

> O que custa dinheiro neste sistema, o que já estourou uma vez, e quais
> proteções estruturais impedem que estoure de novo. Leitura obrigatória para
> quem operar o sistema.

## 1. Onde o dinheiro é gasto

| Serviço | Uso | Quando |
| --- | --- | --- |
| **Azure OpenAI GPT-4o** | Classificação da ligação, triagem LLM de candidatas, avaliação da auditoria (+1 retry opcional), judge de empate do selector, resumo, speaker mapping, reparo de JSON | Por item processado |
| **Azure Speech (Fast Transcription)** | Transcrição padrão (engine `fast`) | 1 chamada por áudio |
| **Azure OpenAI (eastus2)** | Whisper e GPT-4o diarize — só como FALLBACK opt-in ou escalada do selector quando o fast não presta | Minoria dos áudios |
| **Banco PostgreSQL** | Compute por tempo ativo (no Neon atual); polling do frontend mantém o compute acordado | Contínuo |

O custo de UMA auditoria automática típica: 1 transcrição fast + 1
classificação GPT-4o + 1 avaliação GPT-4o (+1 retry se evidência fraca).

## 2. O incidente de junho/2026 (por que isso tudo existe)

Relatório interno de 10/06/2026 (análise do banco `auditoria-nstech-2`):
- Ciclo de automação a cada **30 minutos** (969 ciclos acumulados);
- Engine de transcrição **hybrid_dual** forçada — GPT-4o Diarize + Whisper +
  fusão GPT-4o por auditoria (o motor mais caro disponível);
- `huawei_d1_max_retries=15` — cada falha reprocessava (e pagava) até 15x;
- GPT-4o classificando candidatas que os filtros nativos descartariam depois.

Estimativa: 10-12 mil chamadas GPT-4o só de classificação, fora auditorias e
reprocessos — compatível com o estouro do orçamento.

## 3. Correções de comportamento (v1.3.109–112 + handover)

| Mudança | Versão |
| --- | --- |
| Engine default `fast`, SEM fallback premium automático | v1.3.109 |
| Falha de auditoria → descarte permanente, sem retry (`AUTOMATION_TRANSIENT_RETRY_LIMIT=1`) | v1.3.111 |
| Cron reduzido para 1x/dia | infra (Cloud Scheduler hoje; Container Apps Job/Logic App no Azure) |
| Cache do health-snapshot + polling adaptativo (pausa com aba oculta) | v1.3.110 / v1.3.117 |
| **hybrid_dual DESCONTINUADO** — só roda com `AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL` (não usar) | decisão 2026-06-11 |
| Direção de chamada via consulta VDN (gratuita) em vez de Whisper+GPT por áudio | v1.3.115 |
| Gates nativos ANTES da classificação GPT na Fase 2 do sync | v1.3.116 |
| Retry de avaliação por evidência fraca configurável (`AUDIT_WEAK_EVIDENCE_RETRY`) | v1.3.117 |

## 4. Guardrails estruturais (v1.3.114 — `backend/core/cost_guard.py`)

Garantia de teto INDEPENDENTE de configuração de cadência ou engine:

1. **Teto diário de chamadas LLM** — `COST_MAX_LLM_CALLS_PER_DAY`
   (default **1500**). Toda chamada paga ao Azure OpenAI conta (tentativas
   inclusive). Atingido: pipeline para de pegar itens novos; nada é
   descartado; a fila espera o dia seguinte.
2. **Teto diário de auditorias** — `COST_MAX_AUDITS_PER_DAY` (default **200**).
3. **Kill-switch** — env `COST_KILL_SWITCH` OU chave `cost_kill_switch` na
   tabela `configuracoes`: corta o consumo pago na hora, **sem redeploy**
   (`UPDATE configuracoes SET valor='true' WHERE chave='cost_kill_switch'`).

Valor `<= 0` desativa o teto correspondente. Fallback dos limites também via
tabela `configuracoes` (`cost_max_llm_calls_per_day`, `cost_max_audits_per_day`).

### Telemetria
Tabela `api_usage_daily` (data, provider, categoria → chamadas), alimentada
em todos os 11 call sites pagos. Consumo do dia + tetos + motivo de bloqueio:
`GET /api/telefonia/sync/diagnostics` → bloco `custo_diario`.

### Filosofia
- **Fail-open**: banco indisponível não trava o pipeline (é proteção de
  custo, não controle de acesso).
- Gates verificam no INÍCIO de cada unidade de trabalho — nunca no meio de
  uma auditoria (sem artefato pela metade).
- Bloqueio NUNCA descarta item: tudo fica pendente aguardando o reset diário.

## 5. Alavancas de custo (referência rápida)

Todas documentadas com a marca `[CUSTO]` em `backend/.env.example`. As
principais:

| Env | Default | Efeito |
| --- | --- | --- |
| `AZURE_TRANSCRIPTION_ENGINE` | `fast` | Engine padrão (não mudar) |
| `AZURE_WHISPER_FALLBACK` / `AZURE_GPT4O_DIARIZE_FALLBACK` | off | Fallbacks premium |
| `TRANSCRIPTION_CANDIDATE_SELECTOR_ENABLED` | on | Selector + judge em empate |
| `AUDIT_WEAK_EVIDENCE_RETRY` | 1 | 2ª chamada de avaliação se evidência fraca |
| `COST_MAX_LLM_CALLS_PER_DAY` / `COST_MAX_AUDITS_PER_DAY` | 1500 / 200 | Tetos diários |
| `COST_KILL_SWITCH` (+ config no banco) | off | Corta consumo pago |

## 6. Recomendações ao time de engenharia

1. Configurar **alerta de orçamento** no Azure Cost Management das
   assinaturas de IA (o guardrail interno limita, o alerta avisa).
2. Olhar `custo_diario` no diagnostics ao investigar qualquer suspeita.
3. Nunca reativar `hybrid_dual` nem aumentar retries sem revisar a Seção 2.
