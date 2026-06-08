# Relatorio de Correcao - Modulo Automacao

Data: 2026-05-09

## Escopo

Correcao dos achados de revisao do modulo de automacao:

- lock distribuido ausente no loop residente;
- status `is_running` misturando loop vivo com ciclo ativo;
- cota mensal configuravel ignorada na fase de auditoria;
- intervalo invalido encerrando o loop residente.

## Correcoes Aplicadas

1. O advisory lock distribuido foi movido para `automation_engine.run_automation_cycle()`.
   - O mesmo bloqueio agora cobre Cloud Scheduler, disparo manual e loop residente.
   - O router deixou de adquirir lock proprio para evitar auto-bloqueio.

2. O status do motor agora separa loop residente de ciclo ativo.
   - `is_resident_loop_running` indica a task residente viva.
   - `is_cycle_running` e `is_running` indicam ciclo realmente ativo.

3. A auditoria em lote passou a respeitar `huawei_cota_max_por_operador_mes`.
   - O limite deixou de ser fixo em `2`.
   - Metadados de bloqueio mensal agora registram `monthly_cap_limit`.

4. O intervalo `automacao_intervalo_segundos` agora tem fallback seguro.
   - Valores invalidos voltam para `600` segundos.
   - Valores menores que `1` sao normalizados para `1`.

## Validacao

Comando executado:

```text
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_automation_cron.py backend/tests/test_automation_control_state.py backend/tests/test_telefonia_router.py -q
```

Resultado:

```text
21 passed
```

Observacao: a venv local emitiu o aviso conhecido de `distutils-precedence.pth`, sem impacto nos testes.

