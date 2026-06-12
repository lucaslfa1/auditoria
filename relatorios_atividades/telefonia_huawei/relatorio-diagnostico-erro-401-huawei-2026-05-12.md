# Relatório de Diagnóstico: Falha na Sincronização Automática (Huawei)

**Data do Diagnóstico:** 12/05/2026
**Módulo:** Telefonia (Integração Huawei AICC & OBS)
**Responsável:** Lucas Afonso

## 1. Contexto e Sintoma
O sistema de Sincronização Contínua em Segundo Plano (Cloud Scheduler) estava relatando falhas constantes na coleta de ligações. Os relatórios de execução exibiam "0 chamadas baixadas" e os logs de sincronização indicavam erro em todos os métodos de download (OBS, CC-FS e URL Pré-assinada).

## 2. Metodologia de Diagnóstico
Foi criado e executado um script de teste isolado (`test_huawei_connection.py`) para validar separadamente a comunicação com os dois pilares da integração Huawei:
1. **API AICC (VDN/CC-FS):** Responsável por buscar o extrato oficial de ligações e fornecer as URLs de download dos áudios.
2. **Bucket OBS:** Responsável pelo armazenamento bruto e pelo manifesto de contingência (Contact_Record).

## 3. Resultados do Teste

A execução do script revelou um cenário de falha parcial de autenticação:

* **✅ Teste OBS Client (Sucesso):** 
  A conexão com o bucket `obs-nstech-opentech` ocorreu com sucesso (`HTTP 200 OK`). O sistema conseguiu ler o manifesto do dia (20260512) e encontrou 8.427 registros. Isso prova que:
  - O IP de saída do Cloud NAT (`35.199.111.152`) **está** na Whitelist de rede da Huawei para o serviço de Storage.
  - As credenciais secundárias (`obs_ak` / `obs_sk`) estão corretas e ativas.

* **❌ Teste AICC Client (Falha Crítica):** 
  A chamada para o endpoint `/rest/cmsapp/v2/openapi/vdn/querycalls` foi **rejeitada imediatamente** pela Huawei com o status **`HTTP 401 Unauthorized`**. Como consequência:
  - Nenhuma chamada pode ser descoberta pela via oficial (VDN).
  - Todas as tentativas de conversão e download de áudios pela API FileServer (CC-FS) também sofrem cascata de falha de autorização.

## 4. Conclusão da Causa Raiz
O erro de sincronização "vazia" não é um problema de roteamento (proxy fantasma) ou de Timeout, como ocorrido anteriormente no início do mês. O sistema está batendo na porta correta, mas está sendo barrado por um **Erro 401 de Autenticação na API Principal**.

## 5. Próximos Passos (Plano de Ação Futuro)
Como a resolução deste incidente foi pausada momentaneamente, quando retomada, a equipe deverá focar em:

1. **Revisar Credenciais API:** Verificar se o `AK` (Access Key), `SK` (Secret Key), ou a `App Key` configurados na aba "Telefonia" do sistema (banco de dados) foram alterados ou expiraram no painel da Huawei AICC.
2. **Revisar Whitelist de API:** Confirmar com a Huawei se a liberação do IP `35.199.111.152` foi aplicada **também** no API Gateway (`brazilsaas.aicccloud.com`), pois é comum a Huawei separar a segurança do Storage (OBS) da segurança da API (VDN).
