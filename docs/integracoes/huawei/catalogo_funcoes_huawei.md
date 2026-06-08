# Catálogo de Funções Huawei AICC

Documentação de Funções Huawei AICC
Projeto Auditoria | gerado em 14/05/2026 08:49
Objetivo: consolidar as funções/endpoints Huawei AICC que aparecem na collection local e no código do projeto, em uma tabela simples para estudo. A coluna "Status" separa o que já é usado/previsto no robô de telefonia, o que é apenas documentado/testável e o que pode alterar estado operacional.
Autenticação atual preferida: tokenByAkSk / OAuth direto, com X-TenantSpaceID quando aplicável. O proxy C2 Teledata fica como legado.
Para auditoria de ligações, o caminho principal é descobrir chamadas em querycalls, obter metadados/registro, baixar gravação via OBS ou CC-FS, e só depois triagem/auditoria.
Tabulação/motivo da chamada: no projeto é tratado como callReason, vindo de talkReason/talkRemark quando disponível. leaveReason é motivo técnico de desconexão, não a classificação do operador.
Endpoints de Agent Gateway e Mobile podem logar agente, mudar status, iniciar chamadas ou encerrar sessão. Não executar em produção sem autorização explícita.
Glossário Rápido
Campo
Significado
ccId
ID do call center.
vdn
VDN/VCC usado como escopo da consulta de telefonia.
callId
Identificador principal da chamada/interação.
recordId
Identificador de gravação, quando a chamada tem áudio associado.
workNo / agentId
Identificador do operador/agente na Huawei.
isCallIn
Direção da chamada: true = receptiva/inbound; false = ativa/outbound.
callReason
Motivo/tabulação de negócio da chamada. É o campo útil para filtros de auditoria.
leaveReason
Motivo técnico de saída/desconexão do dispositivo/chamada.
skillId
Fila/skill de atendimento.
OBS
Object Storage da Huawei onde gravações/arquivos podem estar armazenados.
Funções Mais Importantes Para Telefonia/Auditoria
Esta primeira tabela é o atalho de estudo. Ela prioriza descoberta de chamadas, metadados, gravações, tabulação e cadastros úteis.
Módulo
Função
Método
Endpoint
Para que serve
Parâmetros-chave
Status
Cuidados
Autenticação
1. tokenByAkSk Copy
POST
{{base_url}}/apigovernance/api/oauth/tokenByAkSk
Gera token OAuth/AccessToken a partir de app_key/app_secret. Base da autenticação direta atual.
base_url, app_key, app_secret
Em uso/previsto no robô de telefonia
Tratar credenciais e tokens como segredo.
Configuração/Gestão
Agent account query
POST
{{base_url}}/apiaccess/rest/cc-management/v1/agentAccount/query
Lista contas de agentes.
base_url, pageNum, pageSize
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
querySkills
POST
{{base_url}}/apiaccess/rest/cc-management/v1/skill/querySkills
Lista skills/filas configuradas no AICC.
base_url, limit, offset, name
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Gravações/Bilhetagem
Get bucket object
GET
{{base_url_obs}}/{{object_name_obs}}
Acesso direto ao Huawei OBS para listar ou baixar objetos/gravações.
object_name_obs, base_url_obs, prefix
Em uso/previsto no robô de telefonia
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
List objects
GET
{{base_url_obs}}/{{obs_object_parameters}}
Acesso direto ao Huawei OBS para listar ou baixar objetos/gravações.
obs_object_parameters, base_url_obs
Em uso/previsto no robô de telefonia
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
downloadAgentOprInfoFile
POST
{{base_url}}/CCFS/resource/ccfs/downloadAgentOprInfoFile
Consulta operações/eventos de agente em um período, como login, descanso, trabalho e chamadas.
base_url, request, version, msgBody, agentOprInfoFileName
Documentado/testável
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
downloadBillFile
POST
{{base_url}}/CCFS/resource/ccfs/downloadBillFile
Baixa arquivo ZIP de bilhetagem/CDR previamente gerado.
base_url, request, version, msgBody, billFileName
Documentado/testável
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
downloadRecord
POST
{{base_url}}/CCFS/resource/ccfs/downloadRecord
Baixa gravação de voz diretamente por callId.
base_url, request, version, msgBody, callId, ccId
Em uso/previsto no robô de telefonia
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
downloadRecordFile
POST
{{base_url}}/CCFS/resource/ccfs/downloadRecordFile
Baixa gravação por caminho/nome de arquivo retornado pela Huawei/OBS.
base_url, request, version, msgBody, fileName
Em uso/previsto no robô de telefonia
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
getRecordFileUrlFromObs
POST
{{base_url}}/CCFS/resource/ccfs/getRecordFileUrlFromObs
Obtém URL pré-assinada/ponte para gravação no OBS.
base_url, callId, beginTime, endTime, version
Em uso/previsto no robô de telefonia
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
queryAgentOprInfoData
POST
{{base_url}}/CCFS/resource/ccfs/queryAgentOprInfoData
Consulta operações/eventos de agente em um período, como login, descanso, trabalho e chamadas.
base_url, request, version, msgBody, beginTime, endTime, callId, dataType, callBackURL
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Gravações/Bilhetagem
queryBillData
POST
{{base_url}}/CCFS/resource/ccfs/queryBillData
Solicita arquivo de bilhetagem/CDR via CC-FS para período e tipo de dado.
base_url, request, version, msgBody, beginTime, endTime, dataType, callBackURL
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Mensageria/Multimídia
querycontent
POST
{{base_url}}/rest/cmsapp/v1/openapi/multimedia/querycontent
Consulta conteúdo/mensagens multimídia por callId; mantido no cliente como best-effort.
callId, ccId, vdn
Detectado no código; validar contrato Huawei
Pode expor histórico de mensagem/conteúdo; usar com finalidade definida.
Telefonia/CMS
queryCallState
POST
{{base_url}}/apiaccess/CC-Management/v1/mobileAgent/queryCallState
Lista chamadas por VDN, período e direção. É o endpoint principal de descoberta de ligações.
base_url, callSerialNo
Em uso/previsto no robô de telefonia
Não filtra por operador; consultar por VDN, período e direção.
Telefonia/CMS
14.1 Querying Call Result Data
POST
{{base_url}}/apiaccess/rest/dataprocess/v1/openapp/queryCallManualDetailInfo
Consulta detalhes de ligações manuais por callId ou por janela. Pode trazer dados de chamada, agente e histórico.
base_url, subCcNo, vdn, callId, callerNo, calleeNo, beginDate, endDate, callType, mediaType
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
queryManualIndexesByCondition
POST
{{base_url}}/rest/cmsapp/v1/callinday/querymanualindexesbycondition
Consulta indicadores/índices de chamadas manuais por condição: período, número, tipo, VDN e CC.
base_url, queryParam, calleeNos, beginLogDay, endLogDay, callTypes, vdn, ccId
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
querybasiccallinfo
POST
{{base_url}}/rest/cmsapp/v1/openapi/calldata/querybasiccallinfo
Consulta informações básicas de uma chamada por callId no CMS.
base_url, ccId, vdn, callId
Em uso/previsto no robô de telefonia
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
querydetailcallinfo
POST
{{base_url}}/rest/cmsapp/v1/openapi/calldata/querydetailcallinfo
Consulta informações detalhadas de uma chamada por callId no CMS.
base_url, ccId, vdn, callId
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
agentsinskill
POST
{{base_url}}/rest/cmsapp/v1/openapi/realindex/agent/agentsinskill
Lista agentes vinculados a uma skill/fila em tempo real.
base_url, queryParam, vdn, ccId, skillIds
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
queryCalls
POST
{{base_url}}/rest/cmsapp/v2/openapi/vdn/querycalls
Lista chamadas por VDN, período e direção. É o endpoint principal de descoberta de ligações.
base_url, ccId, vdn, beginDate, endDate, isCallIn
Em uso/previsto no robô de telefonia
Não filtra por operador; consultar por VDN, período e direção.
Tabela Completa de Endpoints Documentados
Foram consolidadas 83 funções/endpoints únicos a partir da collection Postman local, removendo duplicidades por método + URL e adicionando um endpoint detectado no código.
Módulo
Função
Método
Endpoint
Para que serve
Parâmetros-chave
Status
Cuidados
AppCube/CRM
Case 2.0 Create Case
POST
{{base_url}}/service/AICC__Case/1.0.0/openapi/case
Cria caso no AppCube/Case 2.0.
base_url, caseInfo, title, description, type, origin, dueDate, isAutoAssigned, priority, state, creatorId, contactPhone
Documentado, fora do fluxo atual de auditoria
Consulta/uso administrativo; validar permissão Huawei.
AppCube/CRM
Case 2.0 Query Case List
POST
{{base_url}}/service/AICC__Case/1.0.0/openapi/case/list
Lista casos no AppCube.
base_url, limit, start
Documentado, fora do fluxo atual de auditoria
Consulta/uso administrativo; validar permissão Huawei.
AppCube/CRM
Case 2.0 Modify a Case
POST
{{base_url}}/service/AICC__Case/1.0.0/openapi/case/modify
Altera caso no AppCube.
base_url, caseInfo, id, title, description, dueDate, ownerId, contactId, creatorId, contactPhone
Documentado, fora do fluxo atual de auditoria
Consulta/uso administrativo; validar permissão Huawei.
AppCube/CRM
Case 2.0 Query Case Details
GET
{{base_url}}/service/AICC__Case/1.0.0/openapi/case/{{case_id_example}}
Consulta detalhes de um caso pelo ID.
case_id_example, base_url, id
Documentado, fora do fluxo atual de auditoria
Consulta/uso administrativo; validar permissão Huawei.
AppCube/CRM
Case 2.0 Case Types
POST
{{base_url}}/service/AICC__Case/1.0.0/openapi/caseType/list
Lista tipos de caso no AppCube/Case 2.0.
base_url, start, limit
Documentado, fora do fluxo atual de auditoria
Consulta/uso administrativo; validar permissão Huawei.
AppCube/CRM
Customer Center Query Contacts
POST
{{base_url}}/service/AICC__Customer/1.0.0/customer/queryCustAllChannelContact
Consulta contatos de cliente em todos os canais.
base_url, start, limit
Documentado, fora do fluxo atual de auditoria
Consulta/uso administrativo; validar permissão Huawei.
Autenticação
2. applyToken
POST
{{base_url}}/apiaccess/ccmessaging/applyToken
Cria/aplica token de sessão para canal de mensagens.
base_url, userId, userName, channelId, locale
Documentado para canais digitais
Tratar credenciais e tokens como segredo.
Autenticação
1. tokenByAkSk Copy
POST
{{base_url}}/apigovernance/api/oauth/tokenByAkSk
Gera token OAuth/AccessToken a partir de app_key/app_secret. Base da autenticação direta atual.
base_url, app_key, app_secret
Em uso/previsto no robô de telefonia
Tratar credenciais e tokens como segredo.
Autenticação
AppCube Token
POST
{{base_url}}/baas/auth/v1.0/oauth2/token
Obtém token para AppCube/BaaS.
base_url
Documentado, fora do fluxo atual de auditoria
Tratar credenciais e tokens como segredo.
Autenticação
C3 getToken
POST
{{base_url}}/oifde/rest/api/gettoken
Obtém token do canal OIFDE/OIAP usando appKey/appSecret.
base_url, appKey, appSecret
Documentado/testável
Tratar credenciais e tokens como segredo.
Autenticação
C2 Authorization for Odfs
POST
{{teledata_lab_url}}/aicc/auth/c2AuthorizationOdfs.php
Proxy Teledata antigo para assinar/reencaminhar chamadas Huawei. Útil só como referência/legado.
teledata_lab_url, method, requestBody, sk, ak, requestHeader, replaceNewLine, url
Legado/proxy Teledata
Tratar credenciais e tokens como segredo.
Autenticação
C2 Authorization
POST
{{teledata_url}}/aicc/auth/c2Authorization.php
Proxy Teledata antigo para assinar/reencaminhar chamadas Huawei. Útil só como referência/legado.
teledata_url, ak, sk, url, method, requestHeader, requestBody, ccId, vdn, beginDate, endDate, isCallIn...
Legado/proxy Teledata
Tratar credenciais e tokens como segredo.
CC-Messaging
thirdPartyClient
POST
{{base_url}}/service-cloud/webclient/chat_client/js/thirdPartyClient.js?t={{timestamp}}
Função documentada na collection; validar contrato detalhado antes de uso produtivo.
timestamp, base_url
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
createCall V1
POST
{{base_url}}/apiaccess/CC-Management/v1/mobileAgent/createCall
Cria chamada pelo Mobile Agent.
base_url, caller, called, agentWorkNo
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Configuração/Gestão
queryPhone
POST
{{base_url}}/apiaccess/CC-Management/v1/mobileAgent/queryPhone
Consulta telefone/softphone do agente mobile.
base_url
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
queryAccessCodeList
POST
{{base_url}}/apiaccess/rest/cc-management/v1/accessCodeInfo/queryAccessCodeList
Lista códigos de acesso configurados.
base_url, accessCode, mediatypeId, description, limit, offset
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
Agent account query
POST
{{base_url}}/apiaccess/rest/cc-management/v1/agentAccount/query
Lista contas de agentes.
base_url, pageNum, pageSize
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
queryCalledRoute
POST
{{base_url}}/apiaccess/rest/cc-management/v1/calledRoute/queryCalledRoute
Consulta rotas/dispositivos associados a números chamados.
base_url, accessCode, extCode, devicetype, deviceDesc, mediatypeId, limit, offset
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
queryIVRFlowList
POST
{{base_url}}/apiaccess/rest/cc-management/v1/ivrFlow/queryIVRFlowList
Lista fluxos IVR configurados.
base_url, pageNum, pageSize
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
isOfflineAgent
POST
{{base_url}}/apiaccess/rest/cc-management/v1/offline/agent/isOfflineAgent
Verifica se o agente é offline/mobile.
base_url, workNo
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
MObile login
POST
{{base_url}}/apiaccess/rest/cc-management/v1/offline/agent/login
Login de agente offline/mobile.
base_url, phone, workNo
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
MObile logout
POST
{{base_url}}/apiaccess/rest/cc-management/v1/offline/agent/logout
Desloga agente.
base_url, workNo
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
satisfaction query
POST
{{base_url}}/apiaccess/rest/cc-management/v1/satisfaction/query
Consulta satisfação associada a uma chamada.
base_url, callId, beginTime, endTime
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
querySkills
POST
{{base_url}}/apiaccess/rest/cc-management/v1/skill/querySkills
Lista skills/filas configuradas no AICC.
base_url, limit, offset, name
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
queryCallInfoByCallId
POST
{{base_url}}/apiaccess/rest/workbench/v1/queryCallInfoByCallId
Consulta informações de chamada no workbench por callId, usuário, tenant e agente.
base_url, callId, userId, tenantId, agentId
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Configuração/Gestão
queryUserContactLimit
POST
{{base_url}}/apiaccess/rest/workbench/v1/queryUserContactLimit
Consulta limite/restrição de contato do usuário em uma chamada.
base_url, callId, userId, tenantId
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Geral
Post data
POST
{{base_url}}/info
Endpoint genérico de exemplo da collection; não é função Huawei operacional.
base_url, name
Exemplo genérico; ignorar
Consulta/uso administrativo; validar permissão Huawei.
Geral
Get data
GET
{{base_url}}/info?id=1
Endpoint genérico de exemplo da collection; não é função Huawei operacional.
base_url
Exemplo genérico; ignorar
Consulta/uso administrativo; validar permissão Huawei.
Geral
Update data
PUT
{{base_url}}/info?id=1
Endpoint genérico de exemplo da collection; não é função Huawei operacional.
base_url, name
Exemplo genérico; ignorar
Consulta/uso administrativo; validar permissão Huawei.
Geral
Delete data
DELETE
{{base_url}}/info?id=1
Endpoint genérico de exemplo da collection; não é função Huawei operacional.
base_url
Exemplo genérico; ignorar
Consulta/uso administrativo; validar permissão Huawei.
Gravações/Bilhetagem
Get bucket object
GET
{{base_url_obs}}/{{object_name_obs}}
Acesso direto ao Huawei OBS para listar ou baixar objetos/gravações.
object_name_obs, base_url_obs, prefix
Em uso/previsto no robô de telefonia
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
List objects
GET
{{base_url_obs}}/{{obs_object_parameters}}
Acesso direto ao Huawei OBS para listar ou baixar objetos/gravações.
obs_object_parameters, base_url_obs
Em uso/previsto no robô de telefonia
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
downloadAgentOprInfoFile
POST
{{base_url}}/CCFS/resource/ccfs/downloadAgentOprInfoFile
Consulta operações/eventos de agente em um período, como login, descanso, trabalho e chamadas.
base_url, request, version, msgBody, agentOprInfoFileName
Documentado/testável
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
downloadBillFile
POST
{{base_url}}/CCFS/resource/ccfs/downloadBillFile
Baixa arquivo ZIP de bilhetagem/CDR previamente gerado.
base_url, request, version, msgBody, billFileName
Documentado/testável
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
download IVR message
POST
{{base_url}}/CCFS/resource/ccfs/downloadIVRRecordFile
Baixa gravação/mensagem de IVR por fileName.
base_url, request, version, msgBody, fileName
Documentado/testável
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
download IVR audio
POST
{{base_url}}/CCFS/resource/ccfs/downloadOiapRecord
Baixa áudio de IVR/OIAP por fileName.
base_url, request, version, msgBody, fileName
Documentado/testável
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
downloadRecord
POST
{{base_url}}/CCFS/resource/ccfs/downloadRecord
Baixa gravação de voz diretamente por callId.
base_url, request, version, msgBody, callId, ccId
Em uso/previsto no robô de telefonia
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
downloadRecordFile
POST
{{base_url}}/CCFS/resource/ccfs/downloadRecordFile
Baixa gravação por caminho/nome de arquivo retornado pela Huawei/OBS.
base_url, request, version, msgBody, fileName
Em uso/previsto no robô de telefonia
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
getRecordFileUrlFromObs
POST
{{base_url}}/CCFS/resource/ccfs/getRecordFileUrlFromObs
Obtém URL pré-assinada/ponte para gravação no OBS.
base_url, callId, beginTime, endTime, version
Em uso/previsto no robô de telefonia
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Gravações/Bilhetagem
queryAgentOprInfoData
POST
{{base_url}}/CCFS/resource/ccfs/queryAgentOprInfoData
Consulta operações/eventos de agente em um período, como login, descanso, trabalho e chamadas.
base_url, request, version, msgBody, beginTime, endTime, callId, dataType, callBackURL
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Gravações/Bilhetagem
queryBillData
POST
{{base_url}}/CCFS/resource/ccfs/queryBillData
Solicita arquivo de bilhetagem/CDR via CC-FS para período e tipo de dado.
base_url, request, version, msgBody, beginTime, endTime, dataType, callBackURL
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Gravações/Bilhetagem
queryCallDetailRecord
POST
{{base_url}}/apiaccess/CC-Management/v1/mobileAgent/queryCallDetailRecord
Consulta histórico/detalhe de chamadas do Mobile Agent por período.
base_url, startTime, endTime, taskType, offset, limit
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Gravações/Bilhetagem
queryRecordHistory
POST
{{base_url}}/oifde/rest/api/queryRecordHistory
Consulta histórico de gravações no canal OIAP/OIFDE.
base_url, tenantId, authToken, userMobile, startTime
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Mensageria/Multimídia
querycontent
POST
{{base_url}}/rest/cmsapp/v1/openapi/multimedia/querycontent
Consulta conteúdo/mensagens multimídia por callId; mantido no cliente como best-effort.
callId, ccId, vdn
Detectado no código; validar contrato Huawei
Pode expor histórico de mensagem/conteúdo; usar com finalidade definida.
Mensageria/WhatsApp
7. downloadFileStream
POST
{{base_url}}/apiaccess/ccmessaging/downloadFileStream
Baixa arquivo de conversa/mensageria.
base_url, fileType, channel, fileId, multiMedia
Documentado para canais digitais
Pode baixar dados sensíveis de áudio/anexo; registrar finalidade e janela.
Mensageria/WhatsApp
8. get Satisfaction
POST
{{base_url}}/apiaccess/ccmessaging/getsatisfactionsurveymode
Consulta modo/formulário de pesquisa de satisfação.
base_url, language
Documentado para canais digitais
Pode enviar/consultar mensagens reais; cuidado com LGPD e ambiente.
Mensageria/WhatsApp
5. poll
GET
{{base_url}}/apiaccess/ccmessaging/poll?receiverId={{userId}}&channel=WEB
Busca mensagens/eventos pendentes do canal de mensagens.
userId, base_url
Documentado para canais digitais
Pode enviar/consultar mensagens reais; cuidado com LGPD e ambiente.
Mensageria/WhatsApp
12. query History Chat Messages
POST
{{base_url}}/apiaccess/ccmessaging/queryHistoryChatMessage
Consulta histórico de chat/mensageria por período, usuário e canal.
base_url, channelId, userId, limit, offset, startTime, endTime, channel
Documentado para canais digitais
Pode enviar/consultar mensagens reais; cuidado com LGPD e ambiente.
Mensageria/WhatsApp
9. save Satisfaction
POST
{{base_url}}/apiaccess/ccmessaging/saveSatisfaction
Grava avaliação de satisfação do atendimento.
base_url, channel, userId, evaluation, comment, channelConfigId, npsScore, fcrValue
Documentado para canais digitais
Pode enviar/consultar mensagens reais; cuidado com LGPD e ambiente.
Mensageria/WhatsApp
3. send connect
POST
{{base_url}}/apiaccess/ccmessaging/send
Envia evento de mensageria: conectar, chat, arquivo ou desconectar.
base_url, content, controlType, from, mediaType, senderNickname, sourceType, to, channel, userAgent, senderAvatar, transData...
Documentado para canais digitais
Pode enviar/consultar mensagens reais; cuidado com LGPD e ambiente.
Mensageria/WhatsApp
4.1. uploadFileStream (jpg)
POST
{{base_url}}/apiaccess/ccmessaging/uploadFileStream
Envia arquivo em base64 para o canal de mensagens.
base_url, fileType, channel, fileStream
Documentado para canais digitais
Pode enviar/consultar mensagens reais; cuidado com LGPD e ambiente.
Mensageria/WhatsApp
sendWhatsApp
POST
{{base_url}}/apiaccess/rest/ccmessaging/omni/1/advanced
Envio avançado/omnichannel, usado no exemplo de WhatsApp template.
base_url, bulkId, whatsApp, templateName, templateData, language, destinations, messageId, to, phoneNumber
Documentado para canais digitais
Pode enviar/consultar mensagens reais; cuidado com LGPD e ambiente.
Mensageria/WhatsApp
20. drop Email
POST
{{base_url}}/apiaccess/rest/ccmessaging/v1/emailchannel/dropMail
Descarta/encerra e-mail no canal de atendimento.
base_url, emailId
Documentado para canais digitais
Pode enviar/consultar mensagens reais; cuidado com LGPD e ambiente.
Mensageria/WhatsApp
InfoBip Message
POST
{{base_url}}/social/on/whatsapp/infobip/message/{tenantId}
Recebe/envia mensagem do adaptador WhatsApp/Infobip.
tenantId, base_url, results, from, to, integrationType, message, text, type, contact, name, price...
Documentado para canais digitais
Pode enviar/consultar mensagens reais; cuidado com LGPD e ambiente.
Operação de Agente
agentEvent (polling)
GET
{{base_url}}/agentgateway/resource/agentevent/{agentId}
Consulta eventos do agente por polling.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
setCallDataExIf
POST
{{base_url}}/agentgateway/resource/calldata/{agentId}/setcalldataex
Define dados extras associados à chamada.
agentId, base_url, callid, calldata, isDataEncoded
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
sendmessage
POST
{{base_url}}/agentgateway/resource/mediacall/{agentId}/sendmessage
Envia mensagem por chamada multimídia.
agentId, base_url, callid, userid, data, from\, to\, channel\, controlType\, mediaType\, messageCode\, content\...
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
onlineagent
PUT
{{base_url}}/agentgateway/resource/onlineagent/{agentId}
Loga/coloca agente online no Agent Gateway.
agentId, base_url, password, phonenum, status, releasephone, agenttype, autoenteridle
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
agentStatus
GET
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/agentstatus
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
auto answer
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/autoanswer/true
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
auto enter idle
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/autoenteridle/false
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
cancel busy
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/cancelbusy
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
cancel rest
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/cancelrest
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
cancel work
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/cancelwork
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
force logout
DELETE
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/forcelogout
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
heartbeat (push)
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/handshake
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
logout
DELETE
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/logout
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
rest
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/rest/{duration}/{reasonCode}
Loga/coloca agente online no Agent Gateway.
reasonCode, duration, agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
busy
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/saybusy
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
idle
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/sayfree
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
syncAgentInfo
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/syncagentinfo
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
update guid
PUT
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/updateGuid
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
work
POST
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/work
Loga/coloca agente online no Agent Gateway.
agentId, base_url
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Operação de Agente
callout
PUT
{{base_url}}/agentgateway/resource/voicecall/{agentId}/callout
Realiza chamada ativa a partir do agente.
agentId, base_url, caller, called
Operacional: altera estado/faz chamada
Usar só em ambiente autorizado; pode mudar estado de agente ou originar chamadas.
Qualidade/SQM
queryQualityItemResult
POST
{{base_url}}/apiaccess/CCSQM/rest/ccisqm/v1/qualityitem/queryQualityItemResult
Consulta resultado de item/avaliação de qualidade SQM.
base_url, qualityId
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
queryCallState
POST
{{base_url}}/apiaccess/CC-Management/v1/mobileAgent/queryCallState
Lista chamadas por VDN, período e direção. É o endpoint principal de descoberta de ligações.
base_url, callSerialNo
Em uso/previsto no robô de telefonia
Não filtra por operador; consultar por VDN, período e direção.
Telefonia/CMS
14.1 Querying Call Result Data
POST
{{base_url}}/apiaccess/rest/dataprocess/v1/openapp/queryCallManualDetailInfo
Consulta detalhes de ligações manuais por callId ou por janela. Pode trazer dados de chamada, agente e histórico.
base_url, subCcNo, vdn, callId, callerNo, calleeNo, beginDate, endDate, callType, mediaType
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
queryManualIndexesByCondition
POST
{{base_url}}/rest/cmsapp/v1/callinday/querymanualindexesbycondition
Consulta indicadores/índices de chamadas manuais por condição: período, número, tipo, VDN e CC.
base_url, queryParam, calleeNos, beginLogDay, endLogDay, callTypes, vdn, ccId
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
agentoprinfo
POST
{{base_url}}/rest/cmsapp/v1/openapi/agent/agentoprinfo
Consulta operações/eventos de agente em um período, como login, descanso, trabalho e chamadas.
base_url, currentAgentId, beginTime, endTime, ccId
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
querybasiccallinfo
POST
{{base_url}}/rest/cmsapp/v1/openapi/calldata/querybasiccallinfo
Consulta informações básicas de uma chamada por callId no CMS.
base_url, ccId, vdn, callId
Em uso/previsto no robô de telefonia
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
querydetailcallinfo
POST
{{base_url}}/rest/cmsapp/v1/openapi/calldata/querydetailcallinfo
Consulta informações detalhadas de uma chamada por callId no CMS.
base_url, ccId, vdn, callId
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
agentsinskill
POST
{{base_url}}/rest/cmsapp/v1/openapi/realindex/agent/agentsinskill
Lista agentes vinculados a uma skill/fila em tempo real.
base_url, queryParam, vdn, ccId, skillIds
Documentado/testável
Consulta/uso administrativo; validar permissão Huawei.
Telefonia/CMS
queryCalls
POST
{{base_url}}/rest/cmsapp/v2/openapi/vdn/querycalls
Lista chamadas por VDN, período e direção. É o endpoint principal de descoberta de ligações.
base_url, ccId, vdn, beginDate, endDate, isCallIn
Em uso/previsto no robô de telefonia
Não filtra por operador; consultar por VDN, período e direção.
Apêndice: Como Localizar no Postman
Use esta tabela para relacionar a função consolidada com o nome/pasta original na collection e ver um exemplo curto de payload.
Função
Endpoint
Nome/pasta na collection
Exemplo de payload resumido
Case 2.0 Create Case
{{base_url}}/service/AICC__Case/1.0.0/openapi/case
AppCube/Case 2.0 Create Case
{ "caseInfo": { "title": "test openapi", "description": "testOpenApi", "type": "cvmC000001OulZstCJLE", "origin": "Voice", "dueDate": "2025-09-27 10:00:00", "isAutoAssigned": true, "priority": "Low", "state": "Processing"...
Case 2.0 Query Case List
{{base_url}}/service/AICC__Case/1.0.0/openapi/case/list
AppCube/Case 2.0 Query Case List
{ "limit": 2, "start": 0 }
Case 2.0 Modify a Case
{{base_url}}/service/AICC__Case/1.0.0/openapi/case/modify
AppCube/Case 2.0 Modify a Case
{ "caseInfo":{ "id":"{{case_id_example}}", "title":"New title", "description":"New description", "ownerId":"10gg0000012IpiXMqxzk", "creatorId": "10gg000001JnmaIlNHma", "contactPhone": "5561983336490" } }
Case 2.0 Query Case Details
{{base_url}}/service/AICC__Case/1.0.0/openapi/case/{{case_id_example}}
AppCube/Case 2.0 Query Case Details
{ "id": "c6m8000001PdC82DJn9M" }
Case 2.0 Case Types
{{base_url}}/service/AICC__Case/1.0.0/openapi/caseType/list
AppCube/Case 2.0 Case Types
{ "start":0, "limit":5 }
Customer Center Query Contacts
{{base_url}}/service/AICC__Customer/1.0.0/customer/queryCustAllChannelContact
AppCube/Customer Center Query Contacts
{ "start":0, "limit":5 }
2. applyToken
{{base_url}}/apiaccess/ccmessaging/applyToken
CC-Messaging/2. applyToken
{ "userId":"{{userId}}", "userName":"Teledata", "channelId":"{{channelAgent}}", "locale":"en" }
1. tokenByAkSk Copy
{{base_url}}/apigovernance/api/oauth/tokenByAkSk
Query Call Result/1. tokenByAkSk Copy; Authorization/C1 tokenByAkSk; CC-Messaging/1. tokenByAkSk
{ "app_key":"{{app_key}}", "app_secret":"{{app_secret}}" }
AppCube Token
{{base_url}}/baas/auth/v1.0/oauth2/token
AppCube/AppCube Token
-
C3 getToken
{{base_url}}/oifde/rest/api/gettoken
Authorization/C3 getToken
{ "appKey": "{{X-TenantSpaceID}}", "appSecret": "{{app_secret_c3}}" }
C2 Authorization for Odfs
{{teledata_lab_url}}/aicc/auth/c2AuthorizationOdfs.php
Authorization/C2 Authorization for Odfs
{"method":"POST","requestBody":"{`queryParam`:{`vdn`:`1`,`ccId`:`1`,`skillIds`:`[1]`}}","sk":"jeSTGFuxTfRJU0zQPbRkcZQGiJdp2TUJXDny6QaizWfXejsSAZtFHXk37vZbAFdA","ak":"366EEA3DAE62A17ACBF9B0CD3FFA37B2E368E674E08C1BEEBC49F9...
C2 Authorization
{{teledata_url}}/aicc/auth/c2Authorization.php
Authorization/C2 Authorization
{ "ak":"{{app_key_c2}}", "sk":"{{app_secret_c2}}", "url":"https: "method":"POST", "requestHeader":"Content-Type:application/json; charset=UTF-8", "requestBody":{"ccId":1,"vdn":25,"beginDate":"1776193200000","endDate":"17...
thirdPartyClient
{{base_url}}/service-cloud/webclient/chat_client/js/thirdPartyClient.js?t={{timestamp}}
CC-Messaging/thirdPartyClient
-
createCall V1
{{base_url}}/apiaccess/CC-Management/v1/mobileAgent/createCall
Mobile/createCall V1; Mobile/createCall V3
{ "caller":"66660130", "called":"01129873835", "agentWorkNo": 133 }
queryPhone
{{base_url}}/apiaccess/CC-Management/v1/mobileAgent/queryPhone
Mobile/queryPhone
{}
queryAccessCodeList
{{base_url}}/apiaccess/rest/cc-management/v1/accessCodeInfo/queryAccessCodeList
CC-Management/queryAccessCodeList
{ "limit":10, "offset":0 }
Agent account query
{{base_url}}/apiaccess/rest/cc-management/v1/agentAccount/query
CC-Management/Agent account query
{ "pageNum":0, "pageSize":100 }
queryCalledRoute
{{base_url}}/apiaccess/rest/cc-management/v1/calledRoute/queryCalledRoute
CC-Management/queryCalledRoute
{ "devicetype": 3, "limit":10, "offset":0 }
queryIVRFlowList
{{base_url}}/apiaccess/rest/cc-management/v1/ivrFlow/queryIVRFlowList
CC-Management/queryIVRFlowList; CC-Management/get APIs; CC-Management/queryIVRFlowList Copy; CC-Management/queryIVRFlowList Copy 2
{ "pageNum":0, "pageSize":100 }
isOfflineAgent
{{base_url}}/apiaccess/rest/cc-management/v1/offline/agent/isOfflineAgent
Mobile/isOfflineAgent
{"workNo":133}
MObile login
{{base_url}}/apiaccess/rest/cc-management/v1/offline/agent/login
Mobile/MObile login
{"phone":"061983336490","workNo":133}
MObile logout
{{base_url}}/apiaccess/rest/cc-management/v1/offline/agent/logout
Mobile/MObile logout
{"workNo":133}
satisfaction query
{{base_url}}/apiaccess/rest/cc-management/v1/satisfaction/query
CC-Management/satisfaction query
{ "callId": "1751911543-17469007", "beginTime": 1751857199000, "endTime": 1751943599000 }
querySkills
{{base_url}}/apiaccess/rest/cc-management/v1/skill/querySkills
CC-Management/querySkills
{ "limit": "100", "offset": "0" }
queryCallInfoByCallId
{{base_url}}/apiaccess/rest/workbench/v1/queryCallInfoByCallId
CC-Management/queryCallInfoByCallId
{ "callId": "1764679535-460341", "userId": "1702036404230451215", "tenantId": "202310023207", "agentId": "133" }
queryUserContactLimit
{{base_url}}/apiaccess/rest/workbench/v1/queryUserContactLimit
CC-Management/queryUserContactLimit
{ "callId": "1764679535-460341", "tenantId": "{tenantId}" }
Post data
{{base_url}}/info
Post data
{ "name": "Add your name in the body" }
Get data
{{base_url}}/info?id=1
Get data
-
Update data
{{base_url}}/info?id=1
Update data
{ "name": "Add your name in the body" }
Delete data
{{base_url}}/info?id=1
Delete data
-
Get bucket object
{{base_url_obs}}/{{object_name_obs}}
OBS/Get bucket object
{"prefix": "ctrcd_day"}
List objects
{{base_url_obs}}/{{obs_object_parameters}}
OBS/List objects
-
downloadAgentOprInfoFile
{{base_url}}/CCFS/resource/ccfs/downloadAgentOprInfoFile
CC-FS/downloadAgentOprInfoFile
{"request":{"version":"2.0"},"msgBody":{"agentOprInfoFileName":"20241113_62e2f1a86b6349ebac41d8f3344f98e9.zip"}}
downloadBillFile
{{base_url}}/CCFS/resource/ccfs/downloadBillFile
CC-FS/downloadBillFile
{"request":{"version":"2.0"},"msgBody":{"billFileName":"20260414_a08a378a3aae43c1bd1f2a81092775ab.zip"}}
download IVR message
{{base_url}}/CCFS/resource/ccfs/downloadIVRRecordFile
CC-FS/download IVR message
{"request":{"version":"2.0"},"msgBody":{"fileName":"Y:/1/record/20241113/15544985183536967.wav"}}
download IVR audio
{{base_url}}/CCFS/resource/ccfs/downloadOiapRecord
CC-FS/download IVR audio
{"request":{"version":"2.0"},"msgBody":{"fileName":"Y:/IVR/7/voice/17/yEE2Lh2x_1738761075708.mp3"}}
downloadRecord
{{base_url}}/CCFS/resource/ccfs/downloadRecord
CC-FS/downloadRecord
{"request":{"version":"2.0"},"msgBody":{"callId":"1776135340-404299","ccId":1}}
downloadRecordFile
{{base_url}}/CCFS/resource/ccfs/downloadRecordFile
CC-FS/downloadRecordFile
{"request":{"version":"2.0"},"msgBody":{"fileName":"/10/1/record/1/20241018/133/1054597.wav"}}
getRecordFileUrlFromObs
{{base_url}}/CCFS/resource/ccfs/getRecordFileUrlFromObs
CC-FS/getRecordFileUrlFromObs
{"callId":"1776135340-404299","beginTime":"2026-04-13 00:00:00","endTime":"2026-04-13 23:59:59","version":"2.0"}
queryAgentOprInfoData
{{base_url}}/CCFS/resource/ccfs/queryAgentOprInfoData
CC-FS/queryAgentOprInfoData
{"request":{"version":"2.0"},"msgBody":{"beginTime":"2024-10-12 00:00:00","endTime":"2024-10-12 23:59:59","callId":"1728711899-525891","dataType":"record","callBackURL":"https:
queryBillData
{{base_url}}/CCFS/resource/ccfs/queryBillData
CC-FS/queryBillData
{"request":{"version":"2.0"},"msgBody":{"beginTime":"2026-02-09 00:00:00","endTime":"2026-02-09 23:59:59","dataType":"call","callBackURL":"https:
queryCallDetailRecord
{{base_url}}/apiaccess/CC-Management/v1/mobileAgent/queryCallDetailRecord
CC-Management/queryCallDetailRecord; Mobile/history
{ "startTime": "1764644400000", "endTime": "1764730740000", "taskType": "0", "offset": "0", "limit": "10" }
queryRecordHistory
{{base_url}}/oifde/rest/api/queryRecordHistory
OIAP/queryRecordHistory
{ "tenantId": "{{X-TenantSpaceID}}", "authToken": "{{access-token-c3}}", "userMobile": "524423361356", "startTime":1750388399 }
querycontent
{{base_url}}/rest/cmsapp/v1/openapi/multimedia/querycontent
backend/core/huawei_client.py
{"callId":"...", "ccId":1, "vdn":25}
7. downloadFileStream
{{base_url}}/apiaccess/ccmessaging/downloadFileStream
CC-Messaging/7. downloadFileStream
{ "fileType": "pdf", "channel": "WEB", "fileId": "local/202507091157-1e135982-d3a5-4010-ad47-a3e860f36010/AICC_CRIACAO_APP_EMAIL", "multiMedia":"multiMedia" }
8. get Satisfaction
{{base_url}}/apiaccess/ccmessaging/getsatisfactionsurveymode
CC-Messaging/8. get Satisfaction
{ "language": "pt_BR" }
5. poll
{{base_url}}/apiaccess/ccmessaging/poll?receiverId={{userId}}&channel=WEB
CC-Messaging/5. poll
-
12. query History Chat Messages
{{base_url}}/apiaccess/ccmessaging/queryHistoryChatMessage
CC-Messaging/12. query History Chat Messages
{ "channelId":"202509298231665897", "userId":"5511970962853", "limit":"100", "offset":"0", "startTime":"1774666800000", "endTime":"1774753200000", "channel":"WEB" }
9. save Satisfaction
{{base_url}}/apiaccess/ccmessaging/saveSatisfaction
CC-Messaging/9. save Satisfaction
{ "channel": "WEB", "userId": "{{userId}}", "evaluation": "4", "comment": "Satisfeito com o atendimento prestado por este usuário.", "channelConfigId": "{{channelAgent}}" }
3. send connect
{{base_url}}/apiaccess/ccmessaging/send
CC-Messaging/3. send connect; CC-Messaging/4. send chat; CC-Messaging/4.2 send file (jpg); CC-Messaging/4.2 send file (png); CC-Messaging/4.2 send file (bmp) (+2)
{ "content":"", "controlType":"CONNECT", "from":"{{userId}}", "mediaType":"TEXT", "senderNickname":"TLD", "sourceType":"CUSTOMER", "to":"{{channelAgent}}", "channel":"WEB", "userAgent":null, "senderAvatar":null, "transDa...
4.1. uploadFileStream (jpg)
{{base_url}}/apiaccess/ccmessaging/uploadFileStream
CC-Messaging/4.1. uploadFileStream (jpg); CC-Messaging/4.1. uploadFileStream (png); CC-Messaging/4.1. uploadFileStream (bmp); CC-Messaging/4.1. uploadFileStream (pdf)
{ "fileType": "jpg", "channel": "WEB", "fileStream":"<base64>" }
sendWhatsApp
{{base_url}}/apiaccess/rest/ccmessaging/omni/1/advanced
sendWhatsApp
{ "bulkId": "2853BC8B21D23F473AB9AE41B75F34FC18D322B91B01F60FAF206ACEBA9EF7BD", "whatsApp": { "templateName": "retomar", "templateData": [], "language": "pt_BR" }, "destinations": [ { "messageId": "46dbab11-f9cc-4d32-852...
20. drop Email
{{base_url}}/apiaccess/rest/ccmessaging/v1/emailchannel/dropMail
CC-Messaging/20. drop Email
{ "emailId":"1953109824684822530" }
InfoBip Message
{{base_url}}/social/on/whatsapp/infobip/message/{tenantId}
WhatsApp Adapter/InfoBip Message
{ "results": [ { "from": "5511983336490", "to": "551137778621", "integrationType": "WHATSAPP", "message": { "text": "Test", "type": "TEXT" }, "contact": { "name": "User Name" }, "price": { "pricePerMessage": 0.000000, "c...
agentEvent (polling)
{{base_url}}/agentgateway/resource/agentevent/{agentId}
CC-Gateway/agentEvent (polling)
{ }
setCallDataExIf
{{base_url}}/agentgateway/resource/calldata/{agentId}/setcalldataex
CC-Gateway/setCallDataExIf
{ "callid": "1456229294-1191", "calldata": "1233", "isDataEncoded": "true" }
sendmessage
{{base_url}}/agentgateway/resource/mediacall/{agentId}/sendmessage
CC-Gateway/sendmessage
{ "callid": "1751035653-16934628", "userid": "116", "data": "{\"from\":\"202310023207088446\",\"to\":\"caio.soares@teledatabrasil.com.br\",\"channel\":\"EMAIL\",\"controlType\":\"CHAT\",\"mediaType\":\"EMAIL\",\"messageC...
onlineagent
{{base_url}}/agentgateway/resource/onlineagent/{agentId}
CC-Gateway/onlineagent
{ "password": "222wsx@WSX", "phonenum": "66660113", "status": "5", "releasephone": "true", "agenttype": "4", "autoenteridle":"false" }
agentStatus
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/agentstatus
CC-Gateway/agentStatus
{ }
auto answer
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/autoanswer/true
CC-Gateway/auto answer
{ }
auto enter idle
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/autoenteridle/false
CC-Gateway/auto enter idle
{ }
cancel busy
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/cancelbusy
CC-Gateway/cancel busy
{ }
cancel rest
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/cancelrest
CC-Gateway/cancel rest
{ }
cancel work
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/cancelwork
CC-Gateway/cancel work
{ }
force logout
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/forcelogout
CC-Gateway/force logout
{ }
heartbeat (push)
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/handshake
CC-Gateway/heartbeat (push)
{ }
logout
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/logout
CC-Gateway/logout
{ }
rest
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/rest/{duration}/{reasonCode}
CC-Gateway/rest
{ }
busy
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/saybusy
CC-Gateway/busy
{ }
idle
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/sayfree
CC-Gateway/idle
{ }
syncAgentInfo
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/syncagentinfo
CC-Gateway/syncAgentInfo
{ }
update guid
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/updateGuid
CC-Gateway/update guid
{ }
work
{{base_url}}/agentgateway/resource/onlineagent/{agentId}/work
CC-Gateway/work
{ }
callout
{{base_url}}/agentgateway/resource/voicecall/{agentId}/callout
CC-Gateway/callout
{ "caller": "8621", "called": "061983336490" }
queryQualityItemResult
{{base_url}}/apiaccess/CCSQM/rest/ccisqm/v1/qualityitem/queryQualityItemResult
SQM/queryQualityItemResult
{ "qualityId": 16239231508327803347 }
queryCallState
{{base_url}}/apiaccess/CC-Management/v1/mobileAgent/queryCallState
CC-Management/queryCallState; Mobile/queryCallState
{ "callSerialNo": "176252373266232729378592674091" }
14.1 Querying Call Result Data
{{base_url}}/apiaccess/rest/dataprocess/v1/openapp/queryCallManualDetailInfo
Query Call Result/14.1 Querying Call Result Data; CC-Management/queryManualCallDetailInfo
{ "subCcNo": "0", "vdn": "25", "callId": "1764705427-466541" }
queryManualIndexesByCondition
{{base_url}}/rest/cmsapp/v1/callinday/querymanualindexesbycondition
CMS/queryManualIndexesByCondition
{"queryParam":{"calleeNos":["8621"],"beginLogDay":"2025-02-01","endLogDay":"2025-02-28","callTypes":[0],"vdn":1,"ccId":1}}
agentoprinfo
{{base_url}}/rest/cmsapp/v1/openapi/agent/agentoprinfo
CMS/agentoprinfo
{"currentAgentId":133,"beginTime":"2025-08-04 03:00:00","endTime":"2025-08-05 03:00:00","ccId":1}
querybasiccallinfo
{{base_url}}/rest/cmsapp/v1/openapi/calldata/querybasiccallinfo
CMS/querybasiccallinfo
{"ccId":1,"vdn":1,"callId":"1762523104-538062"}
querydetailcallinfo
{{base_url}}/rest/cmsapp/v1/openapi/calldata/querydetailcallinfo
CMS/querydetailcallinfo
{"ccId":1,"vdn":1,"callId":"1762523458-538100"}
agentsinskill
{{base_url}}/rest/cmsapp/v1/openapi/realindex/agent/agentsinskill
CMS/agentsinskill
{"queryParam":{"vdn":"1","ccId":"1","skillIds":"[1]"}}
queryCalls
{{base_url}}/rest/cmsapp/v2/openapi/vdn/querycalls
CMS/queryCalls; CMS/batchmultiskill
{"ccId":1,"vdn":25,"beginDate":"1776193200000","endDate":"1776196800000","isCallIn":"false"}
Fontes Locais Usadas
docs/integracoes/huawei/Huawei_AICC_BrazilSaaS-OPENTECH.postman_collection.json
backend/core/huawei_client.py
backend/core/huawei_sync.py
backend/core/huawei_discovery.py
docs/integracoes/huawei/AICC_25.300.1_CC-CMS Interface Reference (RESTful).pdf
docs/integracoes/huawei/AICC_25.300.1_CC-FS Interface Reference (RESTful).pdf
Observação: antes de executar endpoints operacionais em produção, confirme credenciais, tenant, ambiente, permissão Huawei e finalidade de tratamento de dados.
