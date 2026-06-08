# Modulo de Triagem

## Papel da triagem

A triagem e a porta de entrada operacional para classificacao dos audios.

Ela decide:
- qual setor parece mais aderente ao caso;
- qual alerta parece mais aderente ao caso;
- se a identificacao do operador ajuda a reforcar a decisao;
- se o caso pode seguir sozinho ou se deve aguardar revisao.

## Regras importantes ja formalizadas

### 1. Casos certos seguem; casos incertos aguardam

Esta e a regra central da triagem.

O sistema nao deve:
- travar toda a fila por um unico caso incerto;
- fingir certeza quando ela nao existe.

### 2. Baixa confianca gera revisao

Casos com baixa confianca ou confianca muito baixa agora sobem para revisao com prioridade adequada.

Em termos gerenciais, isso significa:
- menos risco de auditoria nascer em cima de classificacao errada;
- mais rastreabilidade para os casos em que a IA teve duvida real.

### 3. "Desconhecido" e melhor que chute

Quando o sistema nao consegue confirmar setor ou alerta com seguranca, ele retorna `desconhecido`.

Motivo:
- evita passar ao usuario a impressao de que a classificacao esta correta;
- preserva a honestidade operacional da triagem;
- facilita a revisao humana.

### 4. Correcao manual virou parte oficial do fluxo

Antes, a edicao na tela podia ficar apenas local.

Hoje, a correcao manual:
- altera a classificacao persistida;
- atualiza a fila;
- deixa o caso rastreavel como revisado;
- alinha o que a UI mostra com o que a automacao e a auditoria passam a enxergar.

## Regras de interpretacao de alerta

### Parada x Desvio

Quando houver confusao entre `parada` e `desvio`, a triagem passou a olhar a enfase da fala.

Regra pratica:
- se a ligacao enfatiza muito `parada`, o sistema tende a tratar como `parada`;
- se a ligacao enfatiza muito `desvio`, `rota` ou equivalente, o sistema tende a tratar como `desvio`.

### Alertas criticos tem prioridade sobre menores

A triagem agora considera uma hierarquia de alertas.

Alertas criticos formalizados:
- posicao em atraso ou perda de sinal;
- violacoes;
- desengates;
- bau.
- acionamento policial.

Exemplo operacional:
- se a ligacao fala fortemente de `painel violado`, isso tem prioridade sobre uma leitura secundaria de `parada` ou `desvio`;
- se a ligacao enfatiza `perda de sinal` ou `posicao em atraso`, isso sobe acima de alerta menor.
- se a ligacao enfatiza `policia`, `acionamento policial`, `patrulhamento`, `viatura` ou `PRF`, isso deve subir para o alerta policial do grupo operacional.

### Cadastro do operador tambem orienta a decisao

Foi formalizado um cuidado importante:
- operadores de distribuicao podem se apresentar verbalmente como `rastreamento`;
- isso nao deve puxar automaticamente o caso para outro setor se o cadastro do operador sustentar uma classificacao mais confiavel.

Regra pratica:
- quando o operador e identificado com seguranca e existe cadastro consistente, o cadastro tem prioridade sobre uma autodeclaracao generica da fala.

## O que a gestao ganha com isso

- menos classificacao errada silenciosa;
- menos auditoria em cima de caso mal enquadrado;
- mais confiabilidade na fila de revisao;
- mais clareza para medir produtividade real da triagem.
