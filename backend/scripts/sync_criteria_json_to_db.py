import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database
from db.scoring_loader import get_alerts, get_sectors, validate_yaml


def sync_criteria_json_to_db():
    """Backward-compatible entrypoint that now syncs from scoring_rules.yaml."""
    validation_errors = validate_yaml()
    if validation_errors:
        raise RuntimeError("scoring_rules.yaml invalido: " + "; ".join(validation_errors))

    conn = database.get_connection()
    cursor = conn.cursor()

    try:
        database._seed_audit_criteria(cursor)
        conn.commit()
        print(
            "Sincronizacao concluida com sucesso a partir de scoring_rules.yaml "
            f"({len(get_sectors())} setores, {len(get_alerts())} alertas)."
        )
    except Exception as exc:
        conn.rollback()
        print(f"Erro ao sincronizar: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sync_criteria_json_to_db()
