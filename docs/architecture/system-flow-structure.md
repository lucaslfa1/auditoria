# Estrutura Alinhada ao Fluxo do Sistema

Atualizado em 2026-03-26 para refletir o estado atual do codigo.

## Fluxos funcionais ativos

- `auth`: login, sessao e autorizacao
- `audit`: configuracao, upload, avaliacao, edicao e exportacao
- `classifier`: triagem de audios antes da auditoria
- `dashboard`: leitura de historico e indicadores
- `supervisor`: aprovacao operacional, KPIs e exports
- `review`: veredito tecnico de contestacoes
- `saved-files`: consulta de artefatos salvos
- `settings`: configuracoes operacionais
- `ai-feedback`: feedback e calibracao de IA
- `admin`: administracao de criterios
- `colaboradores`: gestao de pessoas e vinculos operacionais

## Estrutura canonica do frontend

- `src/features/audit`
- `src/features/classifier`
- `src/features/dashboard`
- `src/features/supervisor`
- `src/features/review`
- `src/features/saved-files`
- `src/features/settings`
- `src/features/ai-feedback`
- `src/features/admin`
- `src/features/colaboradores`
- `src/shared/components`
- `src/shared/hooks`
- `src/shared/lib`
- `src/shared/types`
- `src/contexts`

## Regra pratica para o frontend

- tudo que representa uma etapa do produto fica em `features/<dominio>`
- tudo que e reutilizado entre dominios fica em `shared`
- `App.tsx` permanece como shell da aplicacao
- contextos globais ficam em `src/contexts`
- hooks de fluxo ficam proximos da feature que controlam

## Estrutura canonica do backend

- `backend/main.py`
- `backend/database.py`
- `backend/services.py`
- `backend/core/`
- `backend/audio/`
- `backend/transcription_providers/`
- `backend/routers/auth.py`
- `backend/routers/system.py`
- `backend/routers/saved_files.py`
- `backend/routers/audit.py`
- `backend/routers/classifier.py`
- `backend/routers/supervisor.py`
- `backend/routers/review.py`
- `backend/routers/admin.py`
- `backend/routers/analytics.py`
- `backend/routers/automation.py`
- `backend/routers/ai_feedback.py`
- `backend/routers/admin_criteria.py`
- `backend/routers/common.py`
- `backend/repositories/`
- `backend/db/`

## Regra pratica para o backend

- `main.py` cuida de bootstrap, middlewares, seguranca e registro de routers
- `database.py` faz bootstrap do banco e expoe a fachada publica
- `core/` concentra a logica principal de transcricao, avaliacao e auditoria
- `repositories/` concentra persistencia e regras por agregado
- `routers/` expoe os processos do sistema por dominio funcional
- `services.py` existe como camada de compatibilidade e re-export

## Observacoes atuais

- o frontend buildado em `dist/` pode ser servido pelo proprio backend FastAPI
- o fluxo de auditoria nao termina no score; ele segue para supervisao e revisao
- o modulo de classificacao alimenta filas e tabelas operacionais antes da auditoria
- a organizacao atual privilegia fluxo de produto e manutencao incremental
