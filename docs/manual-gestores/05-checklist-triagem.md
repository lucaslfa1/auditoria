# Checklist Operacional do Modulo de Triagem

Data de referencia: 2026-04-09

## Objetivo

Esta checklist existe para certificar o fechamento do modulo 1 da triagem antes de avancar para os modulos seguintes.

Ela cobre apenas o recorte da triagem:

- entrada do audio;
- classificacao;
- persistencia;
- fila de revisao;
- correcao manual;
- duplicidade;
- audio classificado;
- entrega correta para a fronteira da auditoria.

Ela nao cobre:

- aprovacao do supervisor;
- contestacao;
- revisao tecnica;
- dashboard final.

## Legenda de status

- `Concluido`: validado com evidencia objetiva.
- `Parcial`: validado em parte, mas ainda precisa de confirmacao complementar.
- `Pendente`: ainda precisa de execucao ou confirmacao.
- `Nao se aplica`: item fora do escopo atual.

## Checklist de aceite

| Item | Status | Evidencia | Observacoes |
| --- | --- | --- | --- |
| Upload de audio suportado entra na triagem sem erro de contrato | Concluido | Teste real em `localhost:8080/api/classify` com fixture `20260217114030490_Fabiula_de_Espindola_BAS_Voz.wav` retornando `200` | Validado contra backend local usando persistencia real no banco de dados |
| `/api/classify` retorna setor, alerta, confianca, operador e `input_hash` | Concluido | Resposta real da classificacao retornou `sector_id=bas`, `alert_id=BAS-PRIORITARIO-POLICIA`, `confidence=0.95`, `operator_name=Fabiula de Espindola` e `input_hash` persistido | Comportamento coerente com o contrato atual da triagem; `BAS-POLICIAL` fica como alias legado para compatibilidade |
| Casos certos seguem sem depender de revisao manual | Concluido | Classificacao real retornou `needs_review=false`, `review_reasons=[]`, `review_priority=low` | Entrega correta do caso resolvido automaticamente |
| Casos incertos sobem com `needs_review` e prioridade coerente | Concluido | Suite automatizada `test_classification_guardrails` e `test_classification_direction_guardrail` verde | Guardrails de confianca, direcao e catalogo validados |
| Quando setor ou alerta nao forem seguros, o sistema usa `desconhecido` | Concluido | Cobertura automatizada em `test_classification_guardrails` | Regra operacional mantida |
| A fila persiste item de triagem com contrato publico estavel | Concluido | Suite `test_review_queue_contract` verde e item real visivel em `/api/revisao/classificacao` | Shape publico com `metadata` desserializado mantido |
| `metadata.classified_audio_path` fica salvo para reaproveitamento | Concluido | Item real na fila exibiu `classified_audio_path=5543d8f9be137a1a.wav` | Contrato de reaproveitamento de audio mantido |
| Alias `ready_for_audit` funciona como consulta e nao como status persistido | Concluido | Item real apareceu em `status=auto_resolved` e tambem foi retornado pela consulta `ready_for_audit` | Contrato de alias preservado |
| Correcao manual persiste no backend e vira fonte autoritativa | Concluido | Cobertura automatizada consolidada no review da triagem e nos testes de auth/manual correction | Falta apenas repeticao operacional manual se quisermos evidencia visual complementar |
| Duplicidade reaproveita estado existente e nao sobrescreve revisao manual | Concluido | Etapa residual 2 formalizada no review da triagem e coberta pelos testes da trilha | Regra documentada e mantida como contrato do modulo |
| Reprocessamento por hash nao cria ruido de fila | Concluido | Review da triagem e cobertura automatizada de contrato | Sem indicio atual de regressao nessa trilha |
| `monthly_capped` bloqueia o operador no mesmo mes com rastreabilidade | Concluido | Suite `test_review_queue_contract` verde, incluindo o ramo de cota mensal | Regra oficial centralizada no dominio e na automacao |
| Audio classificado pode ser reaberto pela automacao quando referenciado | Concluido | Suite `test_triagem_e2e_flow` verde | Fluxo integrado exercita o reaproveitamento do audio salvo |
| Audio ausente nao fica em falha silenciosa; volta para `pending` com motivo rastreavel | Concluido | Suite `test_review_queue_contract` verde para `audio_classificado_ausente` | Protecao operacional validada |
| Nenhum modulo da triagem grava status fora do dominio oficial | Concluido | Suite `test_review_queue_contract` verde e aliases legados normalizados | Status oficiais estabilizados: `pending`, `auto_resolved`, `reviewed`, `audited`, `monthly_capped` |
| A triagem entrega corretamente para a fronteira da auditoria | Parcial | Item real foi classificado, persistido e exposto como elegivel para auditoria | A trilha posterior pertence ao modulo seguinte e nao entra no aceite do modulo 1 |
| A interface mostra corretamente fila, filtros e feedback visual da triagem | Pendente | Ainda depende de validacao humana na UI | Recomendado validar no navegador antes do fechamento formal |

## Evidencias automatizadas atuais

- `backend.tests.test_review_queue_contract`
- `backend.tests.test_triagem_e2e_flow`
- `backend.tests.test_classification_guardrails`
- `backend.tests.test_classification_direction_guardrail`

Resultado mais recente da validacao minima:

- `30 tests OK`

## Evidencia operacional real executada

Fluxo real validado em `localhost:8080` com persistencia no banco de dados:

1. login local com `admin/admin`;
2. classificacao real de uma fixture de audio;
3. confirmacao do item na fila de revisao;
4. confirmacao de `auto_resolved` e do alias `ready_for_audit`.

## Criterio de fechamento recomendado

O modulo 1 da triagem pode ser tratado como fechado quando:

- todos os itens desta checklist estiverem `Concluido` ou `Nao se aplica`;
- o unico item restante for a validacao visual da UI, caso a equipe queira essa confirmacao humana antes do aceite final;
- o fluxo posterior de auditoria, supervisor e contestacao for tratado em modulo separado.
