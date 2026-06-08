# Fase 3 - Refatoracao Backend Huawei

Data de referencia: 2026-05-19

## Estado atual

- Fase 1 foi commitada e pushada em `b618958 docs: centraliza referencias canonicas`.
- Fase 2 foi limpeza local de arquivos ignorados; nao gerou commit.
- A Fase 3 foi apenas iniciada com leitura e mapeamento. Ainda nao houve
  alteracao de codigo.
- `git status` antes deste plano estava limpo em `main...origin/main`.

## Objetivo da fase

Reduzir o tamanho e acoplamento de `backend/core/huawei_sync.py` e,
depois, de `backend/routers/telefonia.py`, preservando contratos publicos,
rotas e comportamento operacional.

## Alvo inicial

Arquivo principal:

- `backend/core/huawei_sync.py` com cerca de 2.100 linhas.

Arquivos relacionados:

- `backend/routers/telefonia.py`
- `backend/core/huawei_client.py`
- `backend/core/huawei_obs_client.py`
- `backend/core/huawei_discovery.py`
- `backend/core/huawei_direction.py`
- `backend/core/huawei_d_minus_1.py`
- `backend/tests/test_huawei_sync.py`
- `backend/tests/test_telefonia_router.py`

## Diagnostico rapido

`huawei_sync.py` mistura:

- gate de feature e carregamento de configuracao;
- resolucao de credenciais;
- normalizacao de IDs Huawei/OBS;
- filtros operacionais por setor/direcao;
- resolucao de operador;
- descoberta de chamadas;
- download FS/OBS;
- enfileiramento para triagem;
- classificacao legada opcional;
- lock de execucao;
- orquestracao do ciclo completo.

O risco maior e que os testes e alguns callers importam funcoes privadas de
`core.huawei_sync`, entao a primeira refatoracao deve manter reexports ou aliases
com os nomes atuais.

## Recorte recomendado para continuar

Comecar por uma extracao pequena, com baixo risco e boa cobertura de testes:

1. Criar `backend/core/huawei_sync_config.py`
   - mover `_ensure_enabled`;
   - mover `_load_config`;
   - mover `_missing_credentials`;
   - mover `_env_flag`.

2. Criar `backend/core/huawei_sync_identifiers.py`
   - mover `_clean_obs_prefix`;
   - mover `_clean_huawei_operator_id`;
   - mover `_obs_prefix_candidates`;
   - mover `_obs_match_ids`;
   - mover `_download_id_candidates`;
   - mover `_download_candidate_sort_key` se for possivel sem ciclo ruim.

3. Em `backend/core/huawei_sync.py`
   - importar essas funcoes dos novos modulos;
   - manter os mesmos nomes no namespace de `huawei_sync.py`;
   - evitar mudar chamadas internas no primeiro passo alem dos imports.

## Cuidados tecnicos

- `_load_config` depende de `database.get_config_value`.
- `_missing_credentials` depende de `OAUTH_DIRECT_MODES`.
- `_download_candidate_sort_key` depende de:
  - `get_call_duration_seconds`;
  - `HuaweiDiscoveryService._coerce_huawei_time_ms`.
- `_clean_huawei_operator_id` depende de `normalize_huawei_agent_id`.
- `backend/core/huawei_d_minus_1.py` importa `_load_config` de
  `core.huawei_sync`; manter compatibilidade.
- Testes em `backend/tests/test_huawei_sync.py` chamam varias funcoes privadas
  por `huawei_sync._nome`; manter compatibilidade.

## Testes minimos depois do primeiro recorte

Rodar:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_huawei_sync -q
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_telefonia_router -q
```

Se esses passarem, rodar ao menos:

```powershell
npm run build
```

Antes de pushar uma refatoracao maior, deixar o pre-push rodar tudo.

## Ordem sugerida da Fase 3

1. Extrair config/credenciais e identificadores mantendo reexports.
2. Extrair regras de skip/direcao para `backend/core/huawei_sync_filters.py`.
3. Extrair resolucao de operador para `backend/core/huawei_sync_operators.py`.
4. Extrair enfileiramento/classificacao para um modulo separado.
5. So depois reduzir `backend/routers/telefonia.py`, deixando router como camada
   HTTP fina.

## Criterio de pronto do primeiro PR/commit de Fase 3

- `huawei_sync.py` menor sem alteracao de comportamento.
- Imports antigos ainda funcionando.
- `test_huawei_sync` passando.
- `test_telefonia_router` passando.
- Diff facil de revisar, preferencialmente so move/import/reexport.
