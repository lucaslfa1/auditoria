# Auto-descarte de `desconhecido` no modo automacao

## Resumo

Implementar o descarte automatico de itens `desconhecido` somente no modo automacao,
sem tabela dedicada de historico. O item sai da fila por `DELETE` real para liberar
reentrada futura via `input_hash`; a observabilidade fica no contador do ciclo e nos
logs da aplicacao.

## Mudancas

- `backend/core/automation.py`
  - Flag `AUTOMATION_DISCARD_UNKNOWN_ALERTS`, default ON.
  - Hook em `_audit_single_item` para descartar alerta ausente/`desconhecido`.
  - Contador `discarded`/`descartados` em `audit_all_pending`, sem incrementar
    `failed`/`blocked`.

- `backend/repositories/classification_review.py`
  - `descartar_item_automacao(...)` remove fila e `huawei_sync_logs` dentro da
    transacao.
  - Midia fisica e apagada somente depois do commit.
  - Nao insere em `automation_discards`.

- `backend/core/automation_engine.py`
  - Inclui `descartados` no resultado do ciclo.
  - Preserva `auditadas = completed`.

- Documentacao
  - Registrar que `automation_discards` nao e usado no fluxo atual. Se a tabela existir
    por deploy anterior, ela fica vazia/sem uso; nao criar migration de drop agora.

## Testes

- `tests/backend/test_automation_discard_unknown.py`
  - flag default ON/OFF;
  - repo descarta sem depender de tabela de log;
  - falha antes do commit nao apaga midia;
  - flag OFF preserva triagem manual;
  - setor ausente com alerta valido segue manual;
  - lote soma `discarded`/`descartados` sem falha;
  - ciclo expõe `descartados` sem `last_error`.

## Assumptions

- `cadastro` audita somente `ANTECEDENTES`.
- Sem Safe Smart Routing, timeout/deferred ou reprocessamento nesta entrega.
- Sem tabela/migration nova de descarte.
