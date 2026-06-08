# Relatorio de Configuracao Atual das Regras - GRS/UTI, BAS e Receptivas

Data da leitura: 18/05/2026  
Escopo: regras de setor, criterios de auditoria, aliases de setor e bloqueios de ligacoes receptivas na integracao Huawei.

## Resumo executivo

A configuracao atual separa `uti` e `bas` no banco, mas ainda existem pontos que podem fazer a operacao perceber GRS/UTI e BAS como uma mesma familia de auditoria:

- `uti` esta descrito como "UTI (antigo GRS)" e recebe todos os 10 alertas operacionais 4.1.x.
- `bas` existe como setor separado, mas hoje possui somente 1 alerta no banco: `BAS-PRIORITARIO-POLICIA`.
- Os demais alertas de risco de BAS por nome de arquivo (`PARADA`, `DESVIO`, `POSICAO`, `PRIORITARIO`) ainda apontam para IDs `UTI-*` em `classification.py`, exceto policia.
- O catalogo em memoria ainda replica alertas de `bas` para setores irmaos operacionais, o que mistura a exposicao dos alertas no prompt/catálogo.
- Ha um setor `uti_rj` cadastrado no banco, mas sem alertas e sem aliases apontando para ele; as escalas `RJ` continuam caindo em `uti`.

Sobre receptivas: no caminho Huawei com metadata correta, a regra atual bloqueia receptivas dos setores de risco (`uti`, `bas`, `distribuicao`, `fenix`, `transferencia`). A telemetria confirma bloqueios recentes. Porem a direcao esperada nao esta parametrizada no banco (`expected_direction` esta vazio para todos os 77 alertas), e ha caminhos em que a direcao apenas vira motivo de revisao, sem bloqueio automatico.

## Fontes verificadas

- Banco ativo carregado pelo `.env`: Neon `sa-east-1`, banco `neondb` (credenciais omitidas).
- Tabelas consultadas em modo somente leitura: `audit_sectors`, `audit_alerts`, `audit_criteria`, `sector_aliases`, `colaboradores`, `huawei_sync_logs`, `fila_revisao_classificacao`.
- Codigo revisado:
  - `backend/core/huawei_direction.py`
  - `backend/core/huawei_sync.py`
  - `backend/core/automation_rules.py`
  - `backend/automation.py`
  - `backend/classification.py`
  - `backend/audit_evaluator.py`
  - `backend/database.py`
  - `backend/repositories/admin_criteria.py`
  - `backend/db/scoring_loader.py`

## Estado atual no banco

### Setores relevantes

| Setor | Label | Observacao |
|---|---|---|
| `uti` | UTI | Descricao: "Setor de rastreamento - UTI (antigo GRS)" |
| `bas` | BAS | Descricao: "Base de Sinistros" |
| `uti_rj` | UTI - RJ | Existe no banco, mas nao tem alertas vinculados |
| `receptivo` | Receptivo | Existe como setor oficial de auditoria |

### Alertas por setor

| Setor | Qtde de alertas | Direcao esperada preenchida |
|---|---:|---:|
| `uti` | 10 | 0 |
| `bas` | 1 | 0 |
| `transferencia` | 10 | 0 |
| `distribuicao` | 10 | 0 |
| `fenix` | 10 | 0 |
| `bbm` | 10 | 0 |
| total do catalogo | 77 | 0 |

Alertas de `uti`:

- `UTI-PRIORITARIO-MOT`
- `UTI-PRIORITARIO-CLI`
- `UTI-POSICAO-MOT`
- `UTI-POSICAO-CLI`
- `UTI-PARADA-MOT`
- `UTI-PARADA-CLI`
- `UTI-DESVIO-MOT`
- `UTI-DESVIO-CLI`
- `UTI-PONTO-APOIO`
- `UTI-PRIORITARIO-POLICIA`

Alertas de `bas`:

- `BAS-PRIORITARIO-POLICIA`

Todos os alertas UTI/BAS consultados possuem criterios somando 10 pontos.

### Operadores auditaveis por setor bruto

| Setor bruto | Escala | Total auditavel |
|---|---|---:|
| BAS | sem escala | 1 |
| BAS | Amarela | 16 |
| BAS | Azul | 17 |
| BAS | Cinza | 17 |
| BAS | Verde | 19 |
| UTI | Amarela | 5 |
| UTI | Azul | 8 |
| UTI | Cinza | 6 |
| UTI | Verde | 6 |
| UTI | RJ - Amarela | 2 |
| UTI | RJ - Azul | 2 |
| UTI | RJ - Cinza | 1 |
| UTI | RJ - Verde | 1 |

