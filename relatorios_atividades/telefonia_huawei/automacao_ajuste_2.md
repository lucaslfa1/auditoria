### Resultado da Query (c): `configuracoes_audit_log` (Filtro >= 2026-05-20)

Os logs confirmam que houve alterações manuais (via UI) e pelo próprio sistema (`automation_engine`). É possível ver uma frenética troca de horários, ativações/desativações e quantidade máxima de retentativas nos dias analisados.

```json
[
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "00:10",
    "valor_depois": "02:10",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-24T03:20:09.046579+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "00:00",
    "valor_depois": "00:10",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-24T03:09:23.016541+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "23:59",
    "valor_depois": "00:00",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-24T02:59:19.944937+00:00"
  },
  {
    "chave": "telefonia_cron_sync_ativa",
    "valor_antes": "1",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-24T02:59:05.429638+00:00"
  },
  {
    "chave": "telefonia_cron_sync_ativa",
    "valor_antes": "true",
    "valor_depois": "1",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-24T02:58:33.050956+00:00"
  },
  {
    "chave": "telefonia_cron_sync_ativa",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-24T02:58:17.375794+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "23:45",
    "valor_depois": "23:59",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-24T02:58:10.670199+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "22:45",
    "valor_depois": "23:45",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-24T02:42:39.403876+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-24T02:42:17.443753+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-24T02:42:17.443753+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-24T02:42:16.224985+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-24T02:42:16.224985+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-24T01:40:06.997263+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-24T01:40:06.997263+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "15:33",
    "valor_depois": "22:45",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-24T01:40:05.184404+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-22T20:08:37.779064+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-22T20:08:37.779064+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "00:00",
    "valor_depois": "15:33",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-22T18:32:31.306482+00:00"
  },
  {
    "chave": "huawei_d1_max_retries",
    "valor_antes": "4",
    "valor_depois": "1",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-22T18:31:55.279588+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-22T18:06:17.397019+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-22T18:06:17.397019+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-22T18:06:16.154441+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-22T18:06:16.154441+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-22T16:31:34.160425+00:00"
  },
  {
    "chave": "huawei_d1_max_retries",
    "valor_antes": "2",
    "valor_depois": "4",
    "alterado_por": "fatima",
    "origem": "ui",
    "alterado_em": "2026-05-22T16:31:33.975437+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "06:44",
    "valor_depois": "00:00",
    "alterado_por": "fatima",
    "origem": "ui",
    "alterado_em": "2026-05-22T16:31:12.847820+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-22T10:00:05.321388+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-22T10:00:05.321388+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "22:00",
    "valor_depois": "06:44",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-22T09:42:56.966321+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-22T09:42:44.185917+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-22T09:42:44.185917+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-22T09:42:43.359429+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-22T09:42:43.359429+00:00"
  },
  {
    "chave": "huawei_d1_max_retries",
    "valor_antes": "1",
    "valor_depois": "2",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-22T09:42:31.078401+00:00"
  },
  {
    "chave": "huawei_d1_max_retries",
    "valor_antes": "2",
    "valor_depois": "1",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-22T09:42:29.816086+00:00"
  },
  {
    "chave": "huawei_d1_max_retries",
    "valor_antes": "5",
    "valor_depois": "2",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-22T09:42:27.324030+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "11:00",
    "valor_depois": "22:00",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-21T21:02:15.648308+00:00"
  },
  {
    "chave": "huawei_d1_max_retries",
    "valor_antes": "3",
    "valor_depois": "5",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-21T20:09:27.554822+00:00"
  },
  {
    "chave": "huawei_d1_max_retries",
    "valor_antes": "2",
    "valor_depois": "3",
    "alterado_por": "lucas",
    "origem": "ui",
    "alterado_em": "2026-05-21T20:09:24.433216+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-21T11:10:13.336871+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-21T11:10:13.336871+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "18:00",
    "valor_depois": "11:00",
    "alterado_por": "fatima",
    "origem": "ui",
    "alterado_em": "2026-05-21T11:10:04.769498+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-20T20:55:54.155846+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-20T20:55:54.155846+00:00"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor_antes": "10:00",
    "valor_depois": "18:00",
    "alterado_por": "fatima",
    "origem": "ui",
    "alterado_em": "2026-05-20T18:58:42.634316+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-20T17:41:49.170440+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-20T17:41:49.170440+00:00"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-20T17:41:45.121804+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "true",
    "valor_depois": "false",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(False)",
    "origem": "system",
    "alterado_em": "2026-05-20T17:41:45.121804+00:00"
  },
  {
    "chave": "automacao_hibrida_ativa",
    "valor_antes": "false",
    "valor_depois": "true",
    "alterado_por": "system:automation_engine",
    "motivo": "set_automation_enabled_atomic(True)",
    "origem": "system",
    "alterado_em": "2026-05-20T12:30:12.350814+00:00"
  }
]
```
