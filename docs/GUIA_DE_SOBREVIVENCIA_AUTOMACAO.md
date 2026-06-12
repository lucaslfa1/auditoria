# 🚑 Guia de Sobrevivência da Automação

Este documento é um "manual de bolso" para resolver problemas rápidos quando o sistema de auditoria parecer travado ou quando ligações não estiverem aparecendo no painel. **Feito para salvar vidas na madrugada e antes de apresentações.**

---

## 1. O painel está vazio, a IA parou de trabalhar?

**Diagnóstico rápido:** 
Geralmente a IA não quebrou, o problema é que os *filtros de negócio* barraram a entrada das ligações (ex: ID do operador errado, ou o sistema acha que a direção da chamada é inválida).

**Como destravar as ligações presas (Protocolo de Resgate):**
Se você sabe que existem ligações que foram baixadas e deveriam ter sido auditadas, você pode forçar o sistema a colocá-las de volta na fila principal.

Abra o terminal na pasta do projeto e rode o script de resgate:
```bash
python rescue_v2.py
```
*(Este script puxa as chamadas paradas no status 'Prontas para Auditoria' e as injeta diretamente no cérebro da Inteligência Artificial)*

---

## 2. Como ver POR QUE as ligações estão sendo rejeitadas?

Criamos um relatório automático que varre o banco de dados e diz exatamente o motivo do funil estar bloqueando as chamadas.

Rode o comando:
```bash
python scripts/relatorio_bloqueios_huawei.py
```

**O que ele vai te mostrar:**
* Quantas ligações foram barradas por erro de Inbound/Outbound.
* Uma lista de nomes de **Operadores que estão sem o ID da Huawei preenchido** (se eles não têm ID, o robô os ignora completamente).

**Como resolver:**
Vá no painel de **Colaboradores** e garanta que o campo `ID Huawei` esteja preenchido corretamente com a matrícula numérica da telefonia.

---

## 3. O Servidor Local "Morreu" ou Deu Crash

Se você estiver rodando no seu computador e a tela ficar branca ou a API retornar erro:

1. Derrube tudo:
```bash
npm run stop
```
2. Inicie tudo do zero (limpo e em background):
```bash
npm run up
```

---

## 4. O Sistema em Produção (Nuvem) está desatualizado

Se houve alguma mudança ou reparo local e você precisa jogar isso para a URL oficial da nuvem imediatamente:

1. Salve o código no GitHub:
```bash
git add .
git commit -m "Atualizacao de emergencia"
git push
```
2. Dispare o Deploy para o Google Cloud:
```bash
npm run deploy
```
*Aguarde cerca de 3 a 4 minutos. Quando terminar, a nuvem já estará rodando a versão 100% corrigida.*

---

## 5. Dúvidas Frequentes

* **Desliguei o Download da Huawei (D-1), a IA para?**
  * **Não mais.** Agora a IA processa autonomamente o que você baixar de forma manual.
* **A ligação é de um "Setor de Risco". Por que sumiu?**
  * O sistema é programado para jogar fora ligações *Receptivas* (o cliente ligou pra cá) se o operador for de um Setor de Risco. Apenas as ativas (nstech ligou pro cliente) são auditadas nesses casos.

---
*Fique tranquilo, o coração da IA é sólido. Quase sempre os travamentos são apenas ligações barradas na porta de entrada por falta de dados do operador!*