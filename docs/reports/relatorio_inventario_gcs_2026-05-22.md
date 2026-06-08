# Relatório de Inventário: Storage Físico GCS

**Data:** 22 de Maio de 2026
**Tipo:** snapshot operacional do inventário feito antes da Fase 1 de abstração de mídia.

## 1. Visão Geral da Infraestrutura de Arquivos
Conforme a política de evitar armazenamento de arquivos (mídias) diretamente no banco de dados Neon/Postgres, foi feito o levantamento dos arquivos no provedor Google Cloud Storage (GCS) utilizado pela aplicação.

## 2. Métricas do Bucket GCS
- **Bucket:** `auditoria-nstech-audios`
- **Total de Objetos (Áudios/PDFs):** 1.858 arquivos
- **Volume Total Ocupado:** 4.331,71 MB (~4.33 GB)
- **Tamanho Médio por Objeto:** 2,33 MB
- **Regras de Ciclo de Vida (Lifecycle/Retention):** Nenhuma configurada. O armazenamento continuará crescendo indefinidamente a menos que políticas sejam aplicadas.

### 2.1. Estrutura de Diretórios (Prefixos)
- `classified_audio/`: 1.457 objetos (Áudios que foram baixados da Huawei e passaram pela triagem/classificação).
- `2026/`: 401 objetos (Áudios gerados pelo módulo de auditoria após conclusão).

## 3. Integridade com o Banco de Dados (Drift Analysis)
Foi realizada uma análise comparando os metadados armazenados no banco de dados (`fila_revisao_classificacao` e `audits`) com os caminhos reais encontrados no GCS.

- **Fila de Revisão/Triagem (`fila_revisao_classificacao`):**
  - **Total de Registros na Fila:** 9 itens.
  - **Ponteiros Corretos (Encontrados no GCS):** 8 itens.
  - **Ponteiros Quebrados (Drift):** 1 item. *(Nota: Corresponde ao áudio de teste local 'dummy' injetado durante os testes da automação. Portanto, não há perda real de dados de produção.)*

- **Auditorias Concluídas (`audits`):**
  - **Total de Registros:** 0 itens na base atual.

## 4. Custos e Impacto
Como o tamanho médio é de 2.33 MB e o total não ultrapassa 5GB, os custos atuais de storage no GCS são mínimos (Centavos de Dólar). Transferir esses 4.33 GB para dentro do Neon DB como campos `BYTEA` escalaria os custos de Branching e Storage History do Neon desnecessariamente. Manter no GCS e gerenciar via tabela `media_files` é definitivamente a melhor abordagem arquitetural até a futura migração para Azure Blob.

## 5. Uso deste Registro
Este relatório deve ser tratado como registro histórico do inventário daquele momento, não como plano de implantação ativo.

A Fase 1 da abstração passou a rastrear mídia classificada na tabela `media_files` usando o namespace `classified:{input_hash}`. A migração de áudios finais de auditoria para `media_files` segue bloqueada até a definição explícita das regras de ownership e limpeza entre Telefonia e Triagem.
