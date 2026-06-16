# Relatorio - Restricao de IP Huawei AICC e Caminho para Producao

**Data:** 2026-04-19
**Autor:** Lucas Afonso
**Destinatario:** Lucas Afonso + TI Teledata Brasil (OPENTECH)
**Contexto:** versao 1.3.52 - reconciliacao do cliente Huawei com a collection Postman oficial

---

## 1. O problema em uma frase

A plataforma **Huawei AICC BrazilSaaS** (`brazilsaas.aicccloud.com:28443`)
so aceita requisicoes vindas de **IPs que a Teledata Brasil cadastrou no
whitelist** da conta OPENTECH. Isso foi confirmado por e-mail pela propria
Teledata. Como o backend de auditoria roda (ou vai rodar) no **Google Cloud
Run**, cuja faixa de IP eh dinamica e publica, as chamadas serao bloqueadas
no firewall da Huawei antes mesmo de chegar na API.

## 2. O que isso implica na pratica

Hoje, depois das correcoes da versao 1.3.52, o codigo ja sabe assinar as
chamadas de dois jeitos:

| Modo | Como funciona | IP que precisa estar whitelisted |
|---|---|---|
| `HUAWEI_AUTH_MODE=direct` | Calcula a assinatura HMAC-SHA256 localmente | O IP do servidor que roda o backend |
| `HUAWEI_AUTH_MODE=proxy` | Pede ao `c2Authorization.php` da Teledata para assinar, e usa o token retornado | O IP do servidor que roda o backend (o proxy **so assina**, nao **encaminha**) |

**Ponto critico:** nos dois modos, a requisicao HTTP final (`POST
brazilsaas.aicccloud.com:28443/...`) **ainda sai do nosso servidor**. O
`c2Authorization.php` ajuda a gerar o header `Authorization` sem expor AK/SK
no codigo, mas nao resolve o problema do IP de origem.

Ou seja, hoje o sistema funciona:
- Rodando na sua maquina (IP da Teledata): **SIM**
- Rodando no Cloud Run: **NAO** (firewall Huawei bloqueia)

## 3. Opcoes para desbloquear o Cloud Run

### Opcao A - Whitelist da faixa do Cloud Run (pedido pra Teledata)

**O que pedir:**
> "Podem incluir no whitelist da nossa conta Huawei AICC a faixa de IPs do
> Google Cloud Run (regiao `southamerica-east1`)?"

**Problemas:**
- O Cloud Run nao tem IP fixo. A faixa do GCP `southamerica-east1` tem
  centenas de blocos CIDR que mudam ao longo do tempo.
- A Huawei normalmente exige IPs especificos, nao faixas inteiras.
- Mesmo que seja aceito, da exposicao grande demais.

**Veredito:** provavelmente nao vai ser aceito. Vale como pergunta inicial
so para confirmar que nao eh viavel.

### Opcao B - NAT estatico no GCP (caminho recomendado)

Em vez de whitelistar a faixa toda, saimos do Cloud Run **atraves de um IP
unico e estatico** configurado com Cloud NAT + Serverless VPC Access.

**Passo a passo (infra Google Cloud):**
1. Criar uma **VPC** no projeto GCP.
2. Reservar um **IP externo estatico** (1 IP so).
3. Criar um **Cloud Router** + **Cloud NAT** que use esse IP estatico como
   endereco de saida.
4. Criar um **Serverless VPC Access Connector** para o Cloud Run falar com
   a VPC.
5. No deploy do servico Cloud Run, adicionar `--vpc-connector=<connector>`
   e `--vpc-egress=all-traffic`.
6. Mandar o IP estatico para a Teledata whitelistar uma unica vez.

**Custo aproximado:** ~US$ 15/mes (Cloud NAT) + ~US$ 8/mes (IP reservado)
~= US$ 23/mes.

**Veredito:** eh o caminho **padrao de mercado** para chamar API
IP-restrita a partir de Cloud Run. Recomendo seguir por aqui.

**O que pedir para a Teledata:**
> "Vamos sair do Cloud Run por um IP estatico. Posso mandar o IP assim que
> provisionar no GCP. Podem cadastrar esse IP no whitelist da nossa conta
> Huawei AICC?"

### Opcao C - Proxy de encaminhamento hospedado na Teledata

Em vez de so assinar, a Teledata exporia **um segundo endpoint** que recebe
a requisicao inteira da gente e a **encaminha** para a Huawei, devolvendo a
resposta. Algo como:

```
POST https://opentech.teledatabrasil.com.br/aicc/proxy/forward
{
  "ak": "...",
  "sk": "...",
  "url": "https://brazilsaas.aicccloud.com:28443/rest/cmsapp/v2/.../querycalls",
  "method": "POST",
  "requestBody": {...},
  "requestHeader": "Content-Type: application/json; charset=UTF-8"
}
```

A resposta viria com o JSON (ou binario, no caso do audio) que a Huawei
devolveu.

**Vantagens:**
- Nao precisamos de NAT estatico no GCP (-US$ 23/mes).
- A Teledata centraliza auditoria/observabilidade das chamadas.
- Ja temos o `c2Authorization.php` funcionando; basta ele ganhar uma irma
  que tambem encaminhe.

**Desvantagens:**
- Depende de eles quererem/poderem desenvolver.
- Latencia extra (dois hops em vez de um).
- Para download de audio (pode passar de 10MB), precisa de timeout
  generoso.

**O que pedir para a Teledata:**
> "O `c2Authorization.php` resolve a assinatura, mas nossa aplicacao roda
> em Cloud Run com IP dinamico, entao o request final pra
> `brazilsaas.aicccloud.com:28443` ainda cai no bloqueio de IP. Voces
> conseguiriam expor um endpoint na mesma infra que **encaminhe** a
> requisicao completa para a Huawei (recebe o request da gente, repassa, e
> devolve a resposta)? O ideal seria preservar o content-type binario para
> download de audio."

