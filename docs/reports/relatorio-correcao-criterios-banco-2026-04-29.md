# Relatório - Correção dos critérios de auditoria e sincronização do banco

Data: 2026-04-29
Branch analisada: `auditoria-casa`

## Resumo executivo

Foi confirmada a divergência entre o catálogo preservado no banco e a documentação oficial em `auditoria_criterios/`. O banco foi usado como referência de segurança e rollback, mas a fonte de verdade dos critérios foi mantida na planilha oficial `auditoria_criterios/criterios_pesos/CRITÉRIOS - PESOS -.xlsm`.

O catálogo foi reconstruído em `backend/db/scoring_rules.yaml` a partir da planilha oficial, preservando os alertas ativos do sistema e substituindo os critérios, pesos e descrições pelos dados oficiais. Os critérios de identificação que continham `saudação, nome, setor e empresa` foram fracionados em:

- `Saudação?`
- `Nome?`
- `Setor/Empresa?`

O peso total oficial do critério fracionado foi preservado.

## Backup antes da sincronização

Antes de alterar o banco, foi salvo um snapshot local do catálogo anterior em:

`backend/db/backup_criteria_20260429_173506/criteria_catalog_snapshot.json`

Estado anterior preservado:

- Setores: 13
- Alertas: 37
- Critérios: 544
- Hash do catálogo anterior no banco: `308fc2e43b80cda4`

## Correções aplicadas

Arquivos principais alterados:

- `backend/db/scoring_rules.yaml`
- `backend/db/scoring_loader.py`
- `backend/database.py`
- `scripts/generate_scoring_rules_from_official_workbook.py`

Correções relevantes:

- `scoring_rules.yaml` foi regenerado da planilha oficial.
- Foram gerados 37 alertas ativos.
- Foram gerados 535 critérios após o fracionamento.
- Foram fracionados 29 critérios oficiais de identificação com saudação.
- Todos os alertas ativos somam 10.00 pontos.
- O `deflator` padrão foi corrigido para `0.0` quando não informado no YAML.
- O fallback de seed no banco também foi corrigido para `deflator = 0.0`.

## Validação contra a planilha oficial

Resultado da validação estrutural:

- Erros no YAML: 0
- Alertas ativos: 37
- Critérios no YAML: 535
- Alertas com total diferente de 10.00: 0
- Grupos de identificação fracionados: 29
- Pares não fracionados comparados com a planilha: 448
- Pares não fracionados com texto e peso exatamente iguais à planilha: 448
- Problemas encontrados na comparação: 0

Exemplos conferidos:

- `UTI-PRIORITARIO-MOT`: identificação fracionada em `0.10 + 0.10 + 0.10`, mantendo o total oficial de `0.30`.
- `CHECKLIST-RECEPTIVO`: 12 critérios, total `10.00`, pesos oficiais aplicados.
- `CELULA-RECEPTIVO`: 9 critérios, total `10.00`, pesos oficiais aplicados.
- `LOGISTICA-PARADA`: critério oficial sem saudação mantido sem fracionamento.

## Sincronização do banco

Após o backup, as tabelas de catálogo foram sincronizadas pelo seed controlado a partir do YAML corrigido.

Estado após sincronização:

- Hash do YAML: `8b513e6a5b65357c`
- Hash salvo no banco: `8b513e6a5b65357c`
- Alertas no banco: 37
- Critérios no banco: 535
- Alertas com contagem ou total divergente do YAML: 0
- O banco ainda possui o setor legado `uti_rj`, sem vínculo com alertas ativos. Ele foi mantido para evitar remoção de dado legado fora do escopo da correção.

## Testes executados

Comandos executados:

```powershell
$env:PYTHONIOENCODING='utf-8'; python backend/db/scoring_loader.py
pytest backend/tests/test_scoring_loader_validation.py backend/tests/test_audit_evaluator_payloads.py backend/tests/test_audit_zeroing_rules.py -q
```

Resultado:

- YAML carregado com sucesso.
- `5 passed`.
- Houve apenas aviso de cache do pytest no Windows e um `DeprecationWarning` de dependência externa, sem falha funcional.

## Observações

O banco não deve ser usado como fonte oficial dos critérios, porque estava preservando o estado antigo funcional, mas desalinhado com a documentação oficial. O banco agora está sincronizado com o YAML corrigido, e o YAML foi gerado a partir da planilha oficial centralizada em `auditoria_criterios/`.

Para futuras mudanças de critérios, o procedimento recomendado é:

1. Atualizar a documentação oficial em `auditoria_criterios/`.
2. Executar `python scripts/generate_scoring_rules_from_official_workbook.py`.
3. Validar que todos os alertas somam 10.00.
4. Fazer backup/snapshot do catálogo do banco.
5. Sincronizar o seed de critérios.
6. Conferir o hash `scoring_rules.yaml_hash` no banco.
