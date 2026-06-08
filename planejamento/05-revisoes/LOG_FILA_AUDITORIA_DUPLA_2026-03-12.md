# Log de mudança - fila dupla por operador

Data: 2026-03-12

## Objetivo

Alterar o fluxo de envio ao supervisor para que a primeira auditoria de um operador fique armazenada e oculta da Supervisão até que a segunda auditoria do mesmo operador exista.

## Implementação

- Adicionado o status intermediário `awaiting_pair` no domínio de auditorias.
- O endpoint de salvar no dashboard agora usa uma fila por operador:
  - 1 auditoria aberta: fica em espera.
  - 2 auditorias abertas: ambas seguem para `pending_approval`.
  - 3 ou mais abertas: as excedentes continuam em espera até liberar espaço.
- Ao aprovar ou contestar uma auditoria, o sistema reequilibra automaticamente a fila do operador e promove a próxima pendente em espera quando aplicável.
- A listagem da Supervisão ignora auditorias em `awaiting_pair`.
- A tela de auditoria passou a informar se o resultado foi:
  - armazenado aguardando a 2a auditoria; ou
  - liberado ao supervisor.

## Arquivos principais

- `backend/repositories/audits.py`
- `backend/database.py`
- `backend/routers/system.py`
- `backend/routers/supervisor.py`
- `backend/db/domain_constants.py`
- `backend/db/migration_steps/m20260312_012_allow_awaiting_pair_status.py`
- `src/features/audit/hooks/useTranscription.ts`
- `src/features/audit/components/AuditResultActions.tsx`
- `src/features/audit/components/AuditWorkspace.tsx`
- `src/App.tsx`

## Validação

- `python -m pytest backend/tests/test_audit_review_pair_queue.py backend/tests/test_auth_api.py backend/tests/test_database_security.py -q` -> `38 passed`
- `python -m pytest backend/tests -q` -> `172 passed, 1 skipped`
- `npm run test:frontend` -> OK
- `npm run build` -> OK
