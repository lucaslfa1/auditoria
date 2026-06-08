# Relatório de Estabilização e Recuperação: Huawei Sync & Triagem IA (26/04/2026)

## O que foi realizado
Este relatório documenta a recuperação do código após a desconexão do assistente, reimplementando os 5 itens críticos para o fluxo de coleta e auditoria da Huawei:

1. **Endpoint de Auditoria Instantânea (`/audit`)**: 
   - Arquivo: `backend/routers/telefonia.py`.
   - Adicionado o endpoint `POST /api/telefonia/recordings/{hash}/audit`.
   - Permite acionar a auditoria IA ignorando a triagem manual, extraindo áudio via `load_classified_audio` e salvando o resultado via `persist_audit_artifacts`.

2. **Exposição de Contadores no Frontend**: 
   - Arquivos: `src/features/telefonia/hooks/useTelefoniaSync.ts` e `src/features/telefonia/components/SyncPanel.tsx`.
   - Incluídos contadores detalhados de diagnósticos: `download_fs_miss`, `obs_fallback_tentativas`, `obs_fallback_hits`, `obs_fallback_misses` e array de erros limitados na UI a 5 itens.

3. **Log Diagnóstico no OBS (`huawei_obs_client.py`)**:
   - Adicionado logger no momento de falha total de download (miss).
   - O sistema agora faz um fallback de tentativa rápida de listagem (limit=5) das chaves no diretório vizinho `Voice/{date_str}/` para orientar sobre qual formato real a Huawei está usando.

4. **Persistência de Falhas no Banco (Migrations & DB)**:
   - Arquivo: `backend/db/runtime_schema.py` e `backend/database.py`.
   - Adicionadas as colunas `status` e `failure_reason` em `huawei_sync_logs`.
   - O comando `ON CONFLICT` agora faz `UPDATE` promovendo logs do status `failed` para `success` (ou sobrescrevendo falhas).

5. **Registro das Falhas de Coleta (`huawei_sync.py`)**:
   - Tratamento de falhas e `exceptions`. Quando o áudio não é encontrado ou se houver um erro Python, chama `database.huawei_sync_log_registrar(..., status='failed')`.
   - Inclusão da chave `workNo` na geração de sufixos de tentativa do OBS.

## Situação Atual
- Nenhum erro de TypeScript (`npx tsc --noEmit` ok).
- Backend não apresenta erros de sintaxe (imports validados).
- Testes unitários do `huawei_sync` rodam perfeitamente (11/11).
- O código está estabilizado, pronto para *commit*, *push* e *deploy*.