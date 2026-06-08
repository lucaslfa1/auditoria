# Relatório de Atividades: Sincronização Huawei AICC
**Data:** 22 de abril de 2026

## O Problema
Foi identificado um ciclo infinito ("coleta infinita") em que o backend estava puxando um volume excessivo de chamadas telefônicas da plataforma Huawei AICC para processamento simultâneo, o que sobrecarregava o disco local e os custos de avaliação (LLM/Azure).
O sintoma era um looping em background sem fim aparente, além do registro em logs de chamadas repetidas sem informações vitais do atendente (`agentId` ausente no raw object da ligação).

## A Investigação
Durante a investigação através de consultas simuladas e scripts isolados:
1. **Comportamento do `querycalls`:** Constatou-se que a API da Huawei `/rest/cmsapp/v1/openapi/vdn/querycalls` e `/v2/.../querycalls` não respeita o envio de parâmetros opcionais de restrição como o `agentId`. Quando a automação pedia as ligações "do operador X", a Huawei devolvia todas as chamadas do VDN inteiro (a empresa toda).
2. **O Ciclo Infinito:** Como a automação baseava-se em um looping sequencial sobre *cada operador cadastrado* no banco (mais de 100), ela repetia o mesmo pedido global mais de 100 vezes. Por consequência, enfileirava as mesmas centenas de chamadas globais repetidamente (para download e classificação LLM) por ciclo.
3. **Validação pela Documentação:** A leitura da documentação oficial em PDF da Huawei (`AICC_25.300.1_CC-CMS Interface Reference.pdf`) confirmou empiricamente que o endpoint suporta nativamente apenas os filtros `vdn`, `ccId`, `callerNo`, `calleeNo`, `beginDate`, `endDate`, `limit`, e `offset` — `agentId` nunca esteve entre as chaves de query válidas para o endpoint histórico.

## A Solução Implementada
A arquitetura do motor de coleta foi invertida. Em vez do orquestrador (`backend/core/huawei_sync.py`) iterar por cada operador tentando descobrir suas chamadas passadas, o fluxo agora é **Global (Lote) e Analítico**.

- **Fim do Looping Redundante:** O motor agora realiza uma **única** chamada global para a direção INBOUND e uma para OUTBOUND no período retrospectivo.
- **Cota de Segurança:** Para não saturar a máquina, o ciclo agora processa um máximo seguro pré-definido por execução (ex: 20 áudios), enfileirando apenas o essencial por hora.
- **Descoberta Contextual (LLM):** O `huawei_sync` enfileira a chamada com a tag "Não Identificado" e submete à Inteligência Artificial (GPT-4o). A própria inteligência artificial agora ouvirá a chamada transcrita ("Olá, aqui é o operador X") e inferirá a identidade, atrelando a nota ao funcionário correto, ou direcionando para avaliação sem dono.
- **Tabela Faltante Criada:** A tabela do banco local `huawei_sync_logs` responsável por garantir que um áudio não seja baixado duas vezes (idempotência) estava ausente no banco principal, fazendo registros de download sumirem silenciosamente. Essa tabela e seu índice foram devidamente criados via SQL na base de dados ativa.

## Status Atual
As correções foram aplicadas, o backend foi estabilizado, e os testes de unidade passaram perfeitamente. A chave `ENABLE_HUAWEI_SYNC` encontra-se `false` temporariamente no arquivo `.env` para proteção e conforto do administrador, mas a lógica de sistema já está 100% pronta e preparada para não causar mais surtos infinitos assim que religada.
A limitação da documentação do serviço também foi salva na "memória" de longa duração do projeto para guiar futuros desenvolvimentos sem erros.
