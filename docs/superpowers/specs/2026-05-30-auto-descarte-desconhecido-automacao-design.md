# Auto-descarte de `desconhecido` no modo automacao

**Data:** 2026-05-30
**Status:** Implementado sem tabela de log dedicada

## Decisao atual

No modo automacao, quando a triagem chega na auditoria com alerta ausente ou
`alert_id = 'desconhecido'`, o item deve sair da fila por `DELETE` real para liberar
o `UNIQUE(input_hash)` e permitir reentrada por um download futuro.

Nao ha tabela operacional de descarte. A tabela `automation_discards` foi removida do
codigo/migrations apos revisao de produto, porque adicionava superficie de manutencao
sem acao operacional clara. Se ela existir no banco por deploy anterior, fica sem uso.
Nao criar migration de `DROP` nesta versao.

## Comportamento

- Flag `AUTOMATION_DISCARD_UNKNOWN_ALERTS`, default ON.
- Flag ON: `_audit_single_item` chama `descartar_item_automacao(...)` e retorna
  `{"status": "discarded_unknown_alert"}`.
- Flag OFF: comportamento legado, voltando para `needs_manual_triage`.
- Setor ausente com alerta valido nao e descartado; segue para triagem manual.
- `audit_all_pending` contabiliza `discarded`/`descartados` sem incrementar
  `failed` nem `blocked`.
- `completed` continua significando auditoria efetivamente gerada.

## Persistencia e rastreabilidade

O descarte remove apenas tombstones operacionais:

- `fila_revisao_classificacao` por `input_hash`;
- `huawei_sync_logs` por `huawei_call_id`, quando houver;
- midia fisica depois do commit do banco.

O rastro fica no resultado do ciclo (`discarded`/`descartados`) e no log da aplicacao,
com hash, arquivo, setor, operador, motivo e `call_id`. Nao ha consulta historica em
tabela propria.

## Cadastro

`cadastro` audita somente `ANTECEDENTES`. Descartes nesse setor nao devem ser lidos como
sinal para criar novos alertas auditados.

## Fora de escopo

- Safe Smart Routing, timeout/deferred e reprocessamento de itens atuais.
- Criar novos alertas para `cadastro`.
- Criar tabela/migration/drop para historico de descarte.
- Caminho manual/UI.