Leitura: o cadastro de colaboradores ja separa BAS e UTI, mas `UTI RJ` ainda esta dentro do setor bruto `UTI` por escala, nao no setor canonico `uti_rj`.

### Aliases de setor

Regras ativas relevantes em `sector_aliases`:

| Regra | Valor | Canonico | Prioridade | Impacto |
|---|---|---|---:|---|
| `setor_startswith` | `uti` | `uti` | 900 | UTI por cor cai em `uti` |
| `setor_startswith` | `rj` | `uti` | 900 | RJ cai em `uti`, nao em `uti_rj` |
| `setor_startswith` | `bas` | `bas` | 900 | BAS por cor/base cai em `bas` |
| `setor_exact` | `grs` | `uti` | 200 | GRS legado cai em UTI |
| `setor_exact` | `sinistro`/`sinistros` | `bas` | 200 | Sinistro cai em BAS |
| `organizacao_contains` | `base de sinistro` | `bas` | 700 | Organizacao Huawei cai em BAS |
| `setor_contains` / `setor_exact` | `receptivo` | `celula_atendimento` | 810/200 | Receptivo cru nao cai no setor DB `receptivo` |
| `setor_contains` / `escala_contains` | `celula` | `celula_atendimento` | 820 | Celula cai em `celula_atendimento` |

Observacao importante: `celula_atendimento` nao existe em `audit_sectors`; o banco tem `receptivo`. O codigo preserva `celula_atendimento` como setor nao-telefonia. Isso e uma divergencia historica ja documentada no projeto e pode confundir o fluxo de Receptivo.

Nao ha registros em `sector_aliases_audit_log`, `audit_sectors_audit_log`, `audit_alerts_audit_log` ou `audit_criteria_audit_log`; ou seja, apos a migracao de audit log, nao encontrei edicoes administrativas registradas nessas regras.

## Estado atual no codigo

### Bloqueio de receptivas Huawei

`backend/core/huawei_direction.py:15` define setores de risco que aceitam somente ligacao ativa:

```text
{"uti", "bas", "distribuicao", "fenix", "transferencia"}
```

`backend/core/huawei_sync.py:325` aplica o bloqueio antes do download/enfileiramento:

- setor de risco + direcao desconhecida -> `direction_unknown`
- setor de risco + receptiva -> `risk_inbound`
- setor desconhecido + receptiva -> `receptiva_setor_desconhecido`
- setor de risco + ativa -> aceita

`backend/automation.py:211` reaplica bloqueio na fila antes da auditoria automatica:

- `receptiva_setor_risco`
- `receptiva_pretriagem_audio`
- `direcao_desconhecida_setor_risco`
- `setor_nao_telefonia`

Conclusao: para Huawei com metadata de direcao correta, UTI/BAS receptiva deve ser bloqueada. O ponto fraco e que essa regra esta hardcoded e nao vem de `audit_alerts.expected_direction`.

### Regras da automacao

`backend/core/automation_rules.py` configura:

| Setor | Direcao | Acao |
|---|---|---|
| `transferencia` | `OUTBOUND` | `process_voice_random` |
| `uti` | `OUTBOUND` | `process_voice_random` |
| `bas` | `OUTBOUND` | `process_voice_random` |
| `distribuicao` | `OUTBOUND` | `process_voice_random` |
| `fenix` | `OUTBOUND` | `process_voice_random` |
| `receptivo` | sem direcao fixa | `generate_pdf_and_process` |
| `cadastro`, `logistica`, `logistica_unilever` | sem direcao fixa | `process_voice` |

Gap: `bbm` tem criterios e alertas no catalogo, mas nao aparece em `AUTOMATION_RULES` nem no conjunto `OUTBOUND_ONLY_RISK_SECTORS`. Se BBM tambem for area de risco, hoje pode passar fora do bloqueio de receptivas.

### Prompt e criterios da auditoria

`backend/audit_evaluator.py` separa regras de prompt por setor:

- `uti`: "Ligacao Efetuada (Motorista ou Cliente)"
- `bas`: "Ligacao Efetuada (Policia / Ponto de Apoio)"
- ambos entram em `PASSWORD_RULE_SECTORS`, entao recebem regra de senha/zeragem quando o criterio envolve senha.

Isso reforca que BAS foi modelado como um recorte mais estreito que UTI/GRS, nao como um espelho completo de UTI.

### Catalogo de classificacao e possivel mistura BAS/UTI

`backend/classification.py` ainda possui pontos de mistura:

