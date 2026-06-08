# Documentacao tecnica - Huawei AICC

## Conteudo desta pasta

- `../../../docs/integracoes/huawei/Huawei_AICC_BrazilSaaS-OPENTECH.postman_collection.json`
  - collection oficial fornecida pela Teledata Brasil (OPENTECH) com todos os
    endpoints usados pelo sistema de auditoria. Serve como fonte da verdade
    quando `huawei_client.py` precisa ser ajustado.

## Como a collection se traduz no codigo

| Pasta na collection | Endpoint | Codigo no repo |
|---|---|---|
| CMS / queryCalls | `POST /rest/cmsapp/v2/openapi/vdn/querycalls` | `HuaweiAICCClient.buscar_historico_chamadas` |
| CMS / querybasiccallinfo | `POST /rest/cmsapp/v1/openapi/calldata/querybasiccallinfo` | `HuaweiAICCClient.consultar_detalhe_chamada` |
| CC-FS / getRecordFileUrlFromObs | `POST /CCFS/resource/ccfs/getRecordFileUrlFromObs` | `HuaweiAICCClient.obter_url_audio_obs` |
| CC-FS / downloadRecord | `POST /CCFS/resource/ccfs/downloadRecord` | `HuaweiAICCClient.baixar_gravacao_por_callid` |
| CC-FS / downloadRecordFile | `POST /CCFS/resource/ccfs/downloadRecordFile` | `HuaweiAICCClient.baixar_gravacao_por_filename` |
| Authorization / C2 Authorization | `POST https://opentech.teledatabrasil.com.br/aicc/auth/c2Authorization.php` | `HuaweiAICCClient._assinar_via_proxy` |

## Restricao de IP

A Huawei AICC (BrazilSaaS) exige que as chamadas saiam de um IP whitelisted
pela Teledata. Por isso o cliente opera em dois modos:

- `HUAWEI_AUTH_MODE=proxy` (padrao) - pede ao `c2Authorization.php` que assine
  a requisicao e devolva somente o header `Authorization`. O request final
  ainda precisa sair de um IP whitelisted. Para Cloud Run, sera necessario um
  proxy extra que *encaminhe* a chamada inteira a partir de um host Teledata.
- `HUAWEI_AUTH_MODE=direct` - assina localmente via HMAC-SHA256 (stdlib).
  So funciona em ambientes onde a Huawei ja tem o IP no whitelist.

## Credenciais no banco (`configuracoes`)

Chaves esperadas (strings). Preenchidas pela tela Telefonia no frontend:

| Chave | Descricao |
|---|---|
| `huawei_cms_url` | `https://brazilsaas.aicccloud.com:28443` |
| `huawei_fs_url` | `https://brazilsaas.aicccloud.com:28443` |
| `huawei_ccid` | geralmente `1` |
| `huawei_vdn` | `25` no ambiente da NSTECH |
| `huawei_ak` | C2 app_key (`app_key_c2` na collection) |
| `huawei_sk` | C2 app_secret (`app_secret_c2` na collection) |
| `huawei_app_key` | Apenas se usar OAuth direto (C1) |

As variaveis de ambiente `HUAWEI_*` sobrescrevem o banco em dev local.
