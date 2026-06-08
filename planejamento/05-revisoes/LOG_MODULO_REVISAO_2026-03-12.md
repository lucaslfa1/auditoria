# Log de mudança - módulo Revisão

Data: 2026-03-12

## Objetivo

Separar o fluxo de contestação do supervisor do fluxo final de publicação da auditoria, criando um módulo próprio de `Revisão` para a equipe de auditoria.

## O que mudou

- Criado o módulo `Revisão` no frontend para administradores.
- Movida a fila técnica de classificação para o módulo `Revisão`.
- Removida a fila de revisão da classificação do `Painel`.
- A contestação do supervisor agora muda a auditoria para `contestation_pending_review`.
- A equipe de auditoria passa a registrar:
  - veredito da contestação (`accepted` ou `rejected`);
  - defesa técnica;
  - usuário que revisou;
  - data da revisão.
- Se a contestação for negada, a auditoria volta ao fluxo oficial com status `approved`.
- Se a contestação for aceita, a auditoria fica como `contestation_accepted` e não entra no dashboard oficial.
- A Supervisão passou a mostrar o resultado final da contestação com a defesa técnica.

## Arquivos principais

- `backend/routers/review.py`
- `backend/routers/supervisor.py`
- `backend/repositories/audits.py`
- `backend/database.py`
- `backend/db/domain_constants.py`
- `backend/db/runtime_schema.py`
- `backend/db/migration_steps/m20260312_013_add_review_module_statuses_and_fields.py`
- `src/features/review/components/ReviewPage.tsx`
- `src/features/supervisor/components/SupervisorPortal.tsx`
- `src/features/dashboard/components/Dashboard.tsx`
- `src/App.tsx`
- `src/shared/components/Sidebar.tsx`

## Validação

- `python -m pytest backend/tests/test_review_module_flow.py backend/tests/test_gestor_feedback_persistence.py backend/tests/test_auth_api.py backend/tests/test_database_security.py -q` -> `41 passed`
- `python -m pytest backend/tests -q` -> `175 passed, 1 skipped`
- `npm run test:frontend` -> OK
- `npm run build` -> OK

## Observação

O endpoint legado `/api/dashboard/classificacao-revisao` foi mantido por compatibilidade, mas a UI principal agora consome a fila técnica pelo módulo `Revisão`.

## Ajuste posterior

- A listagem da `Supervisão` passou a exibir um resumo visual por auditoria sem precisar abrir o detalhe.
- Estados resumidos na interface:
  - `Aguardando decisão`
  - `Contestação em análise`
  - `Contestação negada`
  - `Contestação aceita`
  - `Publicada`
- O cabeçalho do card do operador agora mostra o status resumido de cada `Registro`, sem depender da aba ativa.
- As abas também passaram a usar o mesmo rótulo curto com data do registro para manter a leitura consistente.
- A tela de `Revisão` passou a tolerar backend antigo: se a rota nova da classificação não existir, ela usa a rota legada sem quebrar a página.
- Se o backend ativo estiver sem a rota de contestações, a UI exibe aviso de compatibilidade em vez de derrubar toda a carga da tela.
- O backend local em `:8080` foi reiniciado com a versão atual; as rotas `/api/revisao/contestacoes` e `/api/revisao/classificacao` deixaram de retornar `404` e passaram a responder `401` sem sessão, confirmando que estão publicadas.
- Os gráficos principais receberam `minWidth` e `minHeight` para reduzir o warning de `width(-1) / height(-1)` do Recharts.
- O fluxo de contestação na `Supervisão` deixou de ficar escondido atrás de um textarea condicional.
- `Aprovação pendente` agora exibe um campo explícito de `Contestação do supervisor`, com orientação de preenchimento e envio direto para a revisão técnica.
- O texto persistido continua usando `contestation_reason`, mas a interface foi ajustada para refletir o uso operacional correto: registrar a discordância formal do supervisor com a análise.
- O módulo visível passou a se chamar `Contestações`, que é o nome operacional correto para o usuário.
- A fila de erros técnicos da classificação saiu dessa tela e fica guardada como ideia para um fluxo interno futuro, sem expor isso no módulo do usuário final.
