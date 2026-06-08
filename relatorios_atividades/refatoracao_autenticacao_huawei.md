# Relatório Técnico: Refatoração da Autenticação Huawei AICC para Acesso Direto (OAuth 2.0)
**Data:** 27 de Abril de 2026
**Projeto:** Auditoria
**Diretório Base:** `C:\Users\lucas.afonso\projetos\auditoria`

---

## 1. Contexto e Objetivos
Dando continuidade à homologação do IP Estático `35.199.111.152` na *whitelist* da Huawei (comprovado via Prova de Conceito isolada no Cloud Run), este relatório detalha a refatoração definitiva do cliente de integração da telefonia (`huawei_client.py`).
O objetivo principal foi **desativar a dependência do Proxy C2 (Teledata)** e implementar nativamente o fluxo de autenticação direta `oauth_direct`, garantindo alta performance, segurança e alinhamento total com as especificações testadas via Postman.

---

## 2. Atividade Principal: Implementação do Fluxo `oauth_direct`

### 2.1. Arquitetura de Autenticação e Cache de Tokens
A classe `HuaweiAICCClient` foi profundamente reestruturada para suportar múltiplos modos de autenticação de forma transparente:
- **Novo Modo `oauth_direct` (Alias: `token`):** Substitui a lógica antiga de assinatura HMAC e proxy. O sistema agora faz uma requisição inicial POST para `tokenByAkSk` utilizando as credenciais diretas do AICC.
- **Gerenciamento de Estado (Cache):** Para evitar sobrecarga de requisições de autenticação e risco de *rate limiting* por parte da Huawei (Erro 429), foi implementado um mecanismo de cache em memória do `AccessToken`.
  - O token é armazenado com base no tempo de vida (campo `expiresIn`), que possui um *default* de 3300 segundos.
  - Foi introduzido um *buffer* de segurança de 60 segundos, garantindo que o cliente solicite proativamente um novo token antes do atual expirar.

### 2.2. Separação Estrita de Credenciais
Para mitigar os falsos-positivos de bloqueio (Erro 403) causados por colisão de credenciais (onde chaves do proxy Teledata eram enviadas indevidamente para a porta oficial da Huawei), o sistema de injeção de dependências foi atualizado:
- **Novas Variáveis Introduzidas:**
  - `HUAWEI_DIRECT_APP_KEY`
  - `HUAWEI_DIRECT_APP_SECRET`
  - `HUAWEI_TENANT_SPACE_ID`
- **Lógica de Fallback:** O código prioriza as chaves `DIRECT_APP_*`. Caso não existam, o sistema recorre às antigas `HUAWEI_APP_KEY`/`SECRET` para manter compatibilidade retroativa durante a transição.
- **Otimização de Base URL:** A `auth_base_url` agora é resolvida por precedência:
  1. *Override* explícito.
  2. Variável de ambiente (`HUAWEI_AUTH_BASE_URL` ou `HUAWEI_PORTAL_URL`).
  3. Derivação inteligente do `HUAWEI_CMS_URL`, onde a porta de dados (`:28443`) é automaticamente suprimida para construir a URL do portal de governança.

### 2.3. Formatação Canônica de Cabeçalhos (Headers)
Para respeitar estritamente o WAF e o API Gateway da Huawei, a construção de cabeçalhos no modo `oauth_direct` foi ajustada:
- A propriedade `Authorization` passou a receber o valor prefixado por `Bearer <token>`.
- O cabeçalho `X-APP-Key` teve sua grafia forçada (uppercase), conforme exigência não-documentada descoberta via *reverse engineering* da coleção Postman.
- Inclusão sistemática do `X-TenantSpaceID` (Ex: `202509298231`), crucial para roteamento multitenant no AICC.

---

## 3. Atividade Secundária: Resolução de Débitos Técnicos e Testes

### 3.1. Restauração e Expansão da Suíte de Testes
O ecossistema de testes unitários encontrava-se parcialmente degradado devido aos *commits* recentes da funcionalidade "Auditar Instantaneamente".
- **Fila de Revisão (`test_review_queue_contract.py`):** Foram corrigidos 2 testes classificados como *stale* (linhas 316 e 431). O erro decorria da ausência do *assert* para o novo status `awaiting_pair`, injetado recentemente.
- **Cobertura do Cliente Huawei (`test_huawei_client.py`):** Foram desenvolvidos 9 novos casos de teste dedicados à nova arquitetura, validando rigorosamente:
  - Operação dos aliases de autenticação (`token` vs `oauth_direct`).
  - Lógica de derivação e limpeza de portas do `auth_base_url`.
  - Resiliência do *fallback* de credenciais.
  - Validade do formato dos cabeçalhos (Bearer + Tenant).
  - Funcionamento algorítmico do Cache Hit e do ciclo de *Refetch* pós-expiração.

### 3.2. Resultado da Integração Contínua
A execução combinada das suítes de teste (Huawei Client, Huawei Sync, OBS Client e Fila de Revisão) resultou em **38 testes aprovados (38/38 PASSED)**, assegurando que as novas implementações não causaram regressões na cadeia de automação.
O arquivo `.env.example` e a documentação interna (`docs/huawei/README.md`) foram integralmente atualizados para refletir a nova topologia.

---

## 4. Plano de Ação: Implantação e Virada de Chave (Go-Live)
O código está pronto e maduro. A ativação do fluxo direto na nuvem depende estritamente das seguintes variáveis de ambiente na aba "Variables & Secrets" do **Google Cloud Run** (revisão `auditoria-nstech`):

```env
# Modo de Autenticação: Migração de Proxy para Acesso Direto
HUAWEI_AUTH_MODE=oauth_direct

# Chaves Oficiais (AICC OAuth)
HUAWEI_DIRECT_APP_KEY=<HUAWEI_DIRECT_APP_KEY>
HUAWEI_DIRECT_APP_SECRET=<HUAWEI_DIRECT_APP_SECRET>
HUAWEI_TENANT_SPACE_ID=202509298231
```
*(Nota de infraestrutura: Assim que o Cloud Run recarregar com as variáveis acima, o sistema descartará automaticamente o tráfego em direção ao script PHP da Teledata, passando a utilizar o IP `35.199.111.152` contra o portal nativo da Huawei).*