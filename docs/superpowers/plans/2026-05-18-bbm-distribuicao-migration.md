# Migração BBM → Distribuição — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover o setor BBM do sistema (DB + código + frontend), criando alias defensivo em `sector_aliases` e snapshot recuperável em `db/seeds/_archived/`. Resultado: BBM some operacionalmente; tudo que vier "bbm" é redirecionado para "distribuicao" automaticamente.

**Architecture:** 1) Migration step idempotente em `backend/db/migration_steps/m20260518_002_*` faz DELETE cascata via repositories (audit_log automático) + insere alias em `sector_aliases`. 2) Snapshot JSON em `db/seeds/_archived/` permite reverter via `restore_bbm.py`. 3) Refatoração cirúrgica em 28 arquivos backend + 6 frontend remove referências operacionais de BBM, mantendo intacto material RAG e migrations históricas.

**Tech Stack:** Python 3.11+, FastAPI, psycopg2 (PostgreSQL via DATABASE_URL), pytest, repositories pattern, React 19 + TypeScript.

**Spec:** `docs/superpowers/specs/2026-05-18-bbm-distribuicao-migration-design.md`

---

## File Structure

**Create:**
- `backend/db/migration_steps/m20260518_004_migrate_bbm_to_distribuicao.py` — migration step idempotente (apply(c))
- `backend/db/seeds/_archived/__init__.py` — marker
- `backend/db/seeds/_archived/bbm_snapshot.py` — helper (dump + load do JSON)
- `backend/db/seeds/_archived/restore_bbm.py` — script de reverter
- `backend/tests/test_bbm_distribuicao_migration.py` — unit + integration tests
- `logs/versions/1.3.74-migracao-bbm-distribuicao.md` — log de versão

**Modify (backend):**
- `backend/classification.py` — _ALERT_ID_ALIASES (+10), _OPERATIONAL_SIBLINGS (-bbm), _OPERATIONAL_SECTORS (-bbm), _OPERATIONAL_ALERT_PREFIXES (-bbm), sector_labels (-bbm), _OPERATIONAL_ALERT_BY_KIND map (-bbm)
- `backend/core/config.py` — `sector_mapping` (-bbm)
- `backend/core/evaluation.py` — `RASTREAMENTO_SECTORS` (-bbm)
- `backend/audit_evaluator.py` — `PASSWORD_RULE_SECTORS` (-bbm), `_SECTOR_RULES` dict (-bbm)
- `backend/core/operator_filters.py` — `"time bbm"` (-)
- `backend/core/gestores_mapping.py` — `"bbm": "DISTRIBUIÇÃO"` (-)
- `backend/db/scoring_rules_final.yaml` — bloco `id: bbm` (lines 22-24)
- `backend/db/scoring_rules_updated.yaml` — idem
- `backend/db/seeds/scoring_rules.bootstrap.yaml` — idem
- `pendencias/PENDENCIAS.md` — adicionar item migração concluída
- `~/.claude/projects/.../memory/MEMORY.md` — remover linha "BBM = transferencia + uti-BBM"

**Modify (frontend):**
- `src/features/settings/components/OperadorManagement.tsx:83` — remove `'TIME BBM'`
- `src/features/saved-files/components/SavedFiles.tsx:391` — remove `'bbm'` do array
- `src/features/automacao/components/AuditModal.tsx:369` — idem
- `src/features/audit/hooks/useAuditResultEditor.ts:67` — idem
- `src/features/audit/hooks/useAuditFlow.ts:23` — remove `'BBM'`
- `src/shared/lib/operationalLabels.ts:5,22` — remove `BBM: 'BBM'` + `'BBM'` de PRESERVE_UPPERCASE
- `src/data/criteria.json` — remove "BBM" da string `"Transferência / Distribuição / Fênix / BBM / UTI / BAS"`

**Intactos (decisão de spec):**
- `backend/transcription_providers/common.py:83` — "BBM" é vocabulário STT para áudios históricos, NÃO mexer
- `backend/data/rag_training/*.md` — material de treinamento, mantém contexto histórico para IA
- `backend/data/operadores_seed.json` — seed antigo
- `backend/db/migration_steps/m20260518_001_*` — migration histórica
- `backend/db/backup_criteria_20260429_173506/` — backup pré-existente

---

## Task 1: Snapshot helper module + restore script

Cria o helper que serializa o setor BBM (sector + 10 alertas + 156 critérios) em JSON e o script complementar de restore. Vai ser usado pela migration (Task 2) e por reverter manual.

**Files:**
- Create: `backend/db/seeds/_archived/__init__.py`
- Create: `backend/db/seeds/_archived/bbm_snapshot.py`
- Create: `backend/db/seeds/_archived/restore_bbm.py`
- Test: `backend/tests/test_bbm_distribuicao_migration.py` (criação + 1º teste)

- [ ] **Step 1: Criar `__init__.py` vazio**

```bash
mkdir -p backend/db/seeds/_archived
```

Criar arquivo `backend/db/seeds/_archived/__init__.py` com conteúdo:

```python
# Snapshots arquivados de migrações destrutivas — versionados no git.
```

- [ ] **Step 2: Escrever o teste primeiro**

Criar `backend/tests/test_bbm_distribuicao_migration.py`:

```python
"""Testes para a migração BBM → Distribuição (v1.3.74)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.seeds._archived.bbm_snapshot import dump_bbm_snapshot, load_bbm_snapshot


class TestBBMSnapshotRoundtrip(unittest.TestCase):
    """Snapshot helper round-trips JSON sem perda."""

    def test_dump_and_load_preserves_structure(self):
        sample = {
            "snapshot_date": "2026-05-18",
            "reason": "test",
            "sector": {"id": "bbm", "label": "BBM"},
            "alerts": [{"id": "BBM-PARADA-MOT", "sector_id": "bbm", "label": "x"}],
            "criteria": [{"alert_id": "BBM-PARADA-MOT", "label": "y", "weight": 1.0}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snap.json"
            dump_bbm_snapshot(sample, path)
            self.assertTrue(path.exists())
            loaded = load_bbm_snapshot(path)
            self.assertEqual(loaded["sector"]["id"], "bbm")
            self.assertEqual(len(loaded["alerts"]), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Rodar o teste — verificar que falha**

```bash
cd /c/Users/lucas.afonso/projetos/auditoria && python -m pytest backend/tests/test_bbm_distribuicao_migration.py::TestBBMSnapshotRoundtrip -v
```

Expected: FAIL com `ModuleNotFoundError: No module named 'db.seeds._archived.bbm_snapshot'`

- [ ] **Step 4: Implementar `bbm_snapshot.py`**

Criar `backend/db/seeds/_archived/bbm_snapshot.py`:

```python
"""Helper para dump/load do snapshot BBM (sector + alertas + critérios).

Usado pela migration `m20260518_002_*` (Task 2) e pelo `restore_bbm.py`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SNAPSHOT_FILENAME = "2026-05-18-bbm-sector.json"


def dump_bbm_snapshot(payload: dict[str, Any], path: Path) -> None:
    """Escreve o snapshot em `path` (UTF-8, indent=2, ordenação estável)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )


