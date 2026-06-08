# Módulo Automação

Este módulo controla o motor de auditoria automática. A coleta de Telefonia roda em
um cron separado e alimenta a fila usada pela Automação:

```text
Telefonia D-1/OBS -> fila ready_for_audit -> Auditoria IA -> Arquivos
```

## Estado atual

- Backend: `backend/automation_engine.py` expõe um ciclo reutilizável somente para auditoria e mantém o loop residente apenas quando `ENABLE_IN_PROCESS_AUTOMATION_ENGINE=true`.
- Produção: o caminho recomendado é usar dois Cloud Schedulers: Coletor em `POST /api/telefonia/cron/sync` e Auditor em `POST /api/automation/cron/run`, ambos com `Authorization: Bearer <CRON_SECRET_TOKEN>`.
- Telefonia e Automação têm gates separados: o cron de Telefonia usa `telefonia_cron_sync_ativa`; o motor de Automação usa `automacao_hibrida_ativa`; o pipeline D-1 mantém `huawei_d1_enabled`.
- Huawei: `backend/core/huawei_sync.py` consulta a VDN globalmente, sem `agentId`/`mediaType`, complementa a descoberta pelo manifesto `Contact_Record` do OBS, baixa a mídia, classifica áudio pelo classificador de triagem e enfileira o arquivo com `auto_resolved` quando não há motivo de revisão.
- Regras Huawei: antes do download, o sync aplica apenas filtros operacionais mínimos, como duração, histórico de sincronização e limite de tentativas por ciclo. Cadastro de Operadores, classificação, RAG e auditoria não devem bloquear a descoberta nem o download da gravação.
- Auditoria: `backend/automation.py` processa itens `ready_for_audit`, respeita cota mensal e marca a fila como `audited` somente após persistir uma auditoria. Auditorias persistidas ficam em `awaiting_pair`/Arquivos Salvos para revisão do auditor admin; só entram em `pending_approval` quando o admin aciona "Enviar ao supervisor".
- Frontend: `AutomacaoPage.tsx` exibe status do motor e permite ligar/desligar a automação para administradores.

## Contratos

- O motor é controlado por `/api/automation/engine/toggle` e `/api/automation/engine/status`.
- O disparo manual pela tela usa `/api/automation/run-now`, com o mesmo advisory lock do cron para impedir ciclos paralelos.
- O cron do Auditor usa `/api/automation/cron/run`, protegido por `CRON_SECRET_TOKEN` e por lock consultivo no PostgreSQL para evitar execuções paralelas.
- O cron do Coletor usa `/api/telefonia/cron/sync`, protegido pelo mesmo `CRON_SECRET_TOKEN`, e preserva o fluxo Huawei D-1 via OBS.
- O status operacional do ciclo fica persistido em `automation_cycle_runs`, incluindo etapa, mensagem, heartbeat, resultado D-1, progresso da auditoria e erro.
- A execução em lote usa `/api/automation/audit-all`, também restrita a administradores.
- Itens de áudio usam `source_type=audio`; chats PDF da Huawei usam `source_type=pdf`.
- A aprovação final continua no fluxo de supervisor.
