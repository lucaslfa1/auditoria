# Relatório - Textos dos critérios exibidos na auditoria

Data: 2026-04-29  
Branch analisada: `auditoria-casa`  
Base documental: `auditoria_criterios/criterios_pesos/CRITÉRIOS - PESOS -.xlsm`

## Objetivo

Verificar se os critérios que aparecem no resultado da auditoria estão escritos exatamente da mesma forma que os critérios oficiais da documentação de auditoria.

## Escopo e fonte real dos textos

No estado atual da branch `auditoria-casa`, o texto exibido nos critérios avaliados vem do campo `label` de cada critério carregado em `backend/db/scoring_rules.yaml`.

Fluxo verificado:

- `backend/db/scoring_loader.py` carrega sempre `backend/db/scoring_rules.yaml`.
- `backend/database.py` sincroniza o banco a partir de `scoring_rules.yaml`.
- `backend/core/evaluation.py` monta `AuditResultDetail(label=crit.label)`.
- `src/features/audit/components/AuditEvaluationDetailsPanel.tsx` exibe `item.label`.

Portanto, para os critérios saírem exatamente como a planilha oficial, os `label` ativos em `backend/db/scoring_rules.yaml` precisam ser textos idênticos aos da coluna `Critério Avaliado` da planilha.

## Resultado executivo

Os textos ainda não estão exatamente iguais à planilha oficial.

Na comparação dos 37 alertas mapeados entre `scoring_rules.yaml` e as abas oficiais:

- Critérios ativos comparados no YAML: 480
- Critérios oficiais comparados na planilha: 477
- Critérios exatamente iguais na mesma posição: 82
- Critérios exatamente iguais em qualquer posição da mesma aba: 86
- Alertas 100% idênticos em texto e quantidade: 1 de 37

Único alerta 100% idêntico pelo texto:

- `CHECKLIST-RECEPTIVO` -> aba `Checklist`

Alertas sem nenhum critério exatamente igual ao texto oficial:

- `LOGISTICA-TABORDA` -> aba `Taborda`
- `CHECKLIST-VEICULO` -> aba `Checklist`
- `RECEPTIVO-CHATBOT` -> aba `Receptivo`

## Causa principal

O `scoring_rules.yaml` ativo usa muitos rótulos resumidos, enquanto a planilha oficial usa perguntas completas.

Exemplo em `UTI-PRIORITARIO-MOT`, aba oficial `Prioritario`:

| Campo | Texto |
| --- | --- |
| YAML ativo | `Identificação (saudação, nome, setor, empresa)?` |
| Oficial | `O operador se identificou informando saudação, nome, setor e empresa?` |

Outro exemplo:

| Campo | Texto |
| --- | --- |
| YAML ativo | `Confirmou a senha de segurança?` |
| Oficial | `O operador confirmou a senha de segurança antes de prosseguir?` |

Outro exemplo:

| Campo | Texto |
| --- | --- |
| YAML ativo | `Informou o motivo do contato?` |
| Oficial | `O operador informou claramente o motivo do contato?` |

Essa diferença é textual, não apenas visual. Mesmo quando o critério representa a mesma intenção operacional, ele não está escrito exatamente como a documentação oficial.

## Situação por alerta