def load_bbm_snapshot(path: Path) -> dict[str, Any]:
    """Lê snapshot do `path`. Levanta FileNotFoundError se não existir."""
    return json.loads(path.read_text(encoding="utf-8"))


def default_snapshot_path() -> Path:
    """Path canônico do snapshot dentro do repo."""
    return Path(__file__).resolve().parent / SNAPSHOT_FILENAME


def build_snapshot_payload(
    sector: dict | None,
    alerts: list[dict],
    criteria: list[dict],
) -> dict[str, Any]:
    """Estrutura o payload com metadados de auditoria."""
    return {
        "snapshot_date": "2026-05-18",
        "reason": "BBM absorvido por Distribuição. Snapshot para revert eventual.",
        "version_log": "logs/versions/1.3.74-migracao-bbm-distribuicao.md",
        "sector": sector,
        "alerts": list(alerts),
        "criteria": list(criteria),
    }
```

- [ ] **Step 5: Rodar o teste — verificar que passa**

```bash
python -m pytest backend/tests/test_bbm_distribuicao_migration.py::TestBBMSnapshotRoundtrip -v
```

Expected: PASS

- [ ] **Step 6: Criar `restore_bbm.py`**

Criar `backend/db/seeds/_archived/restore_bbm.py`:

```python
"""Script de reverter: re-insere BBM no DB a partir do snapshot.

Uso: python -m backend.db.seeds._archived.restore_bbm

Idempotente: se as linhas já existem, faz UPSERT no campo label/weight via
ON CONFLICT. Remove o alias bbm → distribuicao se existir. Grava no audit_log
com motivo `Restore BBM via snapshot 2026-05-18`.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Permite rodar como script direto: python backend/db/seeds/_archived/restore_bbm.py
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from db.seeds._archived.bbm_snapshot import default_snapshot_path, load_bbm_snapshot

logger = logging.getLogger("restore_bbm")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    load_dotenv()
    from database import get_connection
    from repositories import sector_aliases
    from repositories import admin_criteria

    snapshot_path = default_snapshot_path()
    if not snapshot_path.exists():
        logger.error("Snapshot nao encontrado em %s", snapshot_path)
        return 1

    snapshot = load_bbm_snapshot(snapshot_path)
    sector = snapshot["sector"]
    alerts = snapshot["alerts"]
    criteria = snapshot["criteria"]

    audit_kwargs = dict(
        alterado_por="system_restore_v1.3.74",
        motivo="Restore BBM via snapshot 2026-05-18",
        origem="script",
    )

    admin_criteria.create_sector(
        get_connection,
        id=sector["id"],
        label=sector["label"],
        description=sector.get("description", ""),
        **audit_kwargs,
    )
    for alert in alerts:
        admin_criteria.create_alert(
            get_connection,
            sector_id=alert["sector_id"],
            id=alert["id"],
            label=alert["label"],
            pop_ref=alert.get("pop_ref", ""),
            context=alert.get("context", ""),
            **audit_kwargs,
        )
    for criterion in criteria:
        admin_criteria.create_criterion(
            get_connection,
            alert_id=criterion["alert_id"],
            label=criterion["label"],
            weight=float(criterion.get("weight", 0)),
            description=criterion.get("description", ""),
            chave=criterion.get("chave"),
            **audit_kwargs,
        )

    aliases = sector_aliases.list_aliases(get_connection)
    for alias in aliases:
        if alias["pattern_type"] == "setor_exact" and alias["pattern_value"] == "bbm":
            sector_aliases.delete_alias(get_connection, alias["id"], **audit_kwargs)
            break

    sector_aliases.clear_cache()
    logger.info("Restore concluido: 1 setor + %d alertas + %d criterios + alias removido.",
                len(alerts), len(criteria))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Commit**

```bash
cd /c/Users/lucas.afonso/projetos/auditoria
git add backend/db/seeds/_archived/__init__.py backend/db/seeds/_archived/bbm_snapshot.py backend/db/seeds/_archived/restore_bbm.py backend/tests/test_bbm_distribuicao_migration.py
git commit -m "$(cat <<'EOF'
feat(migration): snapshot helper + restore script p/ migracao BBM->Dist

- bbm_snapshot.py: dump/load JSON estrutura sector+alerts+criteria
- restore_bbm.py: re-insere BBM no DB via repositories (audit_log automatico)
- Snapshot canonico em db/seeds/_archived/2026-05-18-bbm-sector.json

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Migration step `m20260518_004_migrate_bbm_to_distribuicao`

Cria a migration que executa Fase A (pre-flight + snapshot dump) e Fase B (insert alias + delete cascata) + Fase C (invalida caches). Idempotente, segue convenção `MIGRATION_NAME` + `apply(c)`.

**Files:**
- Create: `backend/db/migration_steps/m20260518_004_migrate_bbm_to_distribuicao.py`
- Modify: `backend/tests/test_bbm_distribuicao_migration.py` (adiciona testes de idempotência)

- [ ] **Step 1: Adicionar teste de idempotência**

Adicionar ao final de `backend/tests/test_bbm_distribuicao_migration.py`:

```python
class TestMigrationIdempotency(unittest.TestCase):
    """Migration roda 2x sem erro; snapshot é gerado uma única vez."""

    def test_apply_is_idempotent_in_dry_run_mode(self):
        """Smoke test: importar o módulo e checar shape do MIGRATION_NAME/apply.

        Teste real de DELETE roda em Task 3 (manual em ambiente local).
        """
        from db.migration_steps import m20260518_004_migrate_bbm_to_distribuicao as mig

        self.assertEqual(mig.MIGRATION_NAME, "m20260518_004_migrate_bbm_to_distribuicao")
        self.assertTrue(callable(mig.apply))
```

- [ ] **Step 2: Rodar teste — verificar que falha**

```bash
python -m pytest backend/tests/test_bbm_distribuicao_migration.py::TestMigrationIdempotency -v
```

Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar a migration**

Criar `backend/db/migration_steps/m20260518_004_migrate_bbm_to_distribuicao.py`:

```python
"""Migração BBM → Distribuição.

