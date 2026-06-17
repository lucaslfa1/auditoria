# Guia rápido — Configuração estável do pipeline Huawei D-1

Aplicável ao motor de automação híbrida que baixa as gravações do dia anterior do bucket OBS Huawei (`obs-nstech-opentech/Voice/<YYYYMMDD>/`).

## Modelo mental

1. Um **scheduler HTTP externo** dispara `POST /api/automation/cron/run` e `POST /api/telefonia/cron/sync` (ambos **1x/dia** desde junho/2026 — intervalos curtos foram a causa do estouro de orçamento). Hoje isso é Google Cloud Scheduler; no Azure, use Container Apps Job agendado ou Logic App com o mesmo bearer token.
2. O motor (`backend/core/automation_engine.py`) checa **duas flags** no Postgres antes de rodar: `automacao_hibrida_ativa` e `huawei_d1_enabled` (a terceira, `telefonia_cron_sync_ativa`, foi removida em 2026-06-12).
3. Se ambas estiverem `true`, o motor chama `executar_d_minus_1_pipeline()`, que itera sobre os últimos `lookback_dias` e tenta baixar do OBS.
4. Para cada data, o tracker `huawei_d_minus_1_runs` guarda `status`, `attempts`, `last_attempt_at`. Após `max_retries` tentativas com OBS vazio, a data é abandonada permanentemente.

## Parâmetros (tabela `configuracoes`)

| Chave | Default código | Recomendado | Por quê |
|---|---|---|---|
| `huawei_d1_enabled` | `true` | `true` | Liga o pipeline. Toggle de UI altera as 2 flags atomicamente. |
| `huawei_d1_horario_execucao` | `06:00` | `06:00`–`08:00` | Huawei costuma terminar upload do dia D entre madrugada e início da manhã. Rodar antes das 06:00 quase sempre acha bucket vazio. |
| `huawei_d1_max_retries` | `8` | `6`–`10` | Tolera atrasos. Cada tentativa fracassada fica registrada e respeita o `retry_intervalo`. Valor 1 é uma cilada — uma só tentativa vazia perde o dia inteiro. |
| `huawei_d1_retry_intervalo_minutos` | `60` | `30`–`60` | Tempo mínimo entre re-tentativas para a mesma data. Frequente demais polui logs; raro demais perde dia. |
| `huawei_d1_lookback_dias` | `3` | `3`–`7` | Quantos dias para trás verificar a cada cron. Lookback=1 nunca recupera um dia perdido (se a automação ficar offline 24h+, vira gap permanente). |
| `huawei_d1_limite_ligacoes` | `20` | `20`–`50` | Cap de downloads por ciclo. Subir só se a janela diária estiver crescendo demais. |
| `huawei_cota_max_por_operador_mes` | `2` | conforme contrato | Quantas auditorias por operador por mês. Não afeta download. |
| `huawei_d1_run_lock` | (auto) | — | Lock interno. Se ficar `running` por mais de 2h, é auto-liberado. Não editar manualmente. |

## Armadilhas comuns

- **Horário muito cedo (`00:00`–`05:00`)**: bucket vai vir vazio, retries serão consumidos sem motivo, dia provavelmente perdido. Mantenha 06:00+.
- **`max_retries = 1`**: a primeira tentativa quase sempre acha bucket vazio → dia é marcado `empty` e nunca mais tentado. Causa raiz do incidente de 23–24/05/2026.
- **`lookback_dias = 1`**: se a automação ficar desligada 24h por qualquer motivo (deploy, troubleshooting, toggle off), o dia que ficou para trás nunca é recuperado pelo cron — só com o endpoint manual `/api/telefonia/sync/d-minus-1/run` com `force=true`.
- **Toggle on/off em série**: cada flip gera ~3 escritas no `configuracoes_audit_log` (via `set_automation_enabled_atomic`). Evite mexer no botão de automação em rajadas — observe o efeito por pelo menos um ciclo completo antes do próximo flip.
- **Alterar muitos parâmetros junto**: dificulta diagnóstico. Mude UM parâmetro, espere um ciclo, observe o tracker. Só então mude o próximo.

## Recuperando um dia perdido

Se o tracker mostra `status='empty'` com `attempts >= max_retries` para uma data, o cron normal não vai voltar lá. Duas opções:

1. **Via endpoint manual:**
   ```bash
   curl -X POST https://<host>/api/telefonia/sync/d-minus-1/run \
     -H "Content-Type: application/json" -H "Cookie: <sessão>" \
     -d '{"date_str":"YYYYMMDD","force":true}'
   ```

2. **Limpando o registro do tracker** (deixa o cron tentar de novo no próximo lookback):
   ```sql
   DELETE FROM huawei_d_minus_1_runs WHERE date_str = 'YYYYMMDD';
   ```
   Funciona apenas se a data ainda estiver dentro de `lookback_dias` a partir de hoje.

## Diagnóstico rápido

Sequência de queries para tirar dúvidas em ~30s no Neon SQL Editor:

```sql
-- Estado das flags
SELECT chave, valor FROM configuracoes
 WHERE chave IN ('automacao_hibrida_ativa','huawei_d1_enabled')
    OR chave LIKE 'huawei_d1_%';

-- Histórico recente do tracker
SELECT date_str, status, attempts, last_attempt_at, last_error
  FROM huawei_d_minus_1_runs
 ORDER BY date_str DESC LIMIT 15;

-- Quem mexeu nas flags recentemente
SELECT chave, valor_antes, valor_depois, alterado_por, motivo, alterado_em
  FROM configuracoes_audit_log
 WHERE alterado_em >= NOW() - INTERVAL '7 days'
   AND (chave LIKE 'huawei_%' OR chave = 'automacao_hibrida_ativa')
 ORDER BY alterado_em DESC LIMIT 50;

-- Últimos ciclos do motor
SELECT id, source, status, stage, started_at, finished_at, baixadas, auditadas, error_message
  FROM automation_cycle_runs
 ORDER BY started_at DESC LIMIT 20;
```

## Sintomas vs. causa-raiz

| Sintoma observado | Causa típica |
|---|---|
| Cron dispara mas `Baixadas: 0` em todo ciclo | Bucket OBS vazio (Huawei não depositou ainda) ou tracker já marcou data como `empty` com retries esgotados |
| `WARNING OBS Voice/<data>/ vazio` nos logs | Huawei ainda não finalizou upload — esperar; se persistir > 12h, escalar para admin Huawei |
| Gap inteiro de dia no tracker | Automação ficou desligada o dia anterior; `lookback` não cobriu a janela |
| `CRITICAL após N tentativas` | `max_retries` muito baixo ou intervalo entre tentativas muito curto |
| Flag bate de `true` para `1` ou vice-versa no audit_log | Bug de cliente serializando booleano como número — defesa em `configuration._normalize_boolean_value` deve normalizar |
