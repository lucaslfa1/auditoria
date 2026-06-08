# Manifesto de Infraestrutura de Rede - Integração Huawei

**Prioridade Máxima: Não alterar estas configurações sem revisão de rede.**

## Contexto
Para que o sistema Auditoria consiga se comunicar com a Huawei AICC, é obrigatório que o IP de saída da requisição esteja na **Whitelist** da Huawei/Teledata. A whitelist hoje contempla múltiplos IPs validados, cobrindo tanto execução em Cloud Run (produção) quanto execução local (desenvolvimento e operação a partir da rede da empresa).

## IPs Validados na Whitelist Huawei/Teledata

A Huawei abriu o acesso de forma mais abrangente ou estamos rodando sob um IP dinâmico liberado. Os IPs fixos dedicados do GCP foram **deletados** para redução de custo.

| IP | Origem | Região / Uso | Status |
|----|--------|--------------|--------|
| `35.199.111.152` | GCP Cloud NAT | `southamerica-east1` (São Paulo) | **DELETADO** (Economia de custo, tráfego Cloud Run vai direto para internet) |
| `34.171.63.68`   | GCP Cloud NAT | `us-central1` (Iowa) | **DELETADO** (Máquina e IP destruídos) |
| `189.38.107.13`  | Rede NSTECH (empresa) | Operação local / VPN corporativa | Ativo — execução manual e maquinas de operadores |

> Observação: A infraestrutura em produção hoje utiliza egress direto (`private-ranges-only`), bypassando a necessidade de NAT e IP fixo.

## Recursos de Rede Vinculados (GCP — produção)
- **TODA INFRAESTRUTURA DE REDE FIXA (NAT, Router, VPC Connector) FOI DELETADA** em 13/05/2026 para atingir a meta de R$100/mês.
- O Cloud Run opera de forma 100% serverless, utilizando Egress `private-ranges-only`.

## Configuração do Sistema

### Cloud Run (produção)
- **VPC Egress:** `private-ranges-only` (Tráfego de internet sai de forma direta com IPs dinâmicos do Google).
- Modo de autenticação atual em produção: configurado pelo banco (tabela `configuracoes`, chave `huawei_auth_mode`).
  - Valor em uso desde 26/04/2026: `proxy` (Teledata em `lab.teledatabrasil.com.br/aicc/auth/c2Authorization.php`), com `huawei_proxy_ip = 163.176.162.83`.
  - Modo `direct` (HMAC-SHA256 local) é suportado pelo cliente e pode ser ativado quando alinharmos com a Huawei.
- `ENABLE_HUAWEI_SYNC`: `true`.

### Execução Local (rede NSTECH)
- Pode rodar sem NAT desde que a máquina esteja com IP de saída `189.38.107.13` (rede da empresa ou VPN corporativa).
- Requer `.env` em `backend/` com `DATABASE_URL` apontando para o Neon PostgreSQL e `ENABLE_HUAWEI_SYNC=true`.
- Disparo manual: `python backend/scripts/run_huawei_sync.py --horas 48`.

## Variáveis e Configuração no Banco
A maior parte das credenciais Huawei vive em `configuracoes` no Postgres (chaves prefixadas `huawei_*`), com fallback para variáveis de ambiente. Atualizações via UI de Configuração (admin) ou via SQL direto. Chaves relevantes:
- `huawei_auth_mode`, `huawei_proxy_ip`, `huawei_proxy_url`
- `huawei_cms_url`, `huawei_fs_url`, `huawei_portal_url`
- `huawei_ccid`, `huawei_vdn`
- `huawei_ak`, `huawei_sk`, `huawei_app_key`, `huawei_app_secret`
- `huawei_obs_ak`, `huawei_obs_sk`, `huawei_obs_bucket`, `huawei_obs_endpoint`
- `huawei_horas_retroativas`

## Endpoints Externos Utilizados
- Auth proxy (Teledata): `https://lab.teledatabrasil.com.br/aicc/auth/c2Authorization.php`
- Huawei AICC SaaS: `https://brazilsaas.aicccloud.com:28443`
- OBS Huawei (gravações): `https://<bucket>.obs.sa-brazil-1.myhuaweicloud.com`

---
*Atualizado em: 02 de Maio de 2026 — revalidação da whitelist (3 IPs ativos) e alinhamento com modo `proxy` em uso.*