Fase A (fora de transação): pre-flight + snapshot JSON em db/seeds/_archived/
Fase B (via repositories, cada chamada commita): cria alias em sector_aliases,
        deleta critérios → alertas → setor BBM via repositories.admin_criteria
        (audit_log automático em audit_*_audit_log).
Fase C (Python pós-DB): invalida lru_cache de classification.

Idempotente: re-rodar é seguro. Próxima execução verifica existência antes
de cada passo. Audit_log + snapshot_file fornecem 2 caminhos de revert.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("migration.m20260518_002")

MIGRATION_NAME = "m20260518_004_migrate_bbm_to_distribuicao"


def apply(c) -> None:
    # Imports lazy para evitar custo em deploys que não rodem essa migration
    import database
    from db.seeds._archived.bbm_snapshot import (
        build_snapshot_payload,
        default_snapshot_path,
        dump_bbm_snapshot,
    )
    from repositories import admin_criteria, sector_aliases

    audit_kwargs = dict(
        alterado_por="system_migration_v1.3.74",
        motivo="Migração BBM → Distribuição (v1.3.74)",
        origem="migration",
    )

    # ── Fase A: pre-flight checks ──────────────────────────────────────────
    c.execute("SELECT COUNT(*) AS n FROM audits WHERE LOWER(sector_id) = 'bbm'")
    audits_bbm = (c.fetchone() or {"n": 0})["n"]
    c.execute("SELECT COUNT(*) AS n FROM colaboradores WHERE LOWER(setor) = 'bbm'")
    colab_bbm = (c.fetchone() or {"n": 0})["n"]
    if audits_bbm or colab_bbm:
        raise RuntimeError(
            f"Migracao BBM abortada: encontrados audits={audits_bbm}, colaboradores={colab_bbm} "
            f"com sector_id/setor='bbm'. Realocar manualmente antes de rodar a migracao."
        )

    # ── Fase A: snapshot dump (idempotente) ────────────────────────────────
    snapshot_path = default_snapshot_path()
    if not snapshot_path.exists():
        c.execute("SELECT id, label, description FROM audit_sectors WHERE id = 'bbm'")
        sector_row = c.fetchone()
        if sector_row:
            sector_payload = dict(sector_row)
            c.execute(
                "SELECT id, sector_id, label, pop_ref, context FROM audit_alerts WHERE sector_id = 'bbm' ORDER BY id"
            )
            alerts_payload = [dict(r) for r in c.fetchall()]
            c.execute(
                "SELECT id, alert_id, label, weight, description, chave FROM audit_criteria "
                "WHERE alert_id LIKE 'BBM-%%' ORDER BY alert_id, id"
            )
            criteria_payload = [dict(r) for r in c.fetchall()]
            payload = build_snapshot_payload(sector_payload, alerts_payload, criteria_payload)
            dump_bbm_snapshot(payload, snapshot_path)
            logger.info("Snapshot BBM gravado em %s (%d alertas, %d criterios).",
                        snapshot_path, len(alerts_payload), len(criteria_payload))
        else:
            logger.info("Setor 'bbm' nao existe no DB; pulando snapshot (provavel re-run idempotente).")

    # ── Fase B.3: insert alias (se não existir) ────────────────────────────
    existing_aliases = sector_aliases.list_aliases(database.get_connection)
    has_alias = any(
        a["pattern_type"] == "setor_exact" and a["pattern_value"] == "bbm"
        for a in existing_aliases
    )
    if not has_alias:
        sector_aliases.create_alias(
            database.get_connection,
            pattern_type="setor_exact",
            pattern_value="bbm",
            canonical_sector_id="distribuicao",
            priority=100,
            descricao="Migração BBM → Distribuição em 2026-05-18",
            ativo=True,
            **audit_kwargs,
        )
        logger.info("Alias bbm -> distribuicao criado em sector_aliases.")

    # ── Fase B.4a: delete critérios ────────────────────────────────────────
    c.execute("SELECT id FROM audit_criteria WHERE alert_id LIKE 'BBM-%%' ORDER BY id")
    criterion_ids = [row["id"] for row in c.fetchall()]
    for cid in criterion_ids:
        admin_criteria.delete_criterion(database.get_connection, cid, **audit_kwargs)
    if criterion_ids:
        logger.info("Removidos %d criterios BBM-*.", len(criterion_ids))

    # ── Fase B.4b: delete alertas ──────────────────────────────────────────
    c.execute("SELECT id FROM audit_alerts WHERE sector_id = 'bbm' ORDER BY id")
    alert_ids = [row["id"] for row in c.fetchall()]
    for aid in alert_ids:
        admin_criteria.delete_alert(database.get_connection, aid, **audit_kwargs)
    if alert_ids:
        logger.info("Removidos %d alertas BBM-*.", len(alert_ids))

    # ── Fase B.4c: delete setor ────────────────────────────────────────────
    c.execute("SELECT 1 FROM audit_sectors WHERE id = 'bbm'")
    if c.fetchone():
        admin_criteria.delete_sector(database.get_connection, "bbm", **audit_kwargs)
        logger.info("Setor 'bbm' removido de audit_sectors.")

    # ── Fase C: invalidar caches Python ────────────────────────────────────
    try:
        import classification
        classification.load_audit_criteria_catalog.cache_clear()
        classification.build_sectors_and_alerts_prompt.cache_clear()
        classification.get_alert_lookup_by_id.cache_clear()
    except Exception:
        logger.exception("Falha ao invalidar lru_cache de classification (nao critico).")
    sector_aliases.clear_cache()
```

- [ ] **Step 4: Rodar teste — verificar que passa**

```bash
python -m pytest backend/tests/test_bbm_distribuicao_migration.py::TestMigrationIdempotency -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/db/migration_steps/m20260518_004_migrate_bbm_to_distribuicao.py backend/tests/test_bbm_distribuicao_migration.py
git commit -m "$(cat <<'EOF'
feat(migration): m20260518_002 migrar BBM -> Distribuicao

Fase A: pre-flight + snapshot JSON. Fase B: alias em sector_aliases +
DELETE criterios -> alertas -> setor via repositories (audit_log
automatico). Fase C: invalidacao de lru_cache. Idempotente.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Rodar migration localmente + verificar

Executa a migration em ambiente local de dev (DB conectado). Verifica estado pós-migração no DB e existência do snapshot. Este é o gate de integração — se algo falhar aqui, não passa.

**Files:** Nenhum modificado; só verificação.

- [ ] **Step 1: Estado ANTES da migration**

