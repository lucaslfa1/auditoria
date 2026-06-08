# Fluxo Auditoria, Supervisao e Revisao

Data de referencia: 2026-03-12

## Objetivo

Documentar o fluxo oficial da auditoria desde a triagem ate a publicacao final no painel, incluindo fila dupla por operador, supervisao, contestacao e revisao tecnica.

## Visao geral

1. A ligacao entra pela triagem ou pela auditoria direta.
2. A auditoria e executada e gera nota, resumo, criterios e transcricao.
3. O resultado nao vai direto para a Supervisao na primeira ocorrencia do operador.
4. A primeira auditoria do operador fica armazenada aguardando a segunda.
5. Quando o operador acumula duas auditorias abertas, as duas sao liberadas para a Supervisao.
6. O supervisor decide aprovar ou contestar.
7. Se aprovar, a auditoria entra no dashboard oficial e na base de nota do operador.
8. Se contestar, a auditoria sai do fluxo final e vai para o modulo Revisao.
9. A equipe de auditoria registra o veredito tecnico e a defesa tecnica.
10. Se a contestacao for negada, a auditoria vai para o dashboard oficial.
11. Se a contestacao for aceita, a auditoria fica fora do dashboard oficial.
12. O supervisor passa a enxergar o veredito final e a defesa tecnica.

## Etapa 1. Triagem

- O arquivo pode entrar pela classificacao inicial.
- Se a classificacao estiver segura, o fluxo segue para auditoria.
- Se a classificacao estiver com baixa confianca ou inconsistencia, o arquivo entra na fila tecnica de classificacao.
- Essa fila agora fica no modulo `Revisao`.

## Etapa 2. Auditoria

- A auditoria gera:
  - nota
  - nota maxima
  - resumo
  - criterios avaliados
  - transcricao
  - metadados do operador, setor e alerta
- O audio da auditoria fica salvo como evidencia.

## Etapa 3. Fila dupla por operador

- Regra de negocio: a Supervisao trabalha com no maximo duas auditorias abertas por operador.
- Comportamento:
  - 1 auditoria aberta do operador: fica em espera
  - 2 auditorias abertas do operador: ambas vao para a Supervisao
  - 3 ou mais: as excedentes continuam aguardando ate abrir vaga
- Quando uma auditoria sai do fluxo aberto por aprovacao, contestacao ou resolucao final, a fila do operador e reequilibrada automaticamente.

## Etapa 4. Supervisao

- O supervisor recebe apenas auditorias prontas para revisao.
- A tela de Supervisao deve servir para:
  - mostrar a nota ao operador
  - mostrar criterios avaliados
  - mostrar transcricao e trechos com timestamp
  - exportar Excel e PDF
  - aprovar ou contestar
- O supervisor nao publica contestacao no painel.
- O supervisor apenas envia a contestacao para analise tecnica.

## Etapa 5. Contestacao

- Quando o supervisor contesta:
  - a auditoria muda para `contestation_pending_review`
  - o motivo da contestacao fica registrado
  - a auditoria nao entra no dashboard oficial nesse momento
- O retorno final deixa de ser decisao do supervisor.
- O retorno final passa a ser decisao da equipe de auditoria no modulo `Revisao`.

## Etapa 6. Revisao tecnica

- O modulo `Revisao` e restrito a administradores ou equipe de auditoria.
- Ele concentra duas filas:
  - contestações de auditoria
  - fila tecnica de classificacao
- Na revisao de contestacao, a equipe registra:
  - veredito: `accepted` ou `rejected`
  - defesa tecnica
  - usuario que revisou
  - data da revisao

## Etapa 7. Veredito final

- Se a contestacao for `rejected`:
  - a nota original e mantida
  - a auditoria vai para `approved`
  - a auditoria entra no dashboard oficial
  - o supervisor ve que a contestacao foi negada
  - a defesa tecnica fica visivel

- Se a contestacao for `accepted`:
  - a contestacao e acolhida
  - a auditoria vai para `contestation_accepted`
  - a auditoria nao entra no dashboard oficial
  - o supervisor ve que a contestacao foi aceita
  - a defesa tecnica fica visivel

## Regras de publicacao no dashboard

- O dashboard oficial considera apenas auditorias com status `approved`.
- Nao entram no dashboard:
  - `awaiting_pair`
  - `pending_approval`
  - `contestation_pending_review`
  - `contestation_accepted`

## Status operacionais da auditoria

- `awaiting_pair`
  - primeira auditoria aguardando completar o par do operador
- `pending_approval`
  - auditoria liberada para decisao do supervisor
- `approved`
  - auditoria oficial, publicada no painel
- `contestation_pending_review`
  - contestacao enviada pelo supervisor e aguardando revisao tecnica
- `contestation_accepted`
  - contestacao aceita pela auditoria; registro fica fora do painel oficial

## Responsabilidade por perfil

- Auditoria:
  - executa a auditoria
  - mantem o criterio tecnico
  - decide o veredito final de contestacao

- Supervisor:
  - revisa o caso da propria equipe
  - aprova quando concorda
  - contesta quando discorda
  - recebe o retorno final com defesa tecnica

- Dashboard:
  - mostra apenas o consolidado oficial
  - nao deve ser usado como fila tecnica

## Modulos do sistema

- `Auditoria`
  - gera o resultado e envia para a fila por operador
- `Supervisao`
  - mostra as auditorias abertas para aprovacao ou contestacao
- `Revisao`
  - centraliza contestacoes tecnicas e fila de classificacao
- `Painel`
  - mostra somente indicadores oficiais consolidados

## Observacoes de produto

- O modulo `Revisao` substitui o uso da fila de revisao da classificacao dentro do dashboard.
- A contestacao nao deve mais ser tratada como fim do fluxo.
- O supervisor nao da o veredito final da contestacao.
- A defesa tecnica precisa ficar registrada para rastreabilidade.

## Logs relacionados

- `05-revisoes/LOG_FILA_AUDITORIA_DUPLA_2026-03-12.md`
- `05-revisoes/LOG_MODULO_REVISAO_2026-03-12.md`
- `05-revisoes/LOG_SUPERVISAO_TRANSCRICAO_2026-03-12.md`
- `05-revisoes/LOG_STORAGE_AUDIO_AUDITORIA_2026-03-12.md`
