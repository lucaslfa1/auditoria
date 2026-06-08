# Documentacao oficial de auditoria

Esta pasta centraliza as fontes oficiais usadas para validar criterios, pesos, regras nao negociaveis e fechamento mensal.

## Estrutura

- `CRITÉRIOS DA AUDITORIA - *.pdf`
  - PDFs oficiais por operacao/setor.
- `criterios_pesos/CRITÉRIOS - PESOS -.xlsm`
  - Planilha oficial de criterios, pesos e deflatores.
- `../docs/references/auditoria/criterios-nao-negociaveis.txt`
  - Regras oficiais de zeragem e itens nao negociaveis. Fonte canonica movida
    para `docs/references/` na Fase 1 de organizacao.
- `fechamento/03 - FECHAMENTO PLANEJAMENTO.xlsx`
  - Modelo oficial de fechamento enviado ao Planejamento.

## Regras de organizacao

- Esta pasta deve conter somente documentos oficiais ou diretamente recebidos/validados como fonte oficial.
- Arquivos derivados, extracoes temporarias, comparativos e relatorios devem ficar fora daqui, preferencialmente em `docs/reports/`, `tmp/` ou scripts dedicados.
- O runtime atual nao le os criterios diretamente desta pasta. O catalogo ativo da aplicacao continua em `backend/db/scoring_rules.yaml`, que deve ser reconciliado contra estes documentos.
- Quando um documento oficial for substituido, registre a data e valide se `backend/db/scoring_rules.yaml`, banco, prompts e exportacoes continuam alinhados.

