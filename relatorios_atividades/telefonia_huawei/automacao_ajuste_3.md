# Relatório Final — Correção da Coleta Automática Huawei D-1

**Data:** 2026-05-24
**Autor:** lucas 
**Status:** ✅ Código aplicado e empurrado (`ca706d7`) | ⏳ SQL e recuperação manual pendentes

---

## 1. Sintoma reportado

> "O módulo automação parou de funcionar. O sistema não executa mais download automático conforme o horário agendado."

## 2. Hipótese inicial (refutada)

A suspeita imediata foi regressão nos commits recentes (`d9e0c5b` separou coletor/auditor, `09d0a8a` adicionou toggle de cron telefonia, `0816e50` restaurou D-1). A análise apontou para flag `telefonia_cron_sync_ativa` ausente em DBs antigos.

**Refutada pelos logs de produção (`logs.json`, Cloud Run `auditoria-nstech`):**
- ✅ Google Cloud Scheduler dispara `POST /api/automation/cron/run` regularmente (`User-Agent: Google-Cloud-Scheduler`).
- ✅ `is_automation_enabled()` retorna `true` — engine loga `"Automacao ativa. Iniciando ciclo OBS D-1 + auditoria."` (`automation_engine.py:1111`).
- ✅ Pipeline `executar_d_minus_1_pipeline()` é chamado.
- ✅ HTTP listing do bucket OBS retorna `200 OK` — credenciais e rede funcionam.
- ❌ Bucket retorna listagem **vazia** para `Voice/20260523/`.
- ❌ Ciclo encerra com `"Baixadas: 0, Auditadas: 0"` — Cloud Scheduler recebe 200 OK e segue.

**Conclusão:** o cron NÃO parou. O sistema está fingindo trabalhar — pior caso de diagnóstico, pois nada explode.

## 3. Causa-raiz real (cenário composto)

Três configs no banco se combinaram para inviabilizar coletas:

| Config | Valor atual no DB | Default do código (antes do fix) | Efeito |
|---|---|---|---|
| `huawei_d1_max_retries` | **1** | 4 | A primeira tentativa quase sempre acha bucket vazio (Huawei demora a popular). `_is_retry_exhausted()` retorna `True` na 1ª falha → data marcada `empty` permanentemente. |
| `huawei_d1_lookback_dias` | **1** | 1 | Só processa **uma data por ciclo** (sempre D-1 de "agora"). Qualquer dia perdido nunca é recuperado. |
| `huawei_d1_horario_execucao` | **02:10 BRT** | 06:00 | Roda antes de Huawei finalizar upload do D-1. |

E uma janela crítica revelada pelo `configuracoes_audit_log`:

> **22/05 20:08:37 UTC → 24/05 01:40:06 UTC = ~29h30 com automação DESLIGADA.**
> O cron disparou normalmente nessa janela, mas `run_automation_cycle()` saiu no early-return da linha 1063 (`if not is_automation_enabled() and source != "manual_ui"`). `mark_in_progress("20260522")` nunca executou → row nunca nasceu no tracker → gap permanente.

Histórico do audit_log mostra **~15 alterações de configs em 4 dias** (lucas + fatima alternando `max_retries` entre 1–5, `horario` entre 06:44/22:00/00:00/15:33/22:45/23:45/23:59/00:00/00:10/02:10, múltiplos toggles on/off). A automação raramente ficou ligada tempo suficiente para coletar.

### Bug adicional descoberto durante diagnóstico

`useAutomacaoDashboard.ts:142` — `serializeConfigField` chamava `Number(draft[field])` sem checar tipo. Para `telefonia_cron_sync_ativa` (boolean), `Number(true)=1` virava `"1"` no banco. O audit_log registra exatamente isso em 24/05 02:58:33 UTC. O backend rebateu 32s depois via `set_automation_enabled_atomic`, mas a divergência seria fonte futura de bugs.

## 4. Mudanças aplicadas e empurradas (commit `ca706d7`)

Push confirmado em `a02854e..ca706d7 main → main`. Pre-push hook validou TypeScript + 596 testes Python passaram.

### Código
- **`backend/core/huawei_d_minus_1.py`** — defaults `max_retries 4→8`, `lookback_dias 1→3`. Comentário no topo da seção explicando a motivação.
- **`backend/repositories/configuration.py`** — função `_normalize_boolean_value()` aplicada em `update_config`. Whitelist de chaves bool (`automacao_hibrida_ativa`, `huawei_d1_enabled`, `telefonia_cron_sync_ativa`, `automacao_is_paused`, `automacao_is_cancelled`) aceita `1/0/yes/no/sim/não/on/off/true/false` e grava sempre `"true"`/`"false"`.
- **`src/features/automacao/hooks/useAutomacaoDashboard.ts`** — `serializeConfigField` trata booleanos antes da conversão numérica.

### Documentação
- **`docs/integracoes/huawei/HUAWEI_D1_CONFIG_GUIDE.md`** (novo) — guia curto com tabela de parâmetros, valores recomendados, armadilhas, queries de diagnóstico e mapa sintoma → causa.

### Investigação versionada
- `relatorios_atividades/telefonia_huawei/automacao_ajuste.md` — tracker + configs (queries a/b)
- `relatorios_atividades/telefonia_huawei/automacao_ajuste_2.md` — audit_log (query c)
- `relatorios_atividades/telefonia_huawei/automacao_ajuste_3.md` — este relatório

## 5. Pendências manuais (não automatizadas)

