# Índice — Procedimentos Operacionais Padrão (POPs)

> Fonte curada humana oficial. Alimenta a Camada 1 (injeção direta) e a Camada 2 (embeddings pgvector) do sistema RAG.

## Cobertura atual

| Arquivo | Setor | Fluxos / Alertas cobertos | Critérios | Não-avaliáveis por IA | Acústicos |
|---|---|---|---|---|---|
| `cadastro.md` | Cadastro | Antecedentes (receptivo) | 12 | 0 | 2 |
| `checklist.md` | Checklist | Processo Checklist (WhatsApp) | 12 | 0 | 0 |
| `mondelez.md` | Logística Mondelez | Monitoramento I, Monitoramento II, Logística Reversa | 43 | 0 | 6 |
| `unilever.md` | Logística Unilever | Devolução, Cabinets, Atuação Tratativa, Distribuição, Loss Tree | 70 | 0 | 10 |
| `areas_de_risco.md` | Distribuição / Rastreamento / UTI / Fênix | Alerta Prioritário (motorista/cliente), Posição em Atraso (motorista/cliente), Parada Indevida (motorista/cliente), Desvio de Rota (motorista/cliente), Ponto de Apoio, Acionamento Policial | 136 | 10 | 20 |
| `triagem.md` | Triagem | Regras de Triagem e Limites | - | - | - |
| `processo_localizacao.md` | Processo Localização | Processo para localizar ligações (Huawei) | - | - | - |
| **Total** | **—** | **22 fluxos/alertas** | **273+** | **10+** | **38+** |

## Formato dos arquivos

Cada POP segue esta estrutura:

```markdown
---
setor: <slug_do_setor>
alertas_cobertos:
  - <slug_alerta_1>
  - <slug_alerta_2>
versao: 1.0
ultima_revisao: YYYY-MM-DD
fonte_original: <caminho_do_arquivo_original>
---

# POP — <Título Humano>

> Procedimento Operacional Padrão (POP) oficial. Fonte curada humana para RAG.

## <NOME DO FLUXO / ALERTA EM CAIXA ALTA>

### <Pergunta do critério>

<Justificativa operacional detalhada>

### <Próximo critério> [tag-opcional]

<Justificativa>
```

## Tags nos critérios

Critérios podem receber tags entre colchetes no título (H3):

- `[não-avaliável-por-ia]` — O próprio POP indica que a IA não consegue verificar esse item (ex: "registrou o contato no sistema"). Deve ser omitido do prompt ou marcado como `null`/`N/A`
- `[avaliação-acústica]` — Critério depende de análise de áudio (tom de voz, uso de mudo), não de transcrição. Tratado por camada acústica separada

## Setores oficiais vs. setores auditáveis

Alguns POPs cobrem **múltiplos setores** simultaneamente. O arquivo `areas_de_risco.md` se aplica a Distribuição, Rastreamento, UTI e Fênix — quando o backend recupera o POP por setor, deve mapear todos esses quatro para o mesmo arquivo.

## Setores sem POP oficial nesta fase

Setores cobertos pelo sistema mas **ainda sem POP consolidado em markdown**:

- **BAS** (Base de Sinistros) — pendente como POP próprio; o caso de acionamento policial `4.1.10` já está coberto em `areas_de_risco.md`
- **Logística Opentech** (não Mondelez/Unilever) — Estadia, Ativação AE, Controle de Temperatura, Taborda, etc. (critérios 4.4.1 a 4.4.? em `regras_negocio.md`)
- **Célula de Atendimento** — WhatsApp CHATBOT

Esses setores continuam sendo servidos pelo `scoring_rules.yaml` até que POPs oficiais sejam redigidos e importados.

## Quando atualizar este índice

- Adicionar nova linha à tabela quando criar novo POP
- Atualizar contagens quando critérios forem adicionados/removidos
- Registrar a mudança no `rag/CHANGELOG.md`
