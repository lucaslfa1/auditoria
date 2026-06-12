# Operação — runbook e troubleshooting

> Procedimentos do dia a dia e diagnóstico dos problemas mais comuns.
> Complementa: `docs/07-custos-e-guardrails.md` (custo) e
> `docs/GUIA_DE_SOBREVIVENCIA_AUTOMACAO.md` (manual de bolso legado, mesmo
> espírito, linguagem informal).

## 1. Ciclo normal de operação

1. **Cron diário** (scheduler externo) chama
   `POST /api/telefonia/cron/sync` com `Authorization: Bearer <CRON_SECRET_TOKEN>`.
2. O sync Huawei baixa o manifesto D-1, aplica filtros NATIVOS (operador
   auditável, direção via VDN, duração, cota), triagem LLM por setor,
   baixa os áudios aprovados e classifica (Fase 2) — com gates de
   elegibilidade ANTES de gastar GPT.
3. O motor de automação audita os itens prontos (`ready_for_audit`) em lotes
   limitados por tempo e quantidade; resultado vai para **Arquivos Salvos**
   com `criado_por='automacao'` (status `awaiting_pair`).
4. O auditor revisa em Arquivos Salvos (gate humano por design — automáticas
   e manuais se misturam de propósito) e promove para aprovação do
   supervisor; o fechamento consolida o período.

Esteira binária (v1.3.103+): no modo automação todo item termina **auditado**
ou **descartado** (tombstone com motivo em `huawei_sync_logs`); nada fica
preso em estados intermediários.

## 2. Endpoints de diagnóstico

| Endpoint | Uso |
| --- | --- |
| `GET /api/health` | Vivacidade do serviço |
| `GET /api/telefonia/sync/diagnostics` | Visão geral: sync travado?, lock do banco, flags de cron, **`custo_diario`** (consumo + tetos + kill-switch) |
| `GET /api/automation/engine/status` | Estado do motor (ciclo atual, estágio, último erro) |
| `POST /api/automation/run-now` (admin) | Dispara um ciclo manual (debug) |
| `POST /api/telefonia/sync/reset-lock` (admin) | Destrava `sync_lock` após crash no meio de um sync (também expira sozinho em 30 min) |

## 3. Problemas comuns → diagnóstico

### "A automação não está auditando nada"
1. `GET /api/telefonia/sync/diagnostics`:
   - `custo_diario.bloqueado_motivo` preenchido? → guardrail de orçamento
     atingiu o teto do dia (ou kill-switch ativo). Itens estão pendentes, não
     perdidos; voltam no reset diário. Ver `docs/07` §4.
   - `automacao_hibrida_ativa=false`? → automação desligada por config.
   - `sync_lock` preso? → `POST /sync/reset-lock`.
2. Painel vazio ≠ IA quebrada: normalmente os FILTROS de negócio barraram as
   entradas (operador sem `ID Huawei` cadastrado, direção inválida, cota do
   mês atingida). Os descartes ficam registrados com motivo em
   `huawei_sync_logs` (status/failure_reason).
3. Operadores ignorados pelo robô: conferir no painel **Colaboradores** se o
   campo `ID Huawei` está preenchido — sem cadastro + sem flag auditável, o
   sync NÃO baixa as ligações daquele operador (regra de negócio, não bug).

### "Quero parar o gasto com IA AGORA" (incidente de custo)
```sql
UPDATE configuracoes SET valor='true' WHERE chave='cost_kill_switch';
```
Sem redeploy. Reverter com `valor='false'`. Detalhe em `docs/07` §4.

### "Ciclo aparece como rodando há muito tempo"
O lock do ciclo expira por TTL (30 min) e o release tem retry com conexão
nova (v1.3.119). Se persistir: verificar `automation_cycle_runs` (último run,
estágio) e o log do serviço; heartbeat stale é reconciliado no ciclo seguinte.

### "Transcrição com qualidade ruim"
- Confiança ~52-53% é o TETO normal para codec de telefonia (G.729/GSM) —
  não é defeito.
- Não reativar `hybrid_dual` (descontinuado) nem noise reduction (piora
  telefonia comprimida). O candidate selector já escala para premium quando
  o `fast` não presta.

### "Item de teste apareceu em produção"
A suite escreve no banco. NUNCA rodar testes com `DATABASE_URL` de produção —
guard no conftest bloqueia o host de prod (`docs/09-testes.md`).

## 4. Dados e retenção

- Áudios classificados: storage de mídia (`media_files` aponta o backend) com
  limpeza por retenção (`cleanup_classified_audio_storage`, 30 dias default).
- Descarte da automação = tombstone permanente em `huawei_sync_logs` (não
  reaparece em syncs futuros); apenas falha técnica transitória é reversível.
- Cota: máx. 2 auditorias por operador/mês aplicada no ENVIO ao supervisor
  (auditor deleta uma anterior para liberar espaço).

## 5. Logs e monitoramento

- Logs do serviço: stdout do container (Cloud Run hoje; equivalente na infra
  da empresa).
- Sentry opcional (`SENTRY_*`): erros e traces com sample rate baixo.
- Histórico de mudanças do sistema: `logs/versions/x.y.z.md` (changelog
  técnico, uma entrada por versão).
