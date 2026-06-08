### Resultado da Query (a): `huawei_d_minus_1_runs`

Retornou apenas 3 registros no total (a tabela parece não ter outros dias anteriores):

```json
[
  {
    "date_str": "20260523",
    "status": "empty",
    "attempts": 1,
    "last_attempt_at": "2026-05-24T03:00:03.617229+00:00"
  },
  {
    "date_str": "20260521",
    "status": "partial",
    "attempts": 4,
    "last_attempt_at": "2026-05-22T17:50:04.629500+00:00"
  },
  {
    "date_str": "20260520",
    "status": "partial",
    "attempts": 5,
    "last_attempt_at": "2026-05-21T22:50:05.626772+00:00"
  }
]
```

*(Observação: Não há nenhum registro com o status `completed` nestes resultados e o dia 20260522 foi aparentemente ignorado ou apagado, pois não consta na tabela).*

### Resultado da Query (b): Variáveis do Huawei/OBS (Tabela `configuracoes`)

Filtrando todas as chaves pertinentes a Huawei/D-1/OBS, temos:

```json
[
  {
    "chave": "huawei_obs_bucket",
    "valor": "obs-nstech-opentech"
  },
  {
    "chave": "huawei_d1_enabled",
    "valor": "true"
  },
  {
    "chave": "huawei_d1_run_lock",
    "valor": "false"
  },
  {
    "chave": "huawei_d1_max_retries",
    "valor": "1"
  },
  {
    "chave": "huawei_d1_retry_intervalo_minutos",
    "valor": "30"
  },
  {
    "chave": "huawei_d1_lookback_dias",
    "valor": "1"
  },
  {
    "chave": "huawei_d1_horario_execucao",
    "valor": "02:10"
  },
  {
    "chave": "huawei_d1_limite_ligacoes",
    "valor": "10"
  }
]
```

O bucket permanece configurado corretamente como `"obs-nstech-opentech"`. A flag `huawei_d1_enabled` também está `"true"`. O `huawei_d1_run_lock` se encontra livre (`"false"`).