### 5.1 Aplicar SQL no Neon Postgres
Arquivo `relatorios_atividades/telefonia_huawei/fix_automacao.sql` (ignorado pelo .gitignore — só nesta máquina). Abrir o **Neon SQL Editor** e colar:

```sql
BEGIN;
UPDATE configuracoes SET valor='8',    atualizado_em=CURRENT_TIMESTAMP WHERE chave='huawei_d1_max_retries';
UPDATE configuracoes SET valor='3',    atualizado_em=CURRENT_TIMESTAMP WHERE chave='huawei_d1_lookback_dias';
UPDATE configuracoes SET valor='06:00',atualizado_em=CURRENT_TIMESTAMP WHERE chave='huawei_d1_horario_execucao';
-- (INSERTs em configuracoes_audit_log inclusos no .sql)
COMMIT;

-- Verificar:
SELECT chave, valor FROM configuracoes WHERE chave LIKE 'huawei_d1_%';
```

> Os defaults do código também foram atualizados (commit acima), mas o banco tem precedência via `get_pipeline_config()`. Sem o UPDATE acima, o código novo não muda comportamento.

### 5.2 Recuperar 20260522 e 20260523
O cron normal não vai voltar nessas datas (mesmo com `lookback=3`, 20260522 já está fora da janela a partir de 24/05+). Disparar manualmente:

```bash
curl -X POST https://auditoria-tqr7bp67na-rj.a.run.app/api/telefonia/sync/d-minus-1/run \
  -H "Content-Type: application/json" -H "Cookie: <sua_sessao>" \
  -d '{"date_str":"20260522","force":true}'

curl -X POST https://auditoria-tqr7bp67na-rj.a.run.app/api/telefonia/sync/d-minus-1/run \
  -H "Content-Type: application/json" -H "Cookie: <sua_sessao>" \
  -d '{"date_str":"20260523","force":true}'
```

Se vier `already_done` ou `empty` prematuramente:
```sql
DELETE FROM huawei_d_minus_1_runs WHERE date_str IN ('20260522','20260523');
```
e re-rodar os curls.

### 5.3 Aguardar o deploy no Cloud Run
O commit foi empurrado para `main`. Pipeline de CI/CD do GitHub Actions vai fazer o build + deploy. Confirmar no Cloud Run quando a nova revisão estiver ativa (atual era `auditoria-00797-rgf`). A correção do bug do UI e a defesa booleana só fazem efeito depois do deploy.

## 6. Validação após aplicação

Esperado nas próximas 24h:
1. **`huawei_d_minus_1_runs`** deve mostrar `attempts` subindo de 1 para até 8 antes de marcar uma data como definitivamente perdida.
2. **`obs_voice_empty_will_retry`** deve aparecer com mais frequência no tracker (são tentativas legítimas, não erro).
3. **`Baixadas > 0`** em pelo menos um ciclo após `06:00 BRT`.
4. **Nenhum valor `"1"` ou `"0"`** novo nas chaves bool em `configuracoes_audit_log` — todos devem ser `"true"`/`"false"`.

Query de monitoramento:
```sql
SELECT date_str, status, attempts, last_attempt_at, last_error
  FROM huawei_d_minus_1_runs ORDER BY date_str DESC LIMIT 10;
```

## 7. Recomendações de uso (para evitar repetir o cenário)

1. **Não experimentar configs em rajada.** Mude UM parâmetro, espere um ciclo completo, observe o tracker, só então mude outro. O audit_log dos últimos 4 dias mostra ~15 alterações — isso mascara causa-efeito.
2. **Nunca colocar `max_retries=1`** sob nenhuma circunstância. O Huawei OBS é assíncrono e qualquer falha transitória custa o dia inteiro.
3. **Horário ≥ 06:00 BRT.** Antes disso o bucket frequentemente está vazio.
4. **Lookback ≥ 3 dias.** Se a automação cair por qualquer motivo (deploy, troubleshooting, toggle off), o lookback é a única rede de proteção.
5. **Antes de desligar a automação**, lembrar: se ficar offline > 24h, todos os dias daquela janela viram perda permanente (precisam de `force=true` manual).
6. **Para diagnóstico futuro**, começar SEMPRE pelas 4 queries da seção "Diagnóstico rápido" no `HUAWEI_D1_CONFIG_GUIDE.md` antes de mexer em código.

## 8. Linha do tempo (referência)

| Quando (UTC) | Quem | Ação | Impacto |
|---|---|---|---|
| 22/05 09:42 | lucas | `max_retries`: 5→2→1→2 (~3 mudanças em 4s) | Experimentação |
| 22/05 16:31 | fatima | `max_retries`: 2→4 + `horario`: 06:44→00:00 | Corrigia parcialmente |
| 22/05 18:31 | lucas | `max_retries`: **4→1** | Causa-raiz do "1 tentativa" |
| 22/05 18:32 | lucas | `horario`: 00:00→15:33 | Cilada — Huawei talvez não populou ainda |
| 22/05 20:08 | system | Toggle DESLIGADA | Início do gap de 29h |
| 23/05 (dia todo) | — | Nada | Cron disparava mas motor pulava — gap de 20260522 |
| 24/05 01:40 | lucas | Toggle LIGADA + `horario`→22:45 | Fim do gap |
| 24/05 02:42–03:20 | lucas | Mais 5 mudanças de `horario` em 38min | Convergiu pra 02:10 |
| 24/05 03:00 | system | Primeiro ciclo do dia → 20260523 empty (1 tentativa) | Tracker registra |
| 24/05 ~12:00 | lucas | Solicita diagnóstico | — |
| 24/05 (este commit) | ca706d7 | Fix aplicado + push | Em deploy |
