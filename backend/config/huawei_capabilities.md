# Matriz de Funcionalidades Huawei AICC (Capabilities)

Este arquivo descreve as capacidades operacionais e de consulta que utilizamos (ou evitamos) da API da Huawei AICC, servindo como contrato de integração e filtro de segurança.

## Configuração Geral

- **Autenticação Padrão (CMS e CC-FS):** OBRIGATÓRIO utilizar o Proxy C2 (`opentech.teledatabrasil.com.br`) e os métodos de validação HMAC (ak/sk). A Huawei bloqueou explicitamente o uso do `tokenByAkSk` direto para essas rotas.
- **Identificador de Tenant:** `X-TenantSpaceID` (usado apenas em APIs genéricas ou C3, não misturar com CMS).
- **IPs Autorizados de Saída:** Todo o tráfego do Cloud Run DEVE passar pelo VPC NAT Gateway (`35.199.111.152`) usando a tag `vpc-egress=all-traffic` para não ser bloqueado (erro 403) no NGINX da Teledata.

## Matriz de Endpoints

### 1. Descoberta de Chamadas (Telefonia/CMS)
Endpoints seguros para uso massivo e leitura (Read-Only).

- **`queryCalls`** (`/rest/cmsapp/v2/openapi/vdn/querycalls`)
  - **Uso:** Descobrir lista bruta de chamadas por período, VDN e direção (`isCallIn`).
  - **Status:** ATIVO (Motor Principal de Busca).
  - **Limitação:** Não filtra por operador (`agentId`). Retorna dados parciais de tabulação em algumas versões.

- **`agentoprinfo`** (`/rest/cmsapp/v1/openapi/agent/agentoprinfo`)
  - **Uso:** Consultar chamadas de um operador específico (`currentAgentId`).
  - **Status:** PREVISTO (Melhoria de Busca).
  - **Vantagem:** Evita baixar milhares de chamadas para auditar 2 de um único agente.

- **`queryManualIndexesByCondition`** (`/rest/cmsapp/v1/callinday/querymanualindexesbycondition`)
  - **Uso:** Busca cirúrgica por número de destino (`calleeNos`).
  - **Status:** PREVISTO (Busca Ativa / Rastreio Rápido).

- **`querybasiccallinfo`** / **`querydetailcallinfo`**
  - **Uso:** Buscar detalhes enriquecidos (ex: tabulação completa, tempos de fila e hold) por `callId`.
  - **Status:** PREVISTO (Filtro Anti-IA e Metadados).

### 2. Tabulação e Motivos (Regras de Negócio vs. Técnica)
Campos cruciais para a Triagem e Classificação.

- **`callReason` / `talkReason` / `talkRemark`**
  - **O que é:** O motivo de negócio selecionado pelo operador (Tabulação/Wrap-up).
  - **Ação:** Deve alimentar diretamente a classificação do Alerta na Triagem.

- **`leaveReason`**
  - **O que é:** Motivo técnico de desconexão (ex: Cliente desligou, timeout).
  - **Ação:** Deve ser usado como "Filtro Anti-IA". Se a chamada tem menos de 30s e o `leaveReason` é queda, ela deve ser descartada sem gastar tokens GPT.

### 3. Extração de Áudio e Gravações (OBS e CC-FS)
Operações sensíveis em termos de LGPD (Conteúdo do áudio).

- **`downloadRecord` / `downloadRecordFile`** (`/CCFS/resource/ccfs/...`)
  - **Uso:** Baixar o áudio via ID da chamada ou arquivo.
  - **Status:** ATIVO.
  
- **`getRecordFileUrlFromObs` / Acesso direto OBS**
  - **Uso:** Baixar áudio do Object Storage.
  - **Status:** ATIVO.

### 4. Endpoints Operacionais (Agent Gateway) - PERIGO
Alteram o estado da operação da central telefônica. O robô de auditoria NÃO deve utilizá-los sem isolamento e permissão estrita.

- **`/agentgateway/resource/onlineagent/...`** (ex: `login`, `saybusy`, `work`, `forcelogout`)
- **`/agentgateway/resource/voicecall/.../callout`** (Originar chamada)
- **Status Geral:** RESTRITO / BLOQUEADO para o fluxo analítico.

## Fluxo de Decisão de Qualidade (Call Quality Score)
Antes de baixar/auditar uma chamada, ela deve passar pelos seguintes "Gates":
1. Possui `recordId` válido?
2. Duração é > `X` segundos? (Evita caixas postais mudas).
3. O `leaveReason` + Duração indica queda imediata? (Se sim, descarta).
4. O `agentId` (operador) foi resolvido com sucesso?
5. A cota mensal do operador foi atingida? (Se sim, pula).
