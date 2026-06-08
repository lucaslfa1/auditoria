# Relatório de Diagnóstico e Estratégia de Telefonia (Huawei AICC)
**Data:** 14 de maio de 2026
**Objetivo:** Consolidar as diretrizes de integração com a API da Huawei (AICC) com base na última devolutiva do fabricante ("Resposta Huawei.docx") e nas limitações detectadas no ambiente.

---

## 1. Diagnóstico do Ambiente e Bloqueios

### 1.1 Erro 403 Forbidden (Bloqueio de IP no Proxy C2)
A equipe da Huawei/Teledata confirmou que os IPs do nosso projeto (35.199.111.152 e 34.171.63.68) já estão autorizados no firewall (NGINX) da URL de produção `opentech.teledatabrasil.com.br`. 

**Causa Raiz do Erro:** O serviço do Google Cloud Run (onde o robô roda) estava configurado com a tag `vpc-access-egress: private-ranges-only`. Isso fazia com que as requisições para a internet contornassem o IP fixo (Cloud NAT) e usassem a rede genérica efêmera do Google, resultando em rejeição pelo firewall da Huawei.

**Solução Aplicada:** A configuração de rede do Cloud Run foi forçada para `--vpc-egress=all-traffic`. Agora, todo o tráfego que sai do robô é mascarado com o IP fixo 35.199.111.152, sanando definitivamente o Erro 403.

### 1.2 Erro 401 Unauthorized (Autenticação no CMS)
Nosso robô estava recebendo erro ao utilizar o token OAuth direto (`tokenByAkSk`) para consultar metadados das ligações.

**Causa Raiz e Decisão da Huawei:** A Huawei instruiu formalmente que os endpoints das categorias CMS (Gestão de Chamadas) e CC-FS (Gravações) não devem ser acessados via `tokenByAkSk`. Esse tipo de token só funciona para APIs periféricas (como Mensageria C3).

**Solução Arquitetural:** Para listar chamadas e baixar ligações, somos **obrigados a manter o Proxy C2** e a estrutura de cabeçalhos C2 Authorization (que envelopam as credenciais em HMAC criptografado). A documentação técnica (`huawei_capabilities.md`) já foi revertida para focar exclusivamente neste modelo para a telefonia.

### 1.3 Limitação Silenciosa: Buscas de Dias Anteriores (D-1)
Um problema grave que nos assombrava era não conseguir baixar lotes retroativos no dia seguinte. A Huawei emitiu um aviso vital: os endpoints padrão como `queryCalls` (índices manuais) só possuem acesso aos **dados do dia atual (D-0)**.

**Impacto:** Se o nosso cron (scheduler) da automação tentar rodar às 01:00 da manhã buscando chamadas do dia anterior, os retornos virão em branco se utilizarmos a API padrão.

---

## 2. Estratégia Recomendada para o Fluxo da Telefonia

Para que o robô seja eficiente, preciso, barato (no consumo de IA) e pare de tentar baixar tudo indiscriminadamente, o novo fluxo de descoberta deve seguir 3 passos lógicos:

### Passo 1: Uso dos Endpoints Corretos (Para evitar o limite D-0)
Ao invés de depender apenas de `queryCalls` da API básica, devemos investir em uma camada de "Investigação Profunda" baseada no operador ou em bilhetagem:
- **Para chamadas do dia (D-0):** Continuamos utilizando `queryCalls` ou `queryManualIndexesByCondition`.
- **Para chamadas retroativas:** Devemos ativar o uso do `downloadAgentOprInfoFile` ou consultar a bilhetagem bruta (CDR).
- **Para auditar operador X (Busca cirúrgica):** Usar o endpoint `agentoprinfo`.

### Passo 2: O Filtro Anti-IA (Corte de Custos)
Ao encontrar o identificador de uma chamada (`callId`), antes de gastar recursos de processamento ou token do GPT enviando o áudio, devemos executar o `querybasiccallinfo` ou `querydetailcallinfo`.

Estes metadados nos permitem analisar dois campos críticos:
1. **`leaveReason` (Motivo de Encerramento):** Mostra quem desligou e porquê. Se o cliente desligou (Customer Hung Up) nos primeiros 20 segundos ou foi timeout sistêmico, **nem fazemos o download do áudio** e a chamada é descartada como imprestável.
2. **`callReason` ou `talkReason` (Tabulação):** Se a chamada foi classificada pelo operador em uma URA de vendas e estamos auditando suporte, ela não deve seguir para o fluxo. 

### Passo 3: Auditoria Cirúrgica e Respeito à Cota
Apenas após passar no Filtro de Qualidade, checa-se o limite (Ex: máximo de 2 chamadas por mês) e, se o operador for elegível, usamos o `getRecordFileUrlFromObs` ou o `downloadRecordFile` para extrair a ligação física e despachá-la para o Whisper (modelo Fast-Path implementado hoje).

---

## 3. Conclusões e Entregáveis

- A infraestrutura está saneada (IP Fixo / VPC All Traffic ativado e verificado).
- As restrições de documentação estão atualizadas e com as chaves Proxy C2 devidamente isoladas em nosso contrato interno (`huawei_capabilities.md`).
- A diretriz de desenvolvimento do *Classifier Tracer* e do *Call Quality Score* agora pode ser iniciada de maneira segura com base nessas premissas técnicas aprovadas pelo fornecedor.