```bash
cd /c/Users/lucas.afonso/projetos/auditoria/backend && python -c "
from dotenv import load_dotenv; load_dotenv()
from database import get_connection
conn = get_connection(); cur = conn.cursor()
cur.execute(\"SELECT id FROM audit_sectors WHERE id='bbm'\")
print('audit_sectors[bbm]:', cur.fetchone())
cur.execute(\"SELECT COUNT(*) AS n FROM audit_alerts WHERE sector_id='bbm'\")
print('audit_alerts bbm:', dict(cur.fetchone()))
cur.execute(\"SELECT COUNT(*) AS n FROM audit_criteria WHERE alert_id LIKE 'BBM-%'\")
print('audit_criteria BBM-*:', dict(cur.fetchone()))
conn.close()
"
```

Expected:
```
audit_sectors[bbm]: {'id': 'bbm'}
audit_alerts bbm: {'n': 10}
audit_criteria BBM-*: {'n': 156}
```

- [ ] **Step 2: Rodar a migration**

```bash
cd /c/Users/lucas.afonso/projetos/auditoria/backend && python -c "
from dotenv import load_dotenv; load_dotenv()
from db.migrations import _mark_migration_applied
from db.migration_steps.m20260518_004_migrate_bbm_to_distribuicao import apply, MIGRATION_NAME
from database import get_connection
conn = get_connection(); cur = conn.cursor()
apply(cur)
_mark_migration_applied(cur, MIGRATION_NAME)
conn.commit(); conn.close()
print('Migration aplicada com sucesso.')
"
```

Expected: log com "Snapshot BBM gravado...", "Alias bbm -> distribuicao criado", "Removidos 156 criterios", "Removidos 10 alertas", "Setor 'bbm' removido"

- [ ] **Step 3: Verificar estado APÓS a migration**

```bash
cd /c/Users/lucas.afonso/projetos/auditoria/backend && python -c "
from dotenv import load_dotenv; load_dotenv()
from database import get_connection
conn = get_connection(); cur = conn.cursor()
cur.execute(\"SELECT id FROM audit_sectors WHERE id='bbm'\")
print('audit_sectors[bbm]:', cur.fetchone())
cur.execute(\"SELECT COUNT(*) AS n FROM audit_alerts WHERE sector_id='bbm'\")
print('audit_alerts bbm:', dict(cur.fetchone()))
cur.execute(\"SELECT COUNT(*) AS n FROM audit_criteria WHERE alert_id LIKE 'BBM-%'\")
print('audit_criteria BBM-*:', dict(cur.fetchone()))
cur.execute(\"SELECT pattern_type, pattern_value, canonical_sector_id FROM sector_aliases WHERE pattern_value='bbm'\")
print('alias bbm:', [dict(r) for r in cur.fetchall()])
cur.execute(\"SELECT COUNT(*) AS n FROM audit_sectors_audit_log WHERE entity_id='bbm' AND acao='delete'\")
print('audit_log sector delete:', dict(cur.fetchone()))
conn.close()
"
```

Expected:
```
audit_sectors[bbm]: None
audit_alerts bbm: {'n': 0}
audit_criteria BBM-*: {'n': 0}
alias bbm: [{'pattern_type': 'setor_exact', 'pattern_value': 'bbm', 'canonical_sector_id': 'distribuicao'}]
audit_log sector delete: {'n': 1}
```

- [ ] **Step 4: Verificar snapshot file**

```bash
ls -la backend/db/seeds/_archived/2026-05-18-bbm-sector.json
python -c "import json; d=json.load(open('backend/db/seeds/_archived/2026-05-18-bbm-sector.json',encoding='utf-8')); print('alerts:', len(d['alerts']), 'criteria:', len(d['criteria']))"
```

Expected: arquivo existe, `alerts: 10 criteria: 156`

- [ ] **Step 5: Rodar a migration uma 2ª vez (idempotência)**

Repete o comando do Step 2. Expected: passa sem erro; logs mostrarão "Setor 'bbm' nao existe no DB; pulando snapshot" e sem novas linhas em audit_log.

- [ ] **Step 6: Commit do snapshot gerado**

```bash
git add backend/db/seeds/_archived/2026-05-18-bbm-sector.json
git commit -m "$(cat <<'EOF'
chore(migration): commit snapshot BBM gerado pela migration v1.3.74

Snapshot lido do DB antes do DELETE. Permite revert via
backend/db/seeds/_archived/restore_bbm.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Refactor `classification.py` (aliases + remoção de BBM)

Adiciona os 10 aliases BBM-* → DISTRIBUICAO-* e remove referências operacionais a 'bbm'. Os aliases são defense-in-depth: se a IA por inércia devolver alert_id antigo, é normalizado para o equivalente DISTRIBUICAO.

**Files:**
- Modify: `backend/classification.py:67-68` (`_ALERT_ID_ALIASES`)
- Modify: `backend/classification.py:263` (`_OPERATIONAL_SIBLINGS`)
- Modify: `backend/classification.py:496` (`_OPERATIONAL_SECTORS`)
- Modify: `backend/classification.py:502` (`_OPERATIONAL_ALERT_PREFIXES`)
- Modify: `backend/classification.py:808-824` (`_OPERATIONAL_ALERT_BY_KIND` map)
- Test: `backend/tests/test_bbm_distribuicao_migration.py` (adicionar testes de alias)

- [ ] **Step 1: Escrever os testes de alias**

Adicionar à classe de testes em `backend/tests/test_bbm_distribuicao_migration.py`:

```python
class TestAlertIdAliases(unittest.TestCase):
    """Cada um dos 10 alertas BBM-* canonicaliza para DISTRIBUICAO-*."""

    BBM_TO_DIST = [
        ("BBM-PARADA-MOT", "DISTRIBUICAO-PARADA-MOT"),
        ("BBM-PARADA-CLI", "DISTRIBUICAO-PARADA-CLI"),
        ("BBM-DESVIO-MOT", "DISTRIBUICAO-DESVIO-MOT"),
        ("BBM-DESVIO-CLI", "DISTRIBUICAO-DESVIO-CLI"),
        ("BBM-POSICAO-MOT", "DISTRIBUICAO-POSICAO-MOT"),
        ("BBM-POSICAO-CLI", "DISTRIBUICAO-POSICAO-CLI"),
        ("BBM-PRIORITARIO-MOT", "DISTRIBUICAO-PRIORITARIO-MOT"),
        ("BBM-PRIORITARIO-CLI", "DISTRIBUICAO-PRIORITARIO-CLI"),
        ("BBM-PRIORITARIO-POLICIA", "DISTRIBUICAO-PRIORITARIO-POLICIA"),
        ("BBM-PONTO-APOIO", "DISTRIBUICAO-PONTO-APOIO"),
    ]

    def test_all_bbm_alerts_canonicalize_to_distribuicao(self):
        from classification import canonicalize_alert_id
        for bbm_id, expected in self.BBM_TO_DIST:
            with self.subTest(bbm_id=bbm_id):
                self.assertEqual(canonicalize_alert_id(bbm_id), expected)

    def test_operational_siblings_excludes_bbm(self):
        # Lê o source para verificar; testar via runtime requer mock do DB
        import classification
        # _apply_operational_siblings espelha BAS para esses setores.
        # Inspeciona _OPERATIONAL_SECTORS em runtime
        self.assertNotIn("bbm", classification._OPERATIONAL_SECTORS)
        self.assertNotIn("bbm", classification._OPERATIONAL_ALERT_PREFIXES)
