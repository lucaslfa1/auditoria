---
tipo: decisao
area: banco
criado: 2026-05-30
atualizado: 2026-05-30
---

# Banco de Dados Canônico e Topologia Neon

## Contexto
Durante investigações de drift entre ambiente local, cron e ferramentas de debug (`diagnose_auto_audit_state.py`, `rescue*.py`), observou-se leituras inconsistentes. Havia dois projetos Neon envolvidos (`ep-aged-river` e `ep-falling-hall`) causando confusão ao assumir que eram branches do mesmo projeto.

## Conhecimento
- O Neon project **`ep-falling-hall` foi deletado permanentemente** pelo desenvolvedor e não existe mais. Tratava-se de um projeto diferente (não uma branch).
- O **único banco de dados canônico** atual é o projeto **`auditoria-nstech-2`**.
- O endpoint de compute ativo para este banco é **`ep-aged-river-acr5e219`**.
- O nome do banco dentro da instância do Postgres continua sendo `neondb`.
- A variável `DATABASE_URL` no Cloud Run (produção) e nos `.env` locais já apontam exclusivamente para o `ep-aged-river`.
- Existe uma migração planejada futura para Azure Flexible Server, mas no momento presente, Neon `ep-aged-river` é a única fonte da verdade.

## Como aplicar
Nunca referencie, mencione ou tente conectar a `ep-falling-hall`. Ao analisar o banco, fazer queries locais ou inspecionar o estado da automação, assuma e certifique-se de que a conexão é com `ep-aged-river`.
