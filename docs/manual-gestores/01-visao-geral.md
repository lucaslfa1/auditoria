# Visao Geral do Sistema

## Finalidade

O sistema apoia a operacao de auditoria de ligacoes e eventos, com foco em:
- classificacao inicial dos casos;
- encaminhamento para auditoria;
- revisao operacional de casos incertos;
- rastreabilidade do que foi auditado;
- exportacao de resultados para acompanhamento gerencial.

## O que o sistema faz

- recebe arquivos de audio para triagem e auditoria;
- identifica setor, alerta e operador quando ha evidencia suficiente;
- separa casos seguros de casos que precisam de revisao;
- executa auditoria com base em criterios por setor e alerta;
- registra o historico do processamento;
- permite exportacao e consulta para acompanhamento.

## Principais blocos operacionais

### 1. Triagem

Faz a leitura inicial do audio e tenta responder:
- qual e o setor;
- qual e o alerta;
- qual e o operador;
- se o caso pode seguir direto ou precisa de revisao.

### 2. Revisao operacional

Recebe casos com incerteza, baixa confianca ou conflito de classificacao.

O objetivo dessa etapa e impedir que um caso siga para auditoria com classificacao incorreta.

### 3. Auditoria

Avalia o atendimento ou evento com base nos criterios configurados para o alerta e o setor corretos.

### 4. Automacao

Percorre os casos elegiveis, respeita as regras de negocio e segue com a auditoria sem depender de aprovacao manual caso o item ja esteja regular.

### 5. Relatorios e exportacoes

Organiza os resultados para consulta, controle e uso gerencial.

## Perfis de interesse para gestao

- gestor: acompanha volume, fila, cobertura e consistencia operacional;
- supervisor: atua sobre revisao, auditoria e validacao;
- operacao: usa a triagem e acompanha casos pendentes.

## O que ja esta revisado com mais profundidade

No momento, o modulo revisado formalmente e o de triagem. Isso inclui:
- contrato da fila;
- passagem da triagem para a automacao;
- politica de revisao por confianca;
- correcao manual persistida;
- regras de desempate entre alertas;
- cobertura de testes do fluxo principal.
