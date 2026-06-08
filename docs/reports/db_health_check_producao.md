# Relatório de Saúde do Banco de Dados (Produção - NeonDB)

## 1. Tabela `audits`
- Total de auditorias: 468
- Distribuição de status:
  - `pending_approval`: 141
  - `awaiting_pair`: 202
  - `approved`: 89
  - `discarded`: 36
- Auditorias com `operator_name` mas sem `colaborador_id` (vínculo quebrado): 86
- Auditorias com `input_hash` duplicado: 33

## 2. Tabela `arquivos_salvos`
- Total de arquivos salvos: 170
- Arquivos órfãos (sem `audit_id` associado): 0

## 3. Tabela `fila_revisao_classificacao` (Triagem)
- Total na fila: 0
- Distribuição de status:

## 4. Tabela `colaboradores`
- Total de colaboradores: 220
- Colaboradores com `id_huawei` duplicado: 3
  - IDs duplicados: ['2387', '662', '2505']

## 5. Tabela `huawei_sync_logs`
- Distribuição de status:
  - `failed`: 2215
  - `skipped_direction`: 3016
  - `skipped_quota`: 390
  - `success`: 114

## 6. Integridade Relacional (`gestor_feedbacks`)
- Total de feedbacks: 0
- Feedbacks órfãos (sem auditoria): 0