# Relatório de Incidente e Resolução: Falha no Download de Áudios da Huawei

**Data da Ocorrência:** 03/05/2026 a 05/05/2026
**Data da Resolução:** 05/05/2026
**Módulo:** Integração Huawei AICC (Telefonia)
**Responsável:** Gemini CLI / Lucas Afonso

## 1. Descrição do Problema
O sistema parou de realizar downloads em nuvem das ligações da Huawei a partir do dia 03/05 (domingo). Os relatórios de execução do cron indicavam:
- 0 chamadas encontradas na VDN.
- 0 downloads bem-sucedidos em todas as tentativas (OBS direto, FS fallback, URL pré-assinada).
- O sistema estava operando apenas com chamadas "fantasmas" descobertas via Manifesto CSV do OBS, cujas tentativas de download resultavam em falha (`audio_not_found` ou `ConnectTimeout`).

## 2. Análise de Causa Raiz

A investigação revelou uma combinação de dois fatores distintos: um problema de infraestrutura residual (fantasma) e uma regressão de código.

### Causa Raiz A: O "Proxy Fantasma" (Infraestrutura)
A tabela `configuracoes` do banco de dados de produção (Neon) continha uma entrada legada na chave `huawei_proxy_ip` apontando para o IP `34.171.63.68`. 
- **Impacto:** O código (via `network_utils.py`) interceptava as requisições para a Huawei e as forçava a passar por este IP de proxy.
- **O Bloqueio:** O parceiro da Huawei (Caio) confirmou posteriormente que este IP de proxy **não estava** na Whitelist de segurança deles (foi adicionado apenas no final do incidente).
- **Consequência:** Como o tráfego tentava sair pelo proxy bloqueado, todas as requisições para a API VDN (`querycalls`) e para obter URLs do FileServer (`getRecordFileUrlFromObs`) resultavam em `ConnectTimeout`. Por isso, a VDN sempre retornava 0 ligações.

### Causa Raiz B: Regressão de Otimização (Código)
Uma refatoração realizada no domingo (03/05) introduziu uma otimização agressiva: o sistema passou a pular o download pelo OBS Primário se a ligação não possuísse o campo `recordId`.
- **Impacto:** A API da VDN da Huawei frequentemente omite o `recordId` no histórico recente. Como resultado, ligações válidas e recém-descobertas eram impedidas de tentar o download pelo método mais confiável (OBS) e caíam em fallbacks que falhavam.

## 3. Ações e Correções Implementadas

O incidente foi resolvido através das seguintes ações:

### Fase 1: Correção Lógica e Robustez (Branch `main`)
1. **Relaxamento do Skip no OBS:** O arquivo `backend/core/huawei_sync.py` foi alterado para que o download via OBS só seja ignorado se a chamada for descoberta exclusivamente pelo manifesto (garantindo que o arquivo não existe). Se a chamada for descoberta pela VDN, o download no OBS é tentado mesmo sem o `recordId`.
2. **Retry com ID Curto (Fallback FS):** Em `backend/core/huawei_client.py`, foi adicionada uma lógica de resiliência ao método de download do FileServer. Se o `callId` longo (com hífen) falhar, o sistema automaticamente tenta uma segunda requisição usando apenas a parte numérica final (RecordId).
3. **Cobertura de Testes:** Foram escritos testes unitários adicionais para validar esses novos fluxos de retry e condições de skip, garantindo que o comportamento esperado seja mantido em refatorações futuras.

### Fase 2: Correção de Infraestrutura e Roteamento
1. **Limpeza do Banco de Dados:** A configuração `huawei_proxy_ip` (`34.171.63.68`) foi apagada da tabela `configuracoes` no banco de produção. Imediatamente, o tráfego passou a fluir através da rota padrão do Cloud Run: o **Cloud NAT (IP 35.199.111.152)**.
2. **Confirmação de Whitelist:** Validou-se, através de testes de rede (traces) conduzidos pelo parceiro Caio (Huawei), que o IP do Cloud NAT (`35.199.111.152`) estava corretamente liberado e autorizando requisições com código HTTP 200.

### Fase 3: Consolidação da Arquitetura (Commit `8398b30`)
1. **Remoção da Lógica Legada:** Para blindar o sistema de futuros erros de configuração no banco de dados, o mecanismo de redirecionamento de DNS (`apply_dns_overrides`) voltado para o IP de proxy foi **removido** do código (`backend/core/network_utils.py` e `backend/core/huawei_sync.py`).
2. **Definitivo:** A arquitetura agora garante que o tráfego de saída da aplicação para a Huawei utilizará, invariavelmente, a infraestrutura oficial e nativa de rede do Google Cloud (Cloud NAT).

## 4. Resultado e Conclusão
Após a aplicação das correções de código (enviadas e mescladas na branch `main`) e a oficialização do Cloud NAT limpando o banco de dados, o fluxo de sincronização foi restaurado. 

As chamadas voltaram a ser listadas pela VDN (pois o timeout de proxy foi eliminado) e os downloads em nuvem voltaram a ser concluídos com sucesso através dos métodos primários e fallbacks devidamente ajustados. O sistema agora é mais resiliente a ausências de IDs na API e imune a configurações de roteamento obsoletas.