| Alerta ativo | Aba oficial | Critérios YAML | Critérios oficiais | Iguais na posição |
| --- | --- | ---: | ---: | ---: |
| `UTI-PRIORITARIO-MOT` | `Prioritario` | 12 | 12 | 1 |
| `UTI-PRIORITARIO-CLI` | `C.Prioritario` | 13 | 13 | 2 |
| `UTI-POSICAO-MOT` | `Posição` | 13 | 13 | 1 |
| `UTI-POSICAO-CLI` | `C.Posição` | 15 | 15 | 2 |
| `UTI-PARADA-MOT` | `Parada` | 13 | 13 | 1 |
| `UTI-PARADA-CLI` | `C.Parada` | 14 | 14 | 2 |
| `UTI-DESVIO-MOT` | `Desvio` | 14 | 14 | 1 |
| `UTI-DESVIO-CLI` | `C.Desvio` | 15 | 15 | 2 |
| `UTI-PONTO-APOIO` | `Apoio` | 13 | 13 | 2 |
| `UTI-PRIORITARIO-POLICIA` | `Policial` | 14 | 14 | 2 |
| `BAS-PRIORITARIO-POLICIA` | `Policial` | 14 | 14 | 2 |
| `CADASTRO-ANTECEDENTES` | `Antecedente` | 12 | 12 | 1 |
| `UNILEVER-DEVOLUCAO` | `Devolução` | 14 | 14 | 2 |
| `UNILEVER-CABINETS` | `Cabinets` | 13 | 13 | 2 |
| `UNILEVER-TRATATIVA` | `Atuação` | 16 | 16 | 2 |
| `UNILEVER-DISTRIBUICAO` | `Distribuição` | 14 | 14 | 2 |
| `UNILEVER-LOSSTREE` | `Loss Tree` | 13 | 13 | 2 |
| `LOGISTICA-ESTADIA` | `Estadia` | 12 | 11 | 1 |
| `LOGISTICA-TEMPERATURA-MOT` | `Cont.Temp` | 13 | 13 | 2 |
| `LOGISTICA-TEMPERATURA-CLI` | `Cont.Temp .Clien` | 13 | 13 | 3 |
| `LOGISTICA-DESLIG-TEMP-MOT` | `Desl.Temp` | 14 | 14 | 4 |
| `LOGISTICA-DESLIG-TEMP-CLI` | `Desl.Temp.Clien` | 13 | 13 | 3 |
| `LOGISTICA-ATRASO-ENTREGA` | `Atraso` | 14 | 12 | 1 |
| `LOGISTICA-PARADA` | `Parada Indevida Logística` | 11 | 11 | 2 |
| `LOGISTICA-DESVIO` | `Desvio de Rota Logística ` | 11 | 11 | 2 |
| `LOGISTICA-ATIVACAO-AE` | `Ativação AE.Clien` | 13 | 13 | 3 |
| `LOGISTICA-ATRASO` | `Atr.Entrega.Clien` | 12 | 13 | 1 |
| `LOGISTICA-POSICAO` | `Posição em Atraso Logística` | 12 | 12 | 2 |
| `LOGISTICA-TABORDA` | `Taborda` | 9 | 9 | 0 |
| `LOGISTICA-ATRASO-INICIO` | `Atraso no Início de Viagem` | 12 | 12 | 4 |
| `MONDELEZ-LOGISTICA-REVERSA` | `Logística Reversa` | 16 | 15 | 1 |
| `MONDELEZ-MONITORAMENTO-I` | `Monitoramento I` | 15 | 15 | 2 |
| `MONDELEZ-MONITORAMENTO-II` | `Monitoramento II` | 16 | 16 | 2 |
| `CHECKLIST-VEICULO` | `Checklist` | 12 | 12 | 0 |
| `CHECKLIST-RECEPTIVO` | `Checklist` | 12 | 12 | 12 |
| `RECEPTIVO-CHATBOT` | `Receptivo` | 9 | 9 | 0 |
| `CELULA-RECEPTIVO` | `Receptivo` | 9 | 9 | 8 |

## Observações sobre arquivos gerados

Existem arquivos não rastreados `backend/db/scoring_rules_updated.yaml` e `backend/db/scoring_rules_final.yaml`, mas eles não são carregados pelo runtime atual.

Comparação rápida:

| Arquivo | Critérios comparados | Iguais na posição | Alertas 100% idênticos |
| --- | ---: | ---: | ---: |
| `backend/db/scoring_rules.yaml` | 480 | 82 | 1 |
| `backend/db/scoring_rules_updated.yaml` | 544 | 20 | 1 |
| `backend/db/scoring_rules_final.yaml` | 544 | 20 | 1 |

Assim, mesmo que esses arquivos tenham sido gerados como tentativa de correção, eles não resolvem o problema no caminho ativo e ainda parecem menos aderentes na comparação textual exata.

## Conclusão

Na branch `auditoria-casa`, os critérios exibidos na auditoria ainda não estão escritos exatamente conforme a planilha oficial.

O problema está concentrado nos `label` de `backend/db/scoring_rules.yaml`: eles foram padronizados/resumidos, mas a documentação oficial usa frases completas e específicas. Como o frontend exibe diretamente `item.label`, qualquer divergência nesse YAML aparece no resultado da auditoria.

## Recomendação

Corrigir o `backend/db/scoring_rules.yaml` ativo usando a coluna `Critério Avaliado` da planilha oficial como fonte literal dos labels.

Após a correção:

- manter o mesmo mapeamento de alerta para aba oficial;
- validar quantidade de critérios por alerta;
- validar texto exato por posição;
- só então sincronizar o banco, pois `database.py` agora força o banco a refletir o YAML quando o hash muda.

Critério mínimo de aceite recomendado:

- 37 alertas mapeados;
- 100% dos `label` ativos iguais ao texto oficial correspondente;
- nenhuma dependência runtime apontando para `scoring_rules_updated.yaml` ou `scoring_rules_final.yaml` sem decisão explícita.
