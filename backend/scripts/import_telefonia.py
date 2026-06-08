from pathlib import Path
import pandas as pd

import db.database as database

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
TELEFONIA_DIR = PROJECT_ROOT / "instrucoes" / "telefonia"


def _normalize_column_name(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return " ".join(normalized.split())


def _clean_value(value) -> str:
    if pd.isna(value) or value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text.replace(".0", "", 1).isdigit():
        return text[:-2]
    return text


def _find_latest_workbook() -> Path:
    files = sorted(TELEFONIA_DIR.glob("*.xlsx"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo .xlsx encontrado em {TELEFONIA_DIR}")
    return files[0]


def run_import() -> dict:
    database.init_db()

    workbook_path = _find_latest_workbook()
    df = pd.read_excel(workbook_path)
    column_map = {_normalize_column_name(column): column for column in df.columns}

    nome_col = column_map.get("funcionario")
    conta_col = column_map.get("conta")
    organizacao_col = column_map.get("organizacao proprietaria")
    id_col = column_map.get("id do funcionario")
    softphone_col = column_map.get("numero do softphone")
    tipo_agente_col = column_map.get("tipo de agente")
    status_col = column_map.get("status")

    if not nome_col:
        raise RuntimeError(f"Coluna de funcionario nao encontrada em {workbook_path.name}")

    imported = 0
    skipped = 0

    for _, row in df.iterrows():
        nome = _clean_value(row.get(nome_col))
        if not nome:
            skipped += 1
            continue

        database.upsert_colaborador_telefonia(
            nome=nome,
            id_telefonia=_clean_value(row.get(id_col)) if id_col else "",
            softphone_number=_clean_value(row.get(softphone_col)) if softphone_col else "",
            telefonia_account=_clean_value(row.get(conta_col)) if conta_col else "",
            organizacao_telefonia=_clean_value(row.get(organizacao_col)) if organizacao_col else "",
            tipo_agente=_clean_value(row.get(tipo_agente_col)) if tipo_agente_col else "",
            status_telefonia=_clean_value(row.get(status_col)) if status_col else "",
        )
        imported += 1

    return {
        "file": workbook_path.name,
        "imported": imported,
        "skipped": skipped,
    }


if __name__ == "__main__":
    result = run_import()
    print(f"Arquivo: {result['file']}")
    print(f"Importados: {result['imported']}")
    print(f"Ignorados: {result['skipped']}")
