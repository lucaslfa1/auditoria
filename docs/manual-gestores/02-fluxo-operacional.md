# Fluxo Operacional

## Fluxo resumido

1. O audio entra no sistema.
2. A triagem tenta identificar setor, alerta e operador.
3. O sistema decide se o caso segue automaticamente ou se vai para revisao.
4. Casos elegiveis seguem para auditoria.
5. A auditoria analisa o caso e arquiva o resultado revisavel.
6. A auditoria pode ajustar transcricao, criterios, resumo e feedback enquanto o caso ainda nao aparece para o supervisor.
7. Quando a auditoria envia explicitamente, o caso entra na fila de supervisao.
8. O supervisor decide se aprova ou contesta.
9. Apenas casos contestados entram no modulo de revisao tecnica.
10. O resultado final aprovado fica registrado para consulta e dashboard.

## Separacao por modulo

Para efeito de fechamento por modulo, o fluxo deve ser lido em camadas:

- Modulo 1: triagem.
- Modulo 2: auditoria e entrega ao supervisor.
- Modulo 3: contestacao e revisao tecnica.
- Modulo 4: aprovacao final e dashboard.

### Fronteira formal do modulo 1

O modulo 1 da triagem deve ser considerado fechado quando:

- o audio entra corretamente;
- a classificacao e persistida com contrato estavel;
- o item recebe status coerente na fila;
- a correcao manual vira a versao oficial quando usada;
- o item fica corretamente entregue para auditoria ou corretamente retido na triagem.

O modulo 1 nao depende, para aceite, de:

- aprovacao do supervisor;
- contestacao;
- modulo de revisao tecnica;
- aparicao do caso no dashboard final.

## Como a triagem encaminha os casos

### Quando o caso segue

O caso segue quando a classificacao tem seguranca suficiente e nao ha impedimento operacional relevante.

Exemplos:
- setor identificado com seguranca;
- alerta identificado com seguranca;
- sem conflito estrutural importante;
- operador ainda elegivel para auditoria no mes.

### Quando o caso aguarda

O caso fica em triagem quando ha alguma incerteza relevante.

Exemplos:
- alerta nao identificado;
- setor nao identificado;
- confianca baixa;
- confianca muito baixa;
- conflito entre direcao, operador ou sinais da ligacao;
- erro tecnico na classificacao.

## Regra pratica para a operacao

- o que foi identificado corretamente segue;
- o que nao foi identificado com seguranca aguarda revisao;
- um caso incerto nao trava os demais;
- a automacao continua processando os outros itens elegiveis.

## Status operacionais da fila de triagem

### `pending`

Caso pendente de revisao operacional ou correcao.

### `auto_resolved`

Caso classificado com seguranca suficiente para seguir no fluxo.

### `reviewed`

Caso corrigido ou validado manualmente.

### `audited`

Caso que ja passou pela auditoria.

### `monthly_capped`

Caso bloqueado temporariamente pela cota mensal de auditoria do operador.

## Encadeamento depois da triagem

Depois que a triagem termina sua parte:

- itens `auto_resolved` e `reviewed` ficam elegiveis para auditoria;
- a automacao do modulo seguinte audita o caso e arquiva o resultado para revisao da auditoria;
- o caso so aparece para o supervisor depois do envio explicito pela auditoria;
- o supervisor decide se aprova ou contesta;
- apenas a contestacao leva o caso para o modulo tecnico de revisao.

## Arquivar antes de enviar ao supervisor

No modulo de auditoria, `Arquivar auditoria` salva o resultado em `awaiting_pair`, status oculto do painel do supervisor. O mesmo registro fica espelhado no modulo `Arquivos`, que e a etapa operacional para a auditoria revisar transcricao, criterios, resumo e feedback antes do envio.

As edicoes feitas em `Arquivos` atualizam a auditoria principal em `audits`; portanto, `Enviar ao supervisor` muda a auditoria arquivada para `pending_approval` e o supervisor visualiza exatamente a versao salva apos as correcoes.

## Como a cota mensal afeta o fluxo

O sistema trabalha com uma regra oficial:
- apenas 2 auditorias por operador por mes sao suficientes;
- ao atingir a cota mensal, novos casos daquele operador nao seguem para auditoria ate o proximo mes.

Impacto operacional:
- o caso nao trava a fila;
- ele nao fica aguardando aprovacao manual;
- ele e marcado de forma rastreavel e o processamento segue para os proximos itens.

## Correcao manual

Quando a classificacao inicial nao estiver correta, o usuario pode ajustar o setor e o alerta.

Hoje essa correcao:
- e editavel na interface;
- deixa de ser apenas local;
- fica persistida no backend;
- passa a valer para fila, automacao e auditoria.

## Quando o sistema responde "desconhecido"

O sistema foi ajustado para nao transmitir falsa certeza.

Por isso:
- quando nao conseguir identificar o alerta com seguranca, retorna alerta como `desconhecido`;
- quando nao conseguir identificar o setor com seguranca, retorna setor como `desconhecido`;
- esses casos continuam editaveis e revisaveis.