1. `_apply_operational_siblings` replica alertas de `bas` para setores operacionais irmaos. Como `bas` tem apenas `BAS-PRIORITARIO-POLICIA`, esse alerta pode aparecer tambem nos setores operacionais.
2. `_FILENAME_ALERT_MAP` mapeia arquivos BAS de `POSICAO`, `PARADA`, `DESVIO` e `PRIORITARIO` para alertas `UTI-*`, enquanto apenas `POLICIA/POLICIAL` aponta para `BAS-PRIORITARIO-POLICIA`.
3. O prompt textual diz que "UTI refere-se a GRS" e que "BAS e a base de monitoramento principal", mas o catalogo de BAS nao tem a familia completa de alertas.
4. `_expected_direction_for_alert` detecta direcao por palavras no `alert_id`, mas apenas marca `direction_mismatch` para revisao; nao bloqueia a auditoria.

## Evidencia operacional recente

Telemetria em `huawei_sync_logs`:

| Motivo | Total historico observado | Ultimo registro |
|---|---:|---|
| `direcao_desconhecida` | 18.197 | 17/05/2026 |
| `setor_nao_telefonia` | 3.978 | 17/05/2026 |
| `receptiva_setor_desconhecido` | 2.726 | 17/05/2026 |
| `receptiva_setor_risco` | 476 | 17/05/2026 |
| `direcao_incompativel` | 23 | 11/05/2026 |

Na fila `fila_revisao_classificacao`, no momento da leitura:

- nao havia item Huawei de setor de risco com `huawei_is_call_in=true`;
- havia 1 item `uti` auditado com `huawei_is_call_in=false` e pre-triagem de direcao `unknown`.

Interpretacao: o bloqueio de receptivas no sync esta ativo. Se houver receptivas sendo auditadas, os caminhos mais provaveis sao:

- ligacao entrou sem metadata Huawei suficiente para acionar o bloqueio;
- setor foi resolvido para um slug fora do conjunto de risco;
- caminho manual/classificacao nao-Huawei, onde a direcao vira revisao e nao bloqueio;
- setor `bbm`, que hoje tem criterios mas nao esta no gate de risco;
- divergencia `receptivo` vs `celula_atendimento`.

## Pontos de desalinhamento para decisao operacional

1. **GRS deve continuar como `uti`?**  
   Hoje `grs` e `rj` caem em `uti`. Se a separacao operacional exige um setor proprio (`grs`, `uti_rj` ou outro), e necessario criar alertas/criterios e ajustar aliases.

2. **BAS deve ter apenas acionamento policial ou a familia completa 4.1.x?**  
   Hoje BAS so tem `BAS-PRIORITARIO-POLICIA`. Se BAS deve auditar parada, desvio, posicao, prioritario motorista/cliente etc. com regra propria, faltam alertas `BAS-*` no banco.

3. **Receptivas de areas de risco devem ser bloqueadas em todos os caminhos?**  
   Huawei sync/automacao bloqueiam, mas a classificacao geral apenas marca mismatch. Se a regra for absoluta, o bloqueio precisa ser centralizado tambem no fluxo de classificacao/auditoria manual.

4. **`expected_direction` deve virar fonte oficial.**  
   A coluna existe desde a migration `m20260518_002`, mas esta vazia em todos os 77 alertas. Hoje a direcao esperada esta distribuida entre `AUTOMATION_RULES`, keywords do `alert_id` e gates hardcoded.

5. **Resolver `receptivo` vs `celula_atendimento`.**  
   O banco tem setor `receptivo`; aliases apontam para `celula_atendimento`; o codigo trata `celula_atendimento` como nao-telefonia. E preciso decidir um unico id canonico.

6. **Decidir o status de `bbm`.**  
   BBM tem alertas e criterios, mas nao esta no gate de direcao nem na automacao. Se for setor de risco, deve entrar em `OUTBOUND_ONLY_RISK_SECTORS` e `AUTOMATION_RULES`.

## Recomendacao tecnica para alinhamento

Ordem sugerida:

1. Validar com operacao a matriz oficial: setor canonico, aliases permitidos, alertas aplicaveis e direcao permitida.
2. Preencher `audit_alerts.expected_direction` para todos os alertas.
3. Alterar o sync, a fila e a classificacao para consultarem `expected_direction`/setor canonico em vez de regras hardcoded.
4. Ajustar BAS: ou manter apenas `BAS-PRIORITARIO-POLICIA`, ou criar os alertas BAS completos se a operacao exigir auditoria separada.
5. Remover ou parametrizar a replicacao de alertas BAS para setores irmaos.
6. Corrigir aliases `grs`, `rj`, `receptivo/celula` conforme decisao oficial.
7. Adicionar testes de regressao cobrindo:
   - GRS/UTI nao cai em BAS;
   - BAS nao cai em UTI para alertas nao policiais;
   - receptiva de UTI/BAS/BBM e bloqueada;
   - direcao desconhecida em area de risco nao audita automaticamente;
   - Receptivo/Celula usa um unico id canonico.

