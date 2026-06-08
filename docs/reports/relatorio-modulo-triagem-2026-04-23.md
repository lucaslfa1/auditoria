# Relatório — Módulo Triagem (Auditoria NSTECH)

**Status operacional:** Módulo 1 fechado em 2026-04-09 (ver [docs/reviews/triagem-review-2026-04-08.md](../reviews/triagem-review-2026-04-08.md)). Estrutura ponta-a-ponta funcional: upload → transcrição → classificação GPT-4o → guardrails → persistência em `fila_revisao_classificacao`.

## ✅ Atendendo corretamente
| Item | Evidência |
| :--- | :--- |
| Resolução de operador por hierarquia RH | `id_huawei > nome arquivo > nome IA` (`backend/classification.py:1401`) |
| Fallback por supervisor (Miralha) | `_resolve_db_sector_alias` (`backend/classification.py:702`) |
| Deduplicação | SHA256 do áudio bruto + lookup em fila/auditoria (`backend/routers/classifier.py:110`) |
| Force reclassify | Flag `force_reclassify` em Form (`backend/routers/classifier.py:90`) |
| Correção manual sincroniza RH | PATCH upserta colaboradores (`backend/routers/classifier.py:317`) |
| 5 guardrails de negócio | setor/direção, hierarquia de alerta, temperatura, parada×desvio |
| Testes E2E | `test_triagem_e2e_flow.py`, `test_classification_guardrails.py`, `test_classification_review_policy.py` |

## ⚠ Pontos de atenção (não-bloqueantes)
1.  **Sentinela string "null"** — `backend/classification.py:1411` grava "null" (string) quando não há operador; depois re-converte para `None` na linha 1434. Frágil — recomendado usar `None` direto e ajustar o guardrail de direção.
2.  **float(confidence, 0.5) silencioso** — `backend/classification.py:1443` mascara valor inválido em 0.5 sem `review_reason`. Pode gerar falso "média confiança".
3.  **@lru_cache sem invalidação** — `load_audit_criteria_catalog()` cacheia YAML sem hot reload. Alteração de critério exige restart.
4.  **Erro genérico no GPT** — `backend/classification.py:1261` captura `Exception` amplo; falhas do Azure viram "desconhecido" silencioso em `_safe_classify_audio`.
5.  **Cobertura de testes incompleta** — sem teste para: PATCH de correção manual, detecção de duplicata em lote, reclassificação forçada.
6.  **Fallback de sector_hint sem validar alert_id_hint** — `backend/classification.py:1421-1432` aceita hint do filename; se YAML mudar IDs, cai silencioso.

## 📋 Pendências documentadas (review 2026-04-08)
Etapas residuais marcadas na review original — validar se todas foram concluídas nas Prioridades 1-5.

**Veredicto:** Módulo opera como contratado. Sem bug crítico; refinos acima são dívida técnica de baixa prioridade. Recomendação: fechar as 3 etapas residuais da review antes de avançar Módulo 2.
