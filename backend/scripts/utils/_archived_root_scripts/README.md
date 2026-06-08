# Scripts orfaos da raiz do projeto - arquivados em 2026-05-26

Estes scripts ficavam na raiz do repo (`C:\Users\lucas.afonso\projetos\auditoria\`) sem fazer parte da estrutura oficial. Foram arquivados aqui para preservar historico.

**AVISO: nenhum deles funciona sem ajuste manual.** Os imports usam o layout pre-refactor MIT (`import database` direto, sem o prefixo `db.`).

## Conteudo

| Arquivo | Origem | Estado |
|---|---|---|
| `check_cycle.py` | Debug do ciclo de automacao (`automation_cycle_runs`, `huawei_d_minus_1_runs`) | Quebrado: `import database` -> precisaria virar `from db import database` |
| `check_huawei_telemetry.py` | Debug dos eventos `huawei_telemetry_events` + schema `transcript_candidates` | Mesmo problema acima |
| `fix_quotes.py` | Script ad-hoc usado durante o refactor MIT para corrigir aspas em `patch(...)` em testes | Uso unico, ja executado |
| `refactor_imports.py` | Script ad-hoc usado para mover imports `import X` -> `import core.X as X` etc | Uso unico, ja executado |

Se precisar reativar `check_cycle.py` ou `check_huawei_telemetry.py`, mover para `backend/scripts/` e ajustar `import database` para `from db import database`. Ou usar os equivalentes ja existentes em `backend/scripts/check_queue.py` e `backend/scripts/check_recent_audits.py` que ja seguem o layout novo.