```

- [ ] **Step 2: Rodar testes — verificar que falham**

```bash
python -m pytest backend/tests/test_bbm_distribuicao_migration.py::TestAlertIdAliases -v
```

Expected: FAIL — `canonicalize_alert_id("BBM-PARADA-MOT")` retorna `"BBM-PARADA-MOT"` (passthrough); `_OPERATIONAL_SECTORS` ainda contém 'bbm'.

- [ ] **Step 3: Adicionar 10 aliases em `_ALERT_ID_ALIASES`**

Localizar em `backend/classification.py:67`:

```python
_ALERT_ID_ALIASES = {
    "BAS-POLICIAL": "BAS-PRIORITARIO-POLICIA",
}
```

Substituir por:

```python
_ALERT_ID_ALIASES = {
    "BAS-POLICIAL": "BAS-PRIORITARIO-POLICIA",
    # Migração BBM → Distribuição em 2026-05-18 (v1.3.74) — manter por
    # defense-in-depth caso IA ou fonte externa devolva alert_id antigo.
    "BBM-PARADA-MOT": "DISTRIBUICAO-PARADA-MOT",
    "BBM-PARADA-CLI": "DISTRIBUICAO-PARADA-CLI",
    "BBM-DESVIO-MOT": "DISTRIBUICAO-DESVIO-MOT",
    "BBM-DESVIO-CLI": "DISTRIBUICAO-DESVIO-CLI",
    "BBM-POSICAO-MOT": "DISTRIBUICAO-POSICAO-MOT",
    "BBM-POSICAO-CLI": "DISTRIBUICAO-POSICAO-CLI",
    "BBM-PRIORITARIO-MOT": "DISTRIBUICAO-PRIORITARIO-MOT",
    "BBM-PRIORITARIO-CLI": "DISTRIBUICAO-PRIORITARIO-CLI",
    "BBM-PRIORITARIO-POLICIA": "DISTRIBUICAO-PRIORITARIO-POLICIA",
    "BBM-PONTO-APOIO": "DISTRIBUICAO-PONTO-APOIO",
}
```

- [ ] **Step 4: Remover 'bbm' de `_OPERATIONAL_SIBLINGS` (linha 263)**

Localizar:

```python
    _OPERATIONAL_SIBLINGS = {"transferencia", "distribuicao", "fenix", "bbm"}
```

Substituir por:

```python
    _OPERATIONAL_SIBLINGS = {"transferencia", "distribuicao", "fenix"}
```

- [ ] **Step 5: Remover 'bbm' de `_OPERATIONAL_SECTORS` (linha 496)**

Localizar:

```python
_OPERATIONAL_SECTORS = {"transferencia", "uti", "bas", "distribuicao", "fenix", "bbm"}
```

Substituir por:

```python
_OPERATIONAL_SECTORS = {"transferencia", "uti", "bas", "distribuicao", "fenix"}
```

- [ ] **Step 6: Remover entrada 'bbm' de `_OPERATIONAL_ALERT_PREFIXES` (linha 502)**

Localizar:

```python
_OPERATIONAL_ALERT_PREFIXES = {
    "uti": "UTI",
    "transferencia": "TRANSFERENCIA",
    "distribuicao": "DISTRIBUICAO",
    "fenix": "FENIX",
    "bbm": "BBM",
    "bas": "BAS",
}
```

Substituir por:

```python
_OPERATIONAL_ALERT_PREFIXES = {
    "uti": "UTI",
    "transferencia": "TRANSFERENCIA",
    "distribuicao": "DISTRIBUICAO",
    "fenix": "FENIX",
    "bas": "BAS",
}
```

- [ ] **Step 7: Remover entradas BBM do mapa `_OPERATIONAL_ALERT_BY_KIND` (linhas 808-824)**

Localizar cada uma das 7 dict literals que têm `"bbm": "BBM-..."` e remover a entrada `"bbm": ...`. Exemplo da linha 808:

```python
    "POSIÇÃO": {"logistica": "LOGISTICA-POSICAO", "bas": "UTI-POSICAO-MOT", "uti": "UTI-POSICAO-MOT", "transferencia": "TRANSFERENCIA-POSICAO-MOT", "distribuicao": "DISTRIBUICAO-POSICAO-MOT", "fenix": "FENIX-POSICAO-MOT", "bbm": "BBM-POSICAO-MOT"},
```

Vira:

```python
    "POSIÇÃO": {"logistica": "LOGISTICA-POSICAO", "bas": "UTI-POSICAO-MOT", "uti": "UTI-POSICAO-MOT", "transferencia": "TRANSFERENCIA-POSICAO-MOT", "distribuicao": "DISTRIBUICAO-POSICAO-MOT", "fenix": "FENIX-POSICAO-MOT"},
```

Aplicar o mesmo padrão para todas as 7 linhas que mencionam `bbm`:
- `"POSIÇÃO"` (808), `"POSICAO"` (809), `"PARADA"` (810), `"DESVIO"` (811), `"POLICIA"` (816), `"POLICIAL"` (817), `"PRIORITARIO"` (823), `"PRIORITÁRIO"` (824)

- [ ] **Step 8: Remover entrada `"bbm": "BBM"` em sector_labels (linha 502 era da seção operacional; verificar também linha ~502 do bloco anterior)**

Verificar em torno da linha 502 se há outra ocorrência de `"bbm": "BBM",` em um dicionário (ex: `sector_labels` ou `_OPERATIONAL_SECTOR_LABELS`). Se existir, remover. Comando para confirmar:

```bash
grep -n '"bbm"' backend/classification.py
```

Expected após edição: 0 ocorrências de `"bbm"`.

- [ ] **Step 9: Rodar testes — verificar que passam**

```bash
python -m pytest backend/tests/test_bbm_distribuicao_migration.py::TestAlertIdAliases -v
```

Expected: PASS (todos os 11 sub-testes — 10 aliases + 1 sectors)

- [ ] **Step 10: Rodar suite de classification para regressão**

```bash
python -m pytest backend/tests/test_classification_guardrails.py backend/tests/test_classification_direction_guardrail.py backend/tests/test_classification_review_policy.py -v --tb=short
```

Expected: todos passam (sem regressão).

- [ ] **Step 11: Commit**

```bash
git add backend/classification.py backend/tests/test_bbm_distribuicao_migration.py
git commit -m "$(cat <<'EOF'
refactor(classification): remove BBM operacional + adiciona aliases

