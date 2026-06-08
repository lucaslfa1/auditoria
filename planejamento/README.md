# Planejamento

Data de referencia: 2026-03-12

## Objetivo

Esta pasta concentra material de planejamento, analise, estrategia, referencia operacional e revisoes tecnicas do projeto.

## Estrutura

```text
planejamento/
|-- README.md
|-- INDICE_COMPLETO.md
|-- 01-resumos/
|   `-- RESUMO_EXECUTIVO.txt
|-- 02-analises/
|   |-- ANALISE_FUNCIONARIOS.md
|   `-- CRITERIOS_INTEGRADOS_FUNCIONARIOS.md
|-- 03-estrategia/
|   |-- ESTRATEGIA_IMPLEMENTACAO.md
|   |-- FLUXO_AUDITORIA_SUPERVISAO_REVISAO.md
|   |-- GUIA_IMPLEMENTACAO_AUDITORIA_INTEGRADA.md
|   |-- GUIA_PRATICO.md
|   `-- PROCEDIMENTO_AUTOMATIZACAO.md
|-- 04-referencias/
|   `-- README.md
`-- 05-revisoes/
    `-- REVISAO_ATUALIZACOES_2026-03-12.md
```

## Regra de organizacao

- `01-resumos/`: visao executiva e leitura curta.
- `02-analises/`: consolidacoes, diagnosticos e material analitico.
- `03-estrategia/`: planos de execucao, guias de implementacao e operacao.
- `04-referencias/`: congelada; referencias canonicas migradas para `../docs/references/`.
- `05-revisoes/`: revisoes tecnicas pontuais e achados de verificacao.

## Ponto de entrada por perfil

- Gestao: `01-resumos/RESUMO_EXECUTIVO.txt`
- Desenvolvimento: `03-estrategia/ESTRATEGIA_IMPLEMENTACAO.md`
- Operacao e supervisao: `03-estrategia/GUIA_PRATICO.md`
- Fluxo oficial da auditoria e contestacao: `03-estrategia/FLUXO_AUDITORIA_SUPERVISAO_REVISAO.md`
- Criterios e qualidade: `../docs/references/auditoria/criterios-auditoria-opentech.md`
- Revisao tecnica recente: `05-revisoes/REVISAO_ATUALIZACOES_2026-03-12.md`

## Ordem de leitura recomendada

1. `01-resumos/RESUMO_EXECUTIVO.txt`
2. `02-analises/ANALISE_FUNCIONARIOS.md`
3. `03-estrategia/ESTRATEGIA_IMPLEMENTACAO.md`
4. `03-estrategia/GUIA_IMPLEMENTACAO_AUDITORIA_INTEGRADA.md`
5. `../docs/references/auditoria/criterios-auditoria-opentech.md`

## Convencoes

- Novos documentos de planejamento devem entrar primeiro na categoria correta.
- Revisoes tecnicas novas devem ir para `05-revisoes/` com data no nome.
- Arquivos de entrada da pasta ficam apenas na raiz: `README.md` e `INDICE_COMPLETO.md`.
- Se um documento mudar de funcao, ele deve ser movido para a categoria correta em vez de duplicado.