### Opcao D - Servidor intermediario nosso

Subir uma **VM pequena** num provedor com IP fixo (Digital Ocean, Hetzner,
uma instancia Compute Engine com IP estatico, ou a propria infra da
NSTECH) e rodar um proxy HTTP simples la. Cloud Run chama essa VM, ela
chama a Huawei.

**Custo aproximado:** US$ 5-10/mes (Digital Ocean 1 vCPU) ou US$ 20/mes
(Compute Engine e2-micro com IP estatico).

**Veredito:** funciona, mas adiciona uma peca de infra que precisa de
monitoramento proprio. Eh a opcao B disfarcada, so que fora do GCP.

## 4. Recomendacao

**Minha recomendacao e Opcao B (Cloud NAT com IP estatico).** Motivos:

1. Nao depende da Teledata construir nada novo.
2. Usa componente nativo do GCP, sem pagar a mais por VM avulsa.
3. Resolve o problema para **qualquer** API IP-restrita que a gente venha
   a integrar no futuro (nao so Huawei).
4. O IP estatico eh nosso, entao auditoria/rollback ficam mais faceis.

**Plano de acao sugerido, em ordem:**

1. Tentar Opcao A primeiro (email rapido): "da pra whitelistar a faixa do
   Cloud Run sa-east1?". Vamos receber "nao" em 1 dia, mas eh registro.
2. Provisionar Opcao B no GCP (1-2h de trabalho de infra).
3. Enviar o IP estatico para a Teledata whitelistar.
4. Virar `ENABLE_HUAWEI_SYNC=true` no Cloud Run.
5. Rodar `POST /api/telefonia/sync/manual` como admin e validar end-to-end
   com 1 operador de teste.

## 5. O que voce (Lucas) precisa fazer agora

1. **Mandar e-mail pra Teledata com os dois pedidos combinados** (texto
   sugerido abaixo). Opcoes A e B primeiro, C como fallback se B nao der.
2. **Confirmar comigo se a Opcao B (Cloud NAT) pode ser executada** - eu
   preciso de acesso (ou que voce peca pro Gemini CLI executar) para os
   comandos `gcloud compute networks create`, `gcloud compute routers nats
   create` e `gcloud run services update --vpc-connector`.
3. **Enquanto nenhuma das duas esta resolvida**, manter
   `ENABLE_HUAWEI_SYNC=false` no Cloud Run. O endpoint continua respondendo
   com o stub amigavel, sem quebrar nada.

### Texto sugerido para o e-mail da Teledata

> Ola, tudo bem?
>
> Seguindo a confirmacao de que o ambiente Huawei AICC BrazilSaaS opera
> com restricao de IP, queria alinhar o caminho pra nossa aplicacao (que
> roda no Google Cloud Run) conseguir chamar a API em producao. Listei
> tres opcoes em ordem de preferencia:
>
> 1. **Whitelist da faixa do Cloud Run `southamerica-east1`** - aceitavel
>    do lado de voces? (imagino que nao, mas pergunto para registro).
>
> 2. **Whitelist de um IP estatico unico** - vamos provisionar um Cloud
>    NAT com IP reservado no GCP e usar ele como saida. Mando o IP assim
>    que estiver pronto.
>
> 3. **Endpoint de encaminhamento na infra de voces** - ja usamos o
>    `c2Authorization.php` para assinar as requests. Caso as opcoes
>    anteriores nao sejam viaveis, voces conseguiriam expor tambem um
>    endpoint que receba o request completo da gente e encaminhe para a
>    Huawei, devolvendo a resposta? Serviria para `/querycalls`,
>    `/downloadRecord` e `/getRecordFileUrlFromObs`.
>
> Qualquer uma das tres destrava nosso piloto de automacao da auditoria
> com as ligacoes Huawei.
>
> Abracos,
> Lucas

---

## 6. Estado atual do codigo (para referencia da TI)

Ja foi entregue na versao 1.3.52 o suficiente para que, assim que o IP
for resolvido, baste virar a flag:

- `HUAWEI_AUTH_MODE=proxy` (padrao): usa `c2Authorization.php` para assinar
  sem expor AK/SK no binario do Cloud Run.
- `HUAWEI_PROXY_URL=https://opentech.teledatabrasil.com.br/aicc/auth/c2Authorization.php`
- Endpoints usados (alinhados 1:1 com a collection Postman oficial):
  - `POST /rest/cmsapp/v2/openapi/vdn/querycalls`
  - `POST /CCFS/resource/ccfs/downloadRecord` (preferido)
  - `POST /CCFS/resource/ccfs/getRecordFileUrlFromObs` (fallback)
  - `POST /CCFS/resource/ccfs/downloadRecordFile`
- Idempotencia garantida por `huawei_sync_logs(call_id UNIQUE)` - ligacao
  baixada nao eh reprocessada.
- Cota mensal de auditorias respeitada (`MAX_INTERACOES_POR_OPERADOR=2`).
- Collection Postman versionada em `backend/docs/huawei/` para novos
  agentes nao precisarem sair do repo.

---

## 7. Proximo ponto a decidir depois do IP

- Construir `backend/automation_engine.py` (o "robo de madrugada" do Plano
  de Automacao Hibrida - ja descrito em `PLANO_AUTOMACAO_HIBRIDA.md`).
- Construir a tela `src/features/automacao/` com ON/OFF + log ao vivo.
- Fechar o loop: sync Huawei -> Triagem -> Auditoria -> `awaiting_pair`.
