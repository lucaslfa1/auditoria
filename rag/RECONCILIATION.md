# Reconciliação — POPs oficiais vs. scoring_rules.yaml

Data: 2026-04-16

## Estado atual

| Fonte | Alertas / fluxos | Critérios | Pesos explícitos |
|---|---:|---:|---:|
| `rag/sources/procedimentos_operacionais/*.md` | 20 | 273 | 12 |
| `backend/db/scoring_rules.yaml` | 33 | 433 | 433 |

## Decisão

Nenhum peso foi alterado automaticamente em `backend/db/scoring_rules.yaml`.

Motivo: apenas o POP de Cadastro contém pesos explícitos (`peso=...`) nos critérios. Os demais POPs descrevem critérios oficiais e justificativas operacionais, mas não trazem peso auditável. Reescrever pesos sem uma fonte oficial criaria uma mudança comportamental não rastreável na nota final.

## Regra operacional até a próxima revisão

- `scoring_rules.yaml` continua sendo a fonte ativa para IDs, pesos e cálculo da nota.
- `rag/sources/procedimentos_operacionais/` passa a ser a fonte oficial para interpretação operacional dos critérios já selecionados.
- Quando houver conflito de redação entre documentação histórica e POP oficial, o POP deve guiar a evidência textual, sem inventar critérios fora do YAML.
- Tags `[não-avaliável-por-ia]` e `[avaliação-acústica]` devem impedir inferência fraca quando a transcrição não trouxer evidência direta.

## Pendências para reconciliar pesos

- Receber pesos oficiais para Mondelez, Unilever, Checklist e Áreas de Risco.
- Criar POP próprio de BAS, mantendo `4.1.10` alinhado ao trecho já existente em `areas_de_risco.md`.
- Importar POPs pendentes de Logística Opentech e Célula de Atendimento.
- Depois da importação, comparar cada critério por ID, texto e peso antes de alterar `scoring_rules.yaml`.
