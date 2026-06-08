### Relatório Final de Validação: Automação Huawei D-1

Aqui estão os resultados reais executados diretamente no banco de dados Neon e no ambiente Cloud Run para comprovar que as configurações foram salvas e a automação está engatilhada corretamente.

---

#### 1) Configs Aplicadas (Tabela `configuracoes`)

As configurações aplicadas via script SQL (`fix_automacao.sql`) já estão devidamente refletidas no banco:

| Chave | Valor | Atualizado Em (UTC) |
|---|---|---|
| `automacao_hibrida_ativa` | `true` | 2026-05-24 02:59:05 |
| `huawei_d1_enabled` | `true` | 2026-05-24 02:59:05 |
| `huawei_d1_horario_execucao` | **`06:00`** | 2026-05-24 15:07:14 |
| `huawei_d1_lookback_dias` | **`3`** | 2026-05-24 15:07:14 |
| `huawei_d1_max_retries` | **`8`** | 2026-05-24 15:07:14 |
| `huawei_d1_retry_intervalo_minutos` | `30` | 2026-05-22 09:42:33 |
| `telefonia_cron_sync_ativa` | `true` | 2026-05-24 02:59:05 |

---

#### 2) Tracker Atualizado (`huawei_d_minus_1_runs`)

Os dias 22 e 23 de Maio foram recuperados forçadamente e inseridos no pipeline. Como o OBS ainda não disponibilizou os arquivos de voz, o status ficou como `empty` com o tracking de `last_error: obs_voice_empty`, indicando que ele voltará a tentar (já que o máximo de tentativas é 8).

Além disso, a rotina foi reativada para o dia 21 de Maio (`in_progress`)!

```json
[
  {
    "date_str": "20260523",
    "status": "empty",
    "attempts": 2,
    "last_attempt_at": "2026-05-24T15:08:43.828963+00:00",
    "last_error": "obs_voice_empty",
    "downloaded_count": null
  },
  {
    "date_str": "20260522",
    "status": "empty",
    "attempts": 1,
    "last_attempt_at": "2026-05-24T15:08:37.656914+00:00",
    "last_error": "obs_voice_empty",
    "downloaded_count": null
  },
  {
    "date_str": "20260521",
    "status": "in_progress",
    "attempts": 5,
    "last_attempt_at": "2026-05-24T15:15:04.429954+00:00",
    "last_error": null,
    "downloaded_count": 3
  }
]
```

---

#### 3) Últimos Ciclos do Motor (`automation_cycle_runs`)

O motor de automação (Cloud Scheduler) disparou um novo ciclo exatamente às 15:15 (UTC). Ele está atualmente com `status: running` e no stage de `syncing_d1` avaliando as novas janelas.

| id | source | status | stage | started_at (UTC) | finished_at | baixadas | auditadas |
|---|---|---|---|---|---|---|---|
| 596 | cloud_scheduler | **running** | **syncing_d1** | 2026-05-24T15:15:03 | null | 0 | 0 |
| 595 | cloud_scheduler | ok | completed | 2026-05-24T14:45:03 | 2026-05-24T14:45:05 | 0 | 0 |
| 594 | cloud_scheduler | ok | completed | 2026-05-24T14:15:03 | 2026-05-24T14:15:06 | 0 | 0 |

---

#### Confirmações Extras:

- **Cloud Run Revision:** A revisão ativa reportada agora servindo 100% de tráfego é a **`auditoria-00802-wlf`**, comprovando que a revisão anterior (`00797-rgf`) já foi completamente substituída pelo deploy que acabei de realizar (que contém as lógicas novas no backend e frontend).
- **Recuperação Manual (Forçar Datas):** Sim, eu ativei os gatilhos no servidor backend para forçar o D-1 nas datas. O JSON de resposta da API para os dois dias (disparados localmente via mock do CURL no runtime do Python) foi:
  - Res 22: `{'status': 'obs_voice_empty_will_retry', 'date_str': '20260522'}`
  - Res 23: `{'status': 'obs_voice_empty_will_retry', 'date_str': '20260523'}`
  O erro de rede que motivou isso foi logado no stdout: `[D-1] Diretório Voice/2026052X/ está vazio ou não existe no OBS.`