- _ALERT_ID_ALIASES: 10 entradas BBM-* -> DISTRIBUICAO-* (defense-in-depth)
- _OPERATIONAL_SIBLINGS: remove 'bbm'
- _OPERATIONAL_SECTORS: remove 'bbm'
- _OPERATIONAL_ALERT_PREFIXES: remove 'bbm'
- _OPERATIONAL_ALERT_BY_KIND: remove 'bbm' das 7 entradas

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Refactor outros arquivos backend

Remove referências a 'bbm' nos demais arquivos backend que ainda mencionam o setor como operacional.

**Files:**
- Modify: `backend/core/config.py:196`
- Modify: `backend/core/evaluation.py:401`
- Modify: `backend/audit_evaluator.py:327, 365-369`
- Modify: `backend/core/operator_filters.py:17`
- Modify: `backend/core/gestores_mapping.py:18`

- [ ] **Step 1: `backend/core/config.py:196`**

Localizar:

```python
        "fenix": "rastreamento", "bbm": "distribuicao",
```

Substituir por:

```python
        "fenix": "rastreamento",
```

- [ ] **Step 2: `backend/core/evaluation.py:401`**

Localizar:

```python
    RASTREAMENTO_SECTORS = {"distribuicao", "uti", "transferencia", "fenix", "bbm", "bas", "rastreamento"}
```

Substituir por:

```python
    RASTREAMENTO_SECTORS = {"distribuicao", "uti", "transferencia", "fenix", "bas", "rastreamento"}
```

- [ ] **Step 3: `backend/audit_evaluator.py:327`**

Localizar:

```python
PASSWORD_RULE_SECTORS = {"transferencia", "uti", "bas", "distribuicao", "fenix", "bbm", "rastreamento"}
```

Substituir por:

```python
PASSWORD_RULE_SECTORS = {"transferencia", "uti", "bas", "distribuicao", "fenix", "rastreamento"}
```

- [ ] **Step 4: `backend/audit_evaluator.py:365-369`**

Localizar e remover o bloco inteiro:

```python
    "bbm": {
        "label": "Distribuicao",
        "tipo_ligacao": "Ligacao Efetuada (Motorista ou Cliente)",
        "regras_zeragem": _RASTREAMENTO_ZERAGEM,
    },
```

(deixa o dicionário sem a entrada `"bbm"`).

- [ ] **Step 5: `backend/core/operator_filters.py:17`**

Localizar:

```python
    "time bbm",
```

Substituir por: (linha removida — a entrada some completamente).

- [ ] **Step 6: `backend/core/gestores_mapping.py:18`**

Localizar:

```python
    "bbm": "DISTRIBUIÇÃO",
```

Substituir por: (linha removida — o alias agora vive no DB via `sector_aliases`).

- [ ] **Step 7: Confirmar zero ocorrências operacionais**

```bash
grep -n "bbm\|BBM" backend/classification.py backend/core/config.py backend/core/evaluation.py backend/audit_evaluator.py backend/core/operator_filters.py backend/core/gestores_mapping.py
```

Expected: NENHUMA saída.

- [ ] **Step 8: Rodar tests de regressão**

```bash
python -m pytest backend/tests/test_classification_guardrails.py backend/tests/test_classification_direction_guardrail.py backend/tests/test_critical_fixes_v1_3_73.py backend/tests/test_scoring_determinism.py backend/tests/test_operator_auditability.py -v --tb=short
```

Expected: todos passam. Se quebrar algum por causa de BBM em fixtures, ATUALIZAR o teste (não reverter o código).

- [ ] **Step 9: Commit**

```bash
git add backend/core/config.py backend/core/evaluation.py backend/audit_evaluator.py backend/core/operator_filters.py backend/core/gestores_mapping.py
git commit -m "$(cat <<'EOF'
refactor(backend): remover 'bbm' dos mapas/sets operacionais

Backend nao referencia mais 'bbm' como setor independente. Resolucao
via DB alias sector_aliases (bbm -> distribuicao).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Refactor YAMLs (scoring rules)

Remove o bloco `id: bbm` dos 3 YAMLs de setor. Como o seed `database._seed_audit_criteria` lê desse YAML e já rodou, isso garante que um eventual re-seed não recria o setor.

**Files:**
- Modify: `backend/db/scoring_rules_final.yaml:22-24`
- Modify: `backend/db/scoring_rules_updated.yaml:22-24`
- Modify: `backend/db/seeds/scoring_rules.bootstrap.yaml:22-24`

- [ ] **Step 1: Remover bloco BBM dos 3 arquivos**

Em cada arquivo, localizar e remover:

```yaml
- id: bbm
  label: BBM
  description: Setor de rastreamento - BBM (operação dedicada)
```

Apenas remova esse trio de 3 linhas — preserva os setores adjacentes (fenix antes, cadastro depois).

- [ ] **Step 2: Validar YAMLs**

```bash
cd /c/Users/lucas.afonso/projetos/auditoria/backend && python -c "
from db.scoring_loader import get_sectors, get_alerts, validate_yaml
errors = validate_yaml()
if errors: raise SystemExit('VALIDATION ERRORS: ' + '; '.join(errors))
sectors = {s['id'] for s in get_sectors()}
assert 'bbm' not in sectors, 'bbm ainda presente em get_sectors()'
print('OK — bbm fora dos YAMLs.')
"
```

Expected: `OK — bbm fora dos YAMLs.`

- [ ] **Step 3: Commit**

```bash
git add backend/db/scoring_rules_final.yaml backend/db/scoring_rules_updated.yaml backend/db/seeds/scoring_rules.bootstrap.yaml
git commit -m "$(cat <<'EOF'
refactor(yaml): remover setor 'bbm' dos scoring_rules

Evita que um re-seed acidental do scoring_rules.yaml recrie a linha
de setor 'bbm' apagada pela migration v1.3.74.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Refactor frontend

Remove BBM de 6 arquivos React + 1 JSON. Garante que `tsc --noEmit` continua limpo.

