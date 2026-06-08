## Relatório de Teste: Telefonia Huawei após novo deploy

Data: 2026-04-22

### Objetivo

Validar o estado operacional da telefonia após o novo deploy, separando:

- disponibilidade do serviço publicado
- configuração do deploy em Cloud Run
- conectividade real com a Huawei AICC a partir da máquina local
- riscos imediatos para o sync de telefonia

### Escopo executado

1. Confirmação da URL publicada no Cloud Run
2. Checagem HTTP básica do serviço publicado
3. Inspeção da configuração do serviço `auditoria` no Cloud Run
4. Leitura da coleção Postman oficial `docs/integracoes/huawei/Huawei_AICC_BrazilSaaS-OPENTECH.postman_collection.json`
5. Consulta real de leitura na Huawei usando as credenciais `HUAWEI_*` do `backend/.env`

### URL ativa confirmada

- `https://auditoria-tqr7bp67na-rj.a.run.app`

### Resultado do deploy publicado

- `GET /` respondeu `200`
- O serviço está no ar e servindo a aplicação web

### Resultado do endpoint de telefonia no deploy

- `POST /api/telefonia/cron/sync` sem autenticação respondeu `403`
- A inspeção da configuração publicada mostrou que o Cloud Run **não** tem `CRON_SECRET_TOKEN`

Conclusão operacional:

- o endpoint de cron da telefonia está publicado, mas na prática está bloqueado por falta de `CRON_SECRET_TOKEN`
- portanto, o sync remoto por cron não está homologado neste momento

### Achados na configuração do Cloud Run

Variáveis presentes no deploy:

- `DATABASE_URL`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_KEY`
- `AZURE_OPENAI_DEPLOYMENT`
- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION`
- `AZURE_WHISPER_ENDPOINT`
- `AZURE_WHISPER_KEY`
- `AZURE_WHISPER_DEPLOYMENT`
- `HUAWEI_AK`
- `HUAWEI_SK`
- `HUAWEI_APP_KEY`
- `HUAWEI_CC_ID`
- `HUAWEI_VDN`
- `ENABLE_HUAWEI_SYNC`
- `HUAWEI_AUTH_MODE`
- `HUAWEI_PROXY_URL`

Variáveis ausentes no deploy que impactam o teste:

- `CRON_SECRET_TOKEN`
- `AZURE_SPEECH_ENDPOINT`

Impacto:

- sem `CRON_SECRET_TOKEN`, o endpoint `/api/telefonia/cron/sync` não pode ser acionado corretamente
- sem `AZURE_SPEECH_ENDPOINT`, o caminho `fast` de transcrição em produção continua sujeito ao erro `AZURE_SPEECH_ENDPOINT nao configurado para Fast Transcription`

### Resultado da conectividade real com a Huawei

Foi executada uma consulta real de leitura usando o fluxo da coleção Postman e o cliente do projeto.

Primeira tentativa:

- a chamada chegou à Huawei
- a Huawei respondeu erro de negócio `0100002: Invalid param, must have parameter: 'isCallIn'`

Interpretação:

- autenticação, assinatura e conectividade externa funcionaram
- o problema inicial não foi rede, IP ou credencial inválida
- o payload da consulta estava incompleto

Segunda tentativa:

- a mesma consulta foi repetida com `isCallIn` preenchido
- a Huawei respondeu com sucesso
- foram retornadas chamadas reais da última hora

Resumo da resposta:

- inbound: `3` registros na amostra
- outbound: `3` registros na amostra

Conclusão:

- a integração com a Huawei está funcional a partir desta máquina
- o IP informado pelo usuário está coerente com um cenário de whitelist ativa
- a parte externa da telefonia respondeu com sucesso em consulta real

### Risco funcional identificado no código atual

O endpoint Huawei `/rest/cmsapp/v2/openapi/vdn/querycalls` exige `isCallIn`.

No código do projeto:

- `backend/core/huawei_client.py` só envia esse campo quando `call_direction` é informado
- em `backend/core/automation_rules.py`, alguns setores ainda não definem `call_direction`

Setores que hoje podem cair nesse problema:

- `logistica`
- `receptivo`

Efeito prático:

- mesmo com Huawei acessível e credenciais válidas, o sync pode falhar nesses setores por payload inválido

### Conclusão final

A telefonia não está totalmente homologada no deploy novo.

Estado atual:

- Huawei externa: funcionando
- autenticação Huawei: funcionando
- consulta real de leitura: funcionando
- Cloud Run publicado: funcionando
- cron remoto de telefonia: bloqueado por ausência de `CRON_SECRET_TOKEN`
- fast transcription em produção: ainda com risco por ausência de `AZURE_SPEECH_ENDPOINT`
- sync por setor: com risco funcional para setores sem `call_direction`

### Parecer

O problema principal neste momento não parece ser a Huawei em si.

Os bloqueios mais concretos estão no deploy/configuração e em uma regra de payload do próprio código:

1. falta de `CRON_SECRET_TOKEN` no Cloud Run
2. falta de `AZURE_SPEECH_ENDPOINT` no Cloud Run
3. setores sem `call_direction` podem quebrar a consulta `querycalls`

### Próximo passo recomendado

Antes de um novo teste fim a fim em produção:

1. publicar `CRON_SECRET_TOKEN` no Cloud Run
2. publicar `AZURE_SPEECH_ENDPOINT` no Cloud Run
3. revisar `backend/core/automation_rules.py` para garantir `call_direction` em todos os setores que usam `querycalls`
4. repetir o teste do endpoint remoto `/api/telefonia/cron/sync`
