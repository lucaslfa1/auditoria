# Regras de Negocio para Gestao

## Regra 1: cota mensal por operador

A regra oficial vigente e:
- apenas 2 auditorias por operador por mes sao suficientes;
- ao atingir 2 auditorias no mes, o operador nao deve receber novas auditorias ate o proximo mes.

Efeito pratico:
- o sistema marca o caso como bloqueado por cota mensal;
- esse caso nao segue para auditoria naquele periodo;
- os demais casos continuam normalmente.

## Regra 2: a fila precisa ser rastreavel

Todo caso da triagem precisa ter:
- status compreensivel;
- motivo de revisao quando houver;
- rastreabilidade de alteracao manual;
- rastreabilidade do que ja foi auditado.

## Regra 3: incerteza precisa ser explicitada

O sistema nao deve transformar duvida em falsa certeza.

Por isso:
- setor nao confirmado deve aparecer como `desconhecido`;
- alerta nao confirmado deve aparecer como `desconhecido`;
- caso incerto deve ir para revisao, nao para resolucao silenciosa.

## Regra 4: alertas criticos dominam alertas menores

Quando houver sinais concorrentes na ligacao, alertas criticos devem prevalecer.

Alertas criticos priorizados hoje:
- posicao em atraso ou perda de sinal;
- violacoes;
- desengates;
- bau.
- acionamento policial.

## Regra 5: a fila nao pode parar por um unico caso

O fluxo operacional precisa seguir processando os casos elegiveis.

Isso significa:
- um caso pendente nao trava os demais;
- um operador fora de cota nao trava os demais;
- um caso ja auditado nao trava os demais.

## Regra 6: correcao manual precisa valer de verdade

Se o usuario corrige setor ou alerta:
- a correcao precisa persistir;
- a fila precisa refletir a nova classificacao;
- a auditoria precisa usar a versao corrigida.

## Indicadores gerenciais recomendados

Para acompanhar a operacao, a gestao deve observar pelo menos:
- volume de casos em `pending`;
- volume de casos em `auto_resolved`;
- volume de casos em `monthly_capped`;
- percentual de casos corrigidos manualmente;
- percentual de casos com `desconhecido`;
- tempo medio entre triagem e auditoria;
- distribuicao de motivos de revisao.

## Leitura gerencial dos status

- `pending`: fila de revisao ou classificacao ainda nao segura
- `auto_resolved`: caso apto a seguir no fluxo
- `reviewed`: caso corrigido ou validado manualmente
- `audited`: ciclo concluido
- `monthly_capped`: caso bloqueado por regra de amostragem mensal
