# Relatório Técnico: Comportamento de Sincronização OBS e Deploy Final

**Data:** 05/05/2026
**Módulo:** Integração Huawei AICC (Telefonia)
**Responsável:** Lucas Afonso

## 1. Ajuste Definitivo do Filtro de Direção (`isCallIn`)

A partir da confirmação com o suporte técnico da Huawei (Caio), o mapeamento do parâmetro `isCallIn` no endpoint de `querycalls` foi invertido no código de produção para refletir a arquitetura do parceiro:

- **`isCallIn: "false"`**: Agora mapeado corretamente para retornar ligações **Ativas / Efetuadas** (Outbound).
- **`isCallIn: "true"`**: Mapeado para retornar ligações **Receptivas / Recebidas** (Inbound).

Esta alteração garante que os filtros das Áreas de Risco operem com extrema precisão, poupando custos de Inteligência Artificial ao ignorar chamadas com direção não pertinente. O código já foi publicado (deploy) e está operando no Google Cloud Run.

## 2. Análise do Comportamento OBS vs FS (Real-time vs Batch)

Durante a monitoria do sistema, o painel indicou o seguinte cenário no log de tentativas de download para chamadas recentes:
- **OBS direto:** 20 tentadas, 0 sucesso, 20 falha
- **FS fallback:** 20 tentadas, 20 sucesso, 0 falha

### Investigação e Causa Raiz
Para entender o motivo das falhas no OBS mesmo com credenciais 100% validadas, foi criado um script de auditoria direta no bucket (`obs-nstech-opentech`) para inspecionar a árvore de diretórios. 

Constatou-se a seguinte arquitetura do lado da Huawei:
- Os áudios brutos (`.V3`) **não são gravados no OBS em tempo real**. 
- O diretório `Voice/` possuía pastas até o dia de ontem (`20260504`). A pasta do dia corrente (`20260505`) ainda não existia.
- A Huawei armazena as ligações recentes em um servidor de arquivos transacional (CC-FS) e apenas realiza a sincronia (batch upload) para o bucket OBS (Cold/Warm Storage) no fim do dia ou durante a madrugada.

### Conclusão sobre a Resiliência
O comportamento do nosso robô foi **exatamente o esperado e arquitetado**:
1. Ele tentou buscar o áudio de poucos minutos atrás na via mais rápida (OBS).
2. Constatou que o áudio ainda não havia sofrido *sync* pela Huawei (falha no OBS).
3. Imediatamente acionou o plano de contingência (*FS Fallback*), conectando-se ao servidor transacional da Huawei e resgatando o áudio fresco com **100% de sucesso**.

Quando o robô for acionado para retroceder horas em dias anteriores (D-1, D-2), a taxa de sucesso do OBS saltará para 100%, reduzindo drasticamente a latência e a carga na rede, cumprindo o seu papel híbrido.

## 3. Status Geral da Operação

Com estas últimas implementações, o módulo de telefonia da auditoria atinge um estado de maturidade e estabilidade total:

- **Comunicação de Rede:** O tráfego de saída agora flui de forma unificada e segura através do Cloud NAT (IP Fixo: `35.199.111.152`).
- **Automação Híbrida:** Robô habilitado em produção e executando a cada 10 minutos de forma invisível via Cloud Scheduler.
- **Painel de Controle:** Sincronismo da variável `_LAST_SYNC` restaurado, garantindo que o painel mostre os dados das execuções autônomas em tempo real.
- **Filtros e Coleta:** Direção de chamadas devidamente rastreada e contornando delays arquitetônicos do parceiro com fallback resiliente.