# Revisao de Regras de Negocio - 2026-04-09

## Escopo

Revisao comparativa entre:

- regras de negocio publicadas para gestao;
- catalogo oficial de criterios e alertas;
- contratos executaveis da triagem, fila e automacao;
- materiais de apoio usados como referencia tecnica.

## Resultado Executivo

O nucleo executavel da regra de negocio esta aderente ao fluxo atual da triagem.

Pontos confirmados:

- cota mensal de 2 auditorias por operador esta implementada e refletida na fila;
- casos incertos continuam indo para revisao com `desconhecido` quando necessario;
- fila de triagem usa os status oficiais `pending`, `auto_resolved`, `reviewed`, `audited` e `monthly_capped`;
- setores operacionais continuam compartilhando os alertas BAS do grupo 4.1.x;
- o alerta policial agora esta alinhado ao catalogo oficial como `BAS-PRIORITARIO-POLICIA` com POP `4.1.10`.

## Ajustes Aplicados Nesta Revisao

1. Alinhamento do alerta policial

- catalogo oficial atualizado para `BAS-PRIORITARIO-POLICIA`
- referencia POP corrigida para `4.1.10`
- alias legado `BAS-POLICIAL` mantido apenas para compatibilidade

2. Alinhamento de regra publicada

- regras gerenciais passaram a citar `acionamento policial` como alerta critico
- checklist de triagem atualizada para o novo identificador canonico

3. Correcao de material de apoio

- exemplos de inferencia de alertas em `backend/data/rag_training/regras_negocio.md` foram corrigidos
- referencia ao banco principal como SQLite foi removida desse material
- `docs/architecture/process-flow.md` foi alinhado para PostgreSQL como banco principal

## Evidencias de Aderencia

### Regra 1: cota mensal por operador

Documentacao:

- `docs/manual-gestores/04-regras-de-negocio.md`
- `docs/manual-gestores/02-fluxo-operacional.md`

Implementacao:

- `backend/automation.py`
- `backend/repositories/classification_review.py`
- `backend/db/domain_constants.py`

Status:

- aderente

### Regra 2: incerteza precisa ser explicitada

Documentacao:

- `docs/manual-gestores/03-triagem.md`
- `docs/manual-gestores/04-regras-de-negocio.md`

Implementacao:

- `backend/classification.py`

Status:

- aderente

### Regra 3: alertas criticos dominam alertas menores

Documentacao:

- `docs/manual-gestores/03-triagem.md`
- `docs/manual-gestores/04-regras-de-negocio.md`

Implementacao:

- `backend/classification.py`

Status:

- aderente, incluindo o alerta policial no grupo operacional

### Regra 4: correcao manual precisa valer de verdade

Documentacao:

- `docs/manual-gestores/02-fluxo-operacional.md`
- `docs/reviews/triagem-review-2026-04-08.md`

Implementacao:

- `backend/routers/classifier.py`
- `backend/repositories/classification_review.py`

Status:

- aderente

## Residuos Encontrados

1. Ainda existem documentos historicos fora do manual gerencial que falam em SQLite como banco principal.

Esses arquivos hoje devem ser tratados como historico tecnico, nao como fonte atual de regra operacional.

Exemplos:

- `docs/database.md`
- `docs/database/sqlite-coupling-inventory.md`
- `docs/prompt_gemini_deep_think_projeto_completo.txt`

2. `backend/tests_output.txt` ainda referencia o identificador policial antigo.

Esse arquivo e apenas um artefato de saida historica e nao afeta o runtime.

## Validacao Executada

- `backend.tests.test_classification_guardrails`
- `backend.tests.test_audit_evaluator_payloads`
- `backend.tests.test_auth_api.TestAuthApi.test_classify_returns_review_flags_and_syncs_review_queue`
- `backend.tests.test_review_queue_contract`
- `backend.tests.test_triagem_e2e_flow`

Resultado:

- `30 tests OK`

## Conclusao

Comparando regra publicada, catalogo e implementacao, o sistema esta coerente no nucleo da regra de negocio da triagem.

O que estava desalinhado era principalmente:

- o alerta policial antigo;
- materiais de apoio com referencias POP erradas;
- documentos historicos mencionando SQLite fora do contexto de teste.

O fluxo operacional vigente da triagem agora esta consistente com o que o codigo executa.