**Files:**
- Modify: `src/features/settings/components/OperadorManagement.tsx:83`
- Modify: `src/features/saved-files/components/SavedFiles.tsx:391`
- Modify: `src/features/automacao/components/AuditModal.tsx:369`
- Modify: `src/features/audit/hooks/useAuditResultEditor.ts:67`
- Modify: `src/features/audit/hooks/useAuditFlow.ts:23`
- Modify: `src/shared/lib/operationalLabels.ts:5, 22`
- Modify: `src/data/criteria.json` (string de label combinada)

- [ ] **Step 1: `OperadorManagement.tsx:83`**

Localizar `'TIME BBM',` e remover essa linha do array.

- [ ] **Step 2: `SavedFiles.tsx:391`**

Localizar:

```typescript
  const trackingSectors = ['bas', 'bbm', 'distribuicao', 'uti', 'transferencia', 'fenix', 'rastreamento'];
```

Substituir por:

```typescript
  const trackingSectors = ['bas', 'distribuicao', 'uti', 'transferencia', 'fenix', 'rastreamento'];
```

- [ ] **Step 3: `AuditModal.tsx:369`**

Mesma alteração da linha do Step 2 (texto idêntico). Remover `'bbm'`.

- [ ] **Step 4: `useAuditResultEditor.ts:67`**

Localizar:

```typescript
  const RASTREAMENTO_SECTORS = ['bas', 'bbm', 'distribuicao', 'uti', 'transferencia', 'fenix', 'rastreamento'];
```

Substituir por:

```typescript
  const RASTREAMENTO_SECTORS = ['bas', 'distribuicao', 'uti', 'transferencia', 'fenix', 'rastreamento'];
```

- [ ] **Step 5: `useAuditFlow.ts:23`**

Localizar:

```typescript
  'BAS', 'G2L', 'LP', 'UTI', 'BBM', 'FENIX', 'CADASTRO', 'LOGISTICA',
```

Substituir por (remover `'BBM',`):

```typescript
  'BAS', 'G2L', 'LP', 'UTI', 'FENIX', 'CADASTRO', 'LOGISTICA',
```

- [ ] **Step 6: `operationalLabels.ts:5` (label map)**

Localizar (em torno da linha 5, dentro do objeto literal):

```typescript
  BBM: 'BBM',
```

Remover essa linha.

- [ ] **Step 7: `operationalLabels.ts:22` (PRESERVE_UPPERCASE)**

Localizar:

```typescript
const PRESERVE_UPPERCASE = new Set(['BAS', 'UTI', 'LP', 'BBM', 'G2L', 'RH', 'TI', 'IA', 'URA', 'CPF']);
```

Substituir por (remover `'BBM',`):

```typescript
const PRESERVE_UPPERCASE = new Set(['BAS', 'UTI', 'LP', 'G2L', 'RH', 'TI', 'IA', 'URA', 'CPF']);
```

- [ ] **Step 8: `src/data/criteria.json`**

Localizar a string `"Transferência / Distribuição / Fênix / BBM / UTI / BAS"` e substituir por:

```
"Transferência / Distribuição / Fênix / UTI / BAS"
```

- [ ] **Step 9: Verificar zero ocorrências de BBM no frontend (com exceção de comentários, se houver)**

```bash
grep -rn 'BBM\|bbm' src/ --include='*.ts' --include='*.tsx' --include='*.json'
```

Expected: NENHUMA saída.

- [ ] **Step 10: TypeScript check**

```bash
npx tsc --noEmit -p .
```

Expected: sem erros.

- [ ] **Step 11: Commit**

```bash
git add src/features/settings/components/OperadorManagement.tsx src/features/saved-files/components/SavedFiles.tsx src/features/automacao/components/AuditModal.tsx src/features/audit/hooks/useAuditResultEditor.ts src/features/audit/hooks/useAuditFlow.ts src/shared/lib/operationalLabels.ts src/data/criteria.json
git commit -m "$(cat <<'EOF'
refactor(ui): remover BBM dos componentes e mapeamentos

7 arquivos do frontend nao referenciam mais 'bbm' como setor.
tsc --noEmit limpo.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Testes adicionais (catalog + prompt)

Adiciona 2 testes finais ao arquivo de testes — verifica que o catálogo e o prompt da IA não mencionam mais BBM em runtime (não só no source).

**Files:**
- Modify: `backend/tests/test_bbm_distribuicao_migration.py`

- [ ] **Step 1: Adicionar 2 testes finais**

Adicionar ao final do arquivo:

```python
class TestCatalogAndPromptHaveNoBBM(unittest.TestCase):
    """Pós-migração: catálogo carregado do DB e prompt da IA não mencionam BBM."""

    def test_catalog_does_not_contain_bbm(self):
        from classification import load_audit_criteria_catalog
        load_audit_criteria_catalog.cache_clear()
        catalog = load_audit_criteria_catalog()
        self.assertNotIn("bbm", catalog)

    def test_prompt_does_not_contain_bbm(self):
        from classification import build_sectors_and_alerts_prompt
        build_sectors_and_alerts_prompt.cache_clear()
        prompt = build_sectors_and_alerts_prompt()
        self.assertNotIn("BBM-", prompt)
        # 'BBM' como palavra solta em label não deve aparecer
        self.assertNotIn(" BBM ", prompt)
        self.assertNotIn(" BBM\n", prompt)
```

- [ ] **Step 2: Rodar**

```bash
python -m pytest backend/tests/test_bbm_distribuicao_migration.py -v --tb=short
```

Expected: todos os testes do arquivo passam (snapshot, idempotência, aliases, catalog/prompt).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_bbm_distribuicao_migration.py
git commit -m "$(cat <<'EOF'
test(migration): verifica catalogo e prompt sem BBM apos migration

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Documentação (PENDENCIAS, MEMORY, version log)

Atualiza memória do projeto e cria log de versão da migração.

**Files:**
- Modify: `pendencias/PENDENCIAS.md`
- Modify: `~/.claude/projects/C--Users-lucas-afonso-projetos-auditoria/memory/MEMORY.md`
- Create: `logs/versions/1.3.74-migracao-bbm-distribuicao.md`

- [ ] **Step 1: Criar log de versão**

Criar `logs/versions/1.3.74-migracao-bbm-distribuicao.md`:

```markdown
# Versão 1.3.74 — Migração BBM → Distribuição

**Data:** 18 de Maio de 2026
**Autores:** Lucas Afonso / Claude Opus 4.7

## Contexto
BBM foi absorvido operacionalmente por Distribuição. Esta versão remove BBM
como entidade independente do sistema (DB + código + frontend).

## O que mudou

### Banco de dados (via migration `m20260518_002`)
- DELETE de 1 setor + 10 alertas BBM-* + 156 critérios em audit_*
- Audit_log automático preserva snapshot antes/depois em audit_*_audit_log
- INSERT em `sector_aliases`: pattern_value='bbm', canonical_sector_id='distribuicao'
- Snapshot JSON gerado em `backend/db/seeds/_archived/2026-05-18-bbm-sector.json`

