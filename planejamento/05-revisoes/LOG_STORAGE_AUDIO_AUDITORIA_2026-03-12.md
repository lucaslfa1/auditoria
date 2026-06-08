# Log de ajuste - Storage de audio da auditoria

Data: 2026-03-12

## Objetivo

Persistir os arquivos de audio das auditorias fora do banco de dados, mantendo no SQLite apenas a referencia necessaria para reproducao futura e rastreabilidade.

## Alteracoes

- Adicionadas colunas de referencia de audio na tabela `audits`:
  - `audio_storage_path`
  - `audio_original_filename`
  - `audio_mime_type`
  - `audio_size_bytes`
- Criada migration `20260312_011_add_audit_audio_storage`.
- Criado utilitario `backend/audit_storage.py` para salvar audio em `backend/storage/audits/audio/...` ou no diretorio definido por `AUDIT_AUDIO_STORAGE_DIR`.
- Centralizada a persistencia em `database.persist_audit_artifacts`, cobrindo:
  - auditoria nova
  - auditoria retornada por cache com backfill do audio ausente
- Adicionado endpoint autenticado `GET /api/audit/{audit_id}/audio`.
- O detalhe da auditoria na Supervisao agora informa `audio_available` e `audio_url` quando houver audio salvo.
- Corrigido `get_audit_by_id` para incluir `supervisor` e `escala`, o que mantem a checagem de escopo coerente para supervisores.

## Validacao

- `python -m py_compile backend/audit_storage.py backend/database.py backend/repositories/audits.py backend/routers/audit.py backend/routers/supervisor.py backend/db/runtime_schema.py backend/db/migration_steps/m20260312_011_add_audit_audio_storage.py`
- `python -m pytest backend/tests/test_audit_audio_storage.py backend/tests/test_auth_api.py -q`
- `python -m pytest backend/tests -q`

## Observacao

O backend ja esta preparado para player por auditoria com seek por trecho. O proximo passo, se desejado, e ligar `audio_url` na tela de Supervisao com um player e acao de ir para o `timestamp` do criterio.
