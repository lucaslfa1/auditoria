# Module 2 Kickoff - Auditoria e Entrega ao Supervisor

Data de referencia: 2026-04-09

## Estado consolidado

- Modulo 1 da Triagem foi tratado como fechado.
- A fronteira oficial do Modulo 1 ficou documentada no manual e no review da triagem.
- O fechamento foi registrado em `logs/versions/1.3.44.md`.

## O que ficou fechado no Modulo 1

- upload e classificacao;
- persistencia da fila de triagem;
- contrato de status da fila;
- correcao manual persistida e autoritativa;
- duplicidade e reprocessamento;
- storage do audio classificado;
- regra de `monthly_capped`;
- entrega correta ate a fronteira da auditoria.

## Correcao estrutural relevante herdada

- `sincronizar_fila_revisao_classificacao` nao pode mais sobrescrever itens protegidos em `reviewed`, `audited` ou `monthly_capped`;
- a automacao nao deve marcar fila como `audited` sem `audit_id` valido.

## Validacao consolidada

- trilha minima da triagem validada com `31 tests OK`;
- classificacao real validada em `localhost:8080` com persistencia no banco de dados;
- checklist operacional do Modulo 1 registrada em `docs/manual-gestores/05-checklist-triagem.md`;
- revisao externa confirmou aceite do Modulo 1.

## Fronteira do Modulo 2

O Modulo 2 cobre:

- consumo do item elegivel vindo da triagem;
- execucao da auditoria;
- persistencia correta da auditoria;
- sincronizacao correta entre auditoria e fila;
- entrega do caso ao modulo do supervisor no estado correto.

O Modulo 2 nao cobre:

- contestacao;
- revisao tecnica;
- dashboard final.

## Perguntas centrais do Modulo 2

1. A auditoria persiste um registro valido de forma consistente?
2. A fila so vira `audited` quando houver auditoria persistida de verdade?
3. O caso auditado fica disponivel ao supervisor no endpoint e no estado corretos?
4. A regra de fila aberta do supervisor (`awaiting_pair` / `pending_approval`) esta coerente com o fluxo esperado?

## Pendencias conhecidas levadas para o Modulo 2

- investigar por que um caso real ficou com fila em `audited` sem auditoria localizavel por `audit_input_hash`;
- investigar o `500` observado em `GET /api/gestores/auditorias`;
- separar claramente o que e problema de persistencia da auditoria e o que e problema da camada HTTP do modulo supervisor.

## Arquivos prioritarios para a abertura

- `backend/automation.py`
- `backend/database.py`
- `backend/repositories/audits.py`
- `backend/routers/audit.py`
- `backend/routers/supervisor.py`
- `backend/routers/review.py`
- `backend/tests/test_audit_review_pair_queue.py`
- `backend/tests/test_audit_flow_fixes.py`
- `backend/tests/test_review_module_flow.py`