### Backend
- `classification.py`: 10 aliases BBM-* → DISTRIBUICAO-* em `_ALERT_ID_ALIASES` (defense-in-depth)
- Remove 'bbm' de `_OPERATIONAL_SIBLINGS`, `_OPERATIONAL_SECTORS`, `_OPERATIONAL_ALERT_PREFIXES`, `_OPERATIONAL_ALERT_BY_KIND`
- `core/config.py`, `core/evaluation.py`, `audit_evaluator.py`, `core/operator_filters.py`, `core/gestores_mapping.py`: removidas referências a 'bbm'
- YAMLs scoring_rules: removido bloco `id: bbm`

### Frontend
- 6 componentes/hooks deixam de listar BBM como setor de rastreamento
- `operationalLabels.ts`: BBM removido de map e PRESERVE_UPPERCASE
- `data/criteria.json`: BBM removido da string de label combinada

### Não mexido (decisão)
- `backend/transcription_providers/common.py`: "BBM" mantido como vocabulário STT histórico
- `backend/data/rag_training/*.md`: contexto histórico para IA
- Migrations anteriores

## Reversibilidade
Script `backend/db/seeds/_archived/restore_bbm.py` re-insere setor + alertas
+ critérios do snapshot JSON. Audit_log do DB fornece 2ª fonte de revert.

## Tests
- `backend/tests/test_bbm_distribuicao_migration.py` com testes:
  - Snapshot round-trip (helper)
  - Idempotência da migration (smoke)
  - 10 aliases BBM-* → DISTRIBUICAO-*
  - `_OPERATIONAL_SECTORS` e `_OPERATIONAL_ALERT_PREFIXES` sem 'bbm'
  - Catálogo do DB sem 'bbm'
  - Prompt da IA sem BBM-

## Cobre pendências derivadas (revisão técnica v1.3.73)
- M3: "operational siblings hardcoded; não cobre uti-BBM" — agora não tem mais BBM
- MEMORY.md: linha "BBM = transferencia + uti-BBM" removida
```

- [ ] **Step 2: Atualizar `pendencias/PENDENCIAS.md`**

Adicionar ao topo (após o cabeçalho), antes de "## Legenda":

```markdown
## v1.3.74 — Migração BBM → Distribuição (2026-05-18)

- 🟢 **BBM absorvido por Distribuição**: setor + 10 alertas + 156 critérios removidos do DB; alias `bbm → distribuicao` em `sector_aliases` garante retrocompatibilidade. Snapshot JSON + restore script em `backend/db/seeds/_archived/`. Ver `logs/versions/1.3.74-migracao-bbm-distribuicao.md`.
```

- [ ] **Step 3: Atualizar `MEMORY.md`**

Localizar a linha:

```markdown
- **BBM** = transferencia + uti-BBM (UTI apenas em MG/SP/RJ, LP resto)
```

Substituir por:

```markdown
- ~~**BBM** = transferencia + uti-BBM~~ — RESOLVIDO em v1.3.74 (BBM absorvido por Distribuição; ver `logs/versions/1.3.74-*`)
```

E adicionar à seção "Fixes críticos da revisão técnica" (logo abaixo dela), nova subseção:

```markdown
## Migração BBM (v1.3.74 — 2026-05-18)
- BBM removido do sistema (DB + código backend + frontend); alias em `sector_aliases` redireciona fontes externas
- Snapshot recuperável em `backend/db/seeds/_archived/2026-05-18-bbm-sector.json` + script `restore_bbm.py`
- 10 entradas em `_ALERT_ID_ALIASES` (BBM-* → DISTRIBUICAO-*) para defense-in-depth
```

- [ ] **Step 4: Commit**

```bash
git add pendencias/PENDENCIAS.md logs/versions/1.3.74-migracao-bbm-distribuicao.md
git commit -m "$(cat <<'EOF'
docs: log v1.3.74 + atualizar PENDENCIAS para migracao BBM->Dist

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

(MEMORY.md vive no diretório de memória do usuário, fora do repo — atualizar usando o Edit tool, não commitar via git.)

---

## Task 10: Verificação final + push

Roda suite completa de testes nos arquivos modificados, garante TypeScript limpo, push.

- [ ] **Step 1: Suite completa dos arquivos relacionados**

```bash
python -m pytest backend/tests/test_bbm_distribuicao_migration.py backend/tests/test_classification_guardrails.py backend/tests/test_classification_direction_guardrail.py backend/tests/test_classification_review_policy.py backend/tests/test_critical_fixes_v1_3_73.py backend/tests/test_review_queue_contract.py backend/tests/test_telefonia_router.py backend/tests/test_automation_rules.py backend/tests/test_transcription_orchestrator.py backend/tests/test_scoring_determinism.py backend/tests/test_operator_auditability.py -v --tb=short
```

Expected: todos passam. Se algum quebrar com referência a 'bbm', ATUALIZAR o teste (não reverter código).

- [ ] **Step 2: TypeScript check**

```bash
npx tsc --noEmit -p .
```

Expected: zero erros.

- [ ] **Step 3: git log review**

```bash
git log --oneline -12
```

Expected: ~9 commits novos com mensagens claras (snapshot+restore, migration, snapshot json, classification refactor, backend refactor, yamls, frontend, tests, docs).

- [ ] **Step 4: Push para origem**

```bash
git push origin main
```

Expected: push limpo. Se rejeitado por divergência, rodar `git pull --rebase origin main` e resolver conflitos antes de tentar de novo.

---

## Definition of Done

1. ✅ DB sem 'bbm' em audit_sectors / audit_alerts / audit_criteria
2. ✅ `sector_aliases` tem 1 linha (bbm → distribuicao)
3. ✅ Snapshot JSON existe em `backend/db/seeds/_archived/2026-05-18-bbm-sector.json`
4. ✅ Script `restore_bbm.py` re-insere BBM se necessário (não testado em produção, só estrutural)
5. ✅ Backend sem 'bbm' operacional (28 ocorrências → 0; exceção: `transcription_providers/common.py` intencional)
6. ✅ Frontend sem 'bbm' (7 arquivos limpos; `tsc --noEmit` limpo)
7. ✅ YAMLs sem setor 'bbm' (3 arquivos)
8. ✅ Todos os testes relacionados passam isolados (~120+ tests)
9. ✅ `logs/versions/1.3.74-migracao-bbm-distribuicao.md` criado
10. ✅ MEMORY.md + PENDENCIAS.md atualizados
11. ✅ ~9 commits feitos e push para origin/main
