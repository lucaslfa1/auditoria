# Diagnóstico do Erro 500 em `/api/configuracoes`

Data: 2026-04-22
Escopo: módulo Telefonia / persistência das configurações administrativas

## Resumo executivo

O erro `500 Internal Server Error` observado no `POST /api/configuracoes` não está reproduzível no estado atual do projeto.

O endpoint foi validado em três camadas:

- chamada direta ao repositório `database.update_config(...)`
- chamada HTTP in-memory via FastAPI/ASGI
- chamada HTTP real contra `http://127.0.0.1:8080/api/configuracoes` com sessão administrativa válida

Em todas elas, as gravações retornaram `200 {"status":"success"}` para:

- `huawei_ccid`
- `huawei_vdn`
- `huawei_app_key`
- `huawei_ak`
- `huawei_sk`
- `huawei_horas_retroativas`
- `rpa_url_login`
- `rpa_usuario`
- `rpa_senha`
- `robo_habilitado`
- `tema_visual`
- `ia_prompt_global`

## Evidências técnicas

### 1. Backend local operacional

- `GET /api/health` respondeu `200`
- raiz `http://localhost:8080/` respondeu `200`
- backend em escuta na porta `8080`

### 2. Banco aceitando escrita

Validações executadas:

- `database.update_config('diag_test_key', 'diag_test_value')` retornou `True`
- leitura posterior com `database.get_config_value(...)` retornou o valor salvo
- `SHOW transaction_read_only` retornou `off`

### 3. Schema da tabela `configuracoes`

Schema encontrado em runtime:

- `chave` `text` `PRIMARY KEY`
- `valor` `text`
- `descricao` `text`
- `atualizado_em` `text default CURRENT_TIMESTAMP`

Não há incompatibilidade estrutural entre o código atual e a tabela em uso.

### 4. Endpoint funcional em HTTP real

Foi gerada uma sessão administrativa válida e realizados `POST`s reais contra o backend local.

Todos os requests testados retornaram `200`.

## Código inspecionado

Arquivos principais:

- `backend/routers/system.py`
- `backend/repositories/configuration.py`
- `backend/database.py`
- `backend/db/runtime_schema.py`
- `src/features/telefonia/hooks/useTelefoniaSync.ts`
- `src/features/settings/components/Settings.tsx`
- `src/features/settings/components/TelephonySettings.tsx`

## Conclusão técnica

O erro `500` registrado anteriormente não aponta hoje para:

- falha estrutural da tabela `configuracoes`
- bloqueio de escrita no banco
- problema geral do endpoint `/api/configuracoes`
- problema sistêmico nas chaves Huawei
- falha reproduzível no fluxo atual do frontend de telefonia

Com base na investigação, as hipóteses mais prováveis para os `500`s históricos são:

### Hipótese 1. Estado transitório do processo ou da conexão

O write path hoje está saudável e consistente. Isso sugere um erro transitório de conexão/pool ou algum estado momentâneo do processo durante as tentativas anteriores.

### Hipótese 2. Valor específico enviado na ocasião

Como o erro não reproduz com os mesmos campos, é possível que uma tentativa anterior tenha enviado algum valor atípico ou corrompido no corpo do request.

### Hipótese 3. Ambiente/tela desatualizados no momento da tentativa

Se houve troca de backend local, refresh parcial da SPA, ou múltiplas abas abertas, o navegador pode ter executado uma tentativa antiga não mais compatível com o estado atual.

## Melhorias aplicadas durante o diagnóstico

Foram adicionados logs mais úteis para futuros incidentes, sem expor segredos:

- no repositório, agora o backend registra `chave` e `valor_len` quando uma gravação falhar
- na rota, agora o backend registra explicitamente a chave que falhou antes de devolver `500`

Arquivos alterados:

- `backend/repositories/configuration.py`
- `backend/routers/system.py`

## Próximo passo recomendado

Para capturar o próximo incidente com precisão:

1. reiniciar o backend local para carregar os logs novos
2. repetir a ação de salvar na tela de Telefonia
3. se o `500` reaparecer, verificar imediatamente:
   - `backend/service-localhost.err.log`
   - `backend/service-localhost.out.log`

Com a instrumentação adicionada, a próxima ocorrência deverá registrar:

- qual `chave` falhou
- o tamanho do valor enviado
- o traceback completo do erro no backend

## Status final

- Diagnóstico concluído
- Erro `500` não reproduzível no estado atual
- Endpoint atualmente operacional
- Observabilidade reforçada para próxima ocorrência
