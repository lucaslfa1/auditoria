"""
Script para importar lista de funcionarios dos arquivos Excel para o banco de dados.
Extrai dados de 18 arquivos, mapeia setores e escalas, e armazena em colaboradores.
"""
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
from repositories.common import extract_returning_id

# Garantir que o diretorio backend esteja no path para imports internos.
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Mapeamento de siglas para setores conforme instrucao do usuario.
# Os ids DEVEM coincidir com os valores esperados por _matches_operador_sector
# em repositories/operators.py para que lookup e filtros funcionem.
SETOR_MAPPING = {
    "CADASTRO": {"id": "CADASTRO", "nome": "Cadastro"},
    "CHECKLIST E CELULA DIURNO": {"id": "CHECKLIST", "nome": "Checklist e Celula Diurno"},
    "DIST E CELULA": {"id": "DISTRIBUICAO", "nome": "Distribuicao e Celula"},
    "DIST": {"id": "DISTRIBUICAO", "nome": "Distribuicao"},
    "FENIX": {"id": "FENIX", "nome": "Fenix"},
    "GRS": {"id": "UTI", "nome": "UTI (Gerenciamento de Risco)"},
    "LOG": {"id": "LOGISTICA", "nome": "Logistica Geral"},
    "LOG-MONDELEZ": {
        "id": "LOGISTICA",
        "nome": "Logistica Mondelez",
        "escala_override": "MONDELEZ",
    },
    "LOG-UNILEVER": {
        "id": "LOGISTICA",
        "nome": "Logistica Unilever",
        "escala_override": "UNILEVER",
    },
    "LOG MONDELEZ": {
        "id": "LOGISTICA",
        "nome": "Logistica Mondelez",
        "escala_override": "MONDELEZ",
    },
    "LOG UNILEVER": {
        "id": "LOGISTICA",
        "nome": "Logistica Unilever",
        "escala_override": "UNILEVER",
    },
    "LP": {"id": "TRANSFERENCIA", "nome": "Longo Percurso (Rastreamento)"},
    "UTI": {"id": "UTI", "nome": "Base Dedicada de Gerenciamento de Risco"},
}

# Mapeamento de cores para escalas.
ESCALA_MAPPING = {
    "AMARELA": "Amarela",
    "AZUL": "Azul",
    "CINZA": "Cinza",
    "VERDE": "Verde",
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", normalized)


COLUMN_ALIASES = {
    "nome": ("nome",),
    "matricula": ("matricula",),
    "id_weon": ("idweon",),
    "id_huawei": ("idhuawei",),
    "status": ("status",),
    "tipo_escala": ("turnooperacao",),
    "supervisor": ("supervisor",),
    "setor": ("setor",),
    "obs": ("obs",),
    "status_total": ("status1",),
}


def _safe_matricula(value) -> str | None:
    if pd.isna(value):
        return None
    try:
        return str(int(float(value)))
    except (ValueError, TypeError):
        return str(value).strip() or None


def _build_existing_lookup(cursor):
    by_matricula = {}
    by_normalized_name = {}

    cursor.execute("SELECT id, nome, matricula, supervisor FROM colaboradores")
    for row in cursor.fetchall():
        item = dict(row)
        matricula = str(item.get("matricula") or "").strip()
        normalized_name = _normalize_text(item.get("nome"))

        if matricula:
            by_matricula[matricula] = item

        if normalized_name:
            by_normalized_name.setdefault(normalized_name, []).append(item)

    return by_matricula, by_normalized_name


def _find_existing_colaborador(funcionario, by_matricula, by_normalized_name):
    matricula = str(funcionario.get("matricula") or "").strip()
    if matricula and matricula in by_matricula:
        return by_matricula[matricula], "matricula"

    normalized_name = _normalize_text(funcionario.get("nome"))
    if not normalized_name:
        return None, None

    candidates = by_normalized_name.get(normalized_name, [])
    if len(candidates) != 1:
        return None, None

    candidate = candidates[0]
    candidate_matricula = str(candidate.get("matricula") or "").strip()
    if candidate_matricula:
        return None, None

    return candidate, "nome"


def _upsert_funcionario(
    cursor,
    func,
    fallback_setor_id,
    fallback_escala,
    by_matricula,
    by_normalized_name,
):
    existing, matched_by = _find_existing_colaborador(func, by_matricula, by_normalized_name)
    resolved_setor_id = _resolve_sector_id(
        func["setor"],
        fallback_setor_id,
        func["tipo_escala"],
    )
    now_iso = datetime.now().isoformat()

    if existing:
        cursor.execute(
            """
            UPDATE colaboradores SET
                nome = %s,
                matricula = %s,
                supervisor = %s,
                setor = %s,
                escala = %s,
                status = %s,
                auditavel = %s,
                id_weon = %s,
                id_huawei = %s,
                tipo_escala = %s,
                atualizado_em = %s
            WHERE id = %s
            """,
            (
                func["nome"],
                func["matricula"],
                func["supervisor"],
                resolved_setor_id,
                fallback_escala,
                func["status"],
                1 if func["status"] == "ATIVO" else 0,
                func["id_weon"],
                func["id_huawei"],
                func["tipo_escala"],
                now_iso,
                existing["id"],
            ),
        )
        existing.update(
            {
                "nome": func["nome"],
                "matricula": func["matricula"],
                "supervisor": func["supervisor"],
            }
        )
        if func["matricula"]:
            by_matricula[func["matricula"]] = existing
        return "reconciled_name" if matched_by == "nome" else "updated"

    cursor.execute(
        """
        INSERT INTO colaboradores (
            nome, matricula, supervisor, setor, escala, status,
            auditavel, id_weon, id_huawei, tipo_escala, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            func["nome"],
            func["matricula"],
            func["supervisor"],
            resolved_setor_id,
            fallback_escala,
            func["status"],
            1 if func["status"] == "ATIVO" else 0,
            func["id_weon"],
            func["id_huawei"],
            func["tipo_escala"],
            now_iso,
        ),
    )

    created = {
        "id": extract_returning_id(cursor.fetchone()),
        "nome": func["nome"],
        "matricula": func["matricula"],
        "supervisor": func["supervisor"],
    }
    if func["matricula"]:
        by_matricula[func["matricula"]] = created
    normalized_name = _normalize_text(func["nome"])
    if normalized_name:
        by_normalized_name.setdefault(normalized_name, []).append(created)
    return "inserted"


def _should_skip_workbook(filename: str) -> bool:
    return _normalize_text(filename).startswith("funcionariosconsolidado")


def _get_row_value(row, field_name: str):
    row_keys = row.index if hasattr(row, "index") else row.keys()
    normalized_row_keys = {_normalize_text(key): key for key in row_keys}

    for alias in COLUMN_ALIASES[field_name]:
        if alias in normalized_row_keys:
            value = row[normalized_row_keys[alias]]
            if pd.notna(value):
                return value

    if field_name == "tipo_escala":
        for normalized_key, original_key in normalized_row_keys.items():
            if normalized_key.startswith("turnoopera"):
                value = row[original_key]
                if pd.notna(value):
                    return value

    return None


def _resolve_sector_id(
    row_sector: str | None,
    fallback_sector_id: str,
    operation_hint: str | None = None,
) -> str:
    normalized_row_sector = _normalize_text(row_sector)
    normalized_fallback_sector = _normalize_text(fallback_sector_id)
    normalized_operation_hint = _normalize_text(operation_hint)

    # Fenix e tratado como setor proprio quando a origem da planilha ou da operacao
    # indica Fenix, porque os subsetores internos nao estao identificados de forma confiavel.
    if normalized_fallback_sector == "fenix" or "fenix" in normalized_operation_hint:
        return "FENIX"

    if not normalized_row_sector:
        return fallback_sector_id

    if normalized_row_sector == "cadastro":
        return "CADASTRO"
    if normalized_row_sector == "checklist":
        return "CHECKLIST"
    if normalized_row_sector == "receptivo" or "celula" in normalized_row_sector:
        return "RECEPTIVO"
    if normalized_row_sector in {"distribuicao", "distribuio"}:
        return "DISTRIBUICAO"
    if normalized_row_sector in {"transferencia", "transferncia", "lp"}:
        return "TRANSFERENCIA"
    if "fenix" in normalized_row_sector:
        return "FENIX"
    if normalized_row_sector == "grs" or normalized_row_sector.startswith("uti"):
        return "UTI"
    if normalized_row_sector == "bas" or "sinistro" in normalized_row_sector:
        return "BAS"
    if any(tag in normalized_row_sector for tag in ("logistica", "mondelez", "unilever", "taborda")):
        return "LOGISTICA"

    return fallback_sector_id


def parse_filename(filename):
    """
    Parse do nome do arquivo para extrair setor e escala.
    Exemplos: 2602-GRS-AMARELA.xlsx, 2602-CADASTRO.xlsx, 2602-LOG-MONDELEZ.xlsx
    Com espacos: 2602-DIST - AMARELA.xlsx, 2602-DIST E CELULA - VERDE.xlsx
    """
    name = filename.replace(".xlsx", "").replace("2602-", "").strip()

    escala = None
    setor = name

    for cor in ESCALA_MAPPING.keys():
        if name.endswith(cor):
            setor = name[: -len(cor)].rstrip(" -").strip()
            escala = ESCALA_MAPPING[cor]
            break
        if name.endswith(" - " + cor) or name.endswith("-" + cor):
            escala = ESCALA_MAPPING[cor]
            setor = name[: -(len(cor) + 2)].rstrip(" -").strip()
            break

    setor_upper = setor.upper()
    setor_info = SETOR_MAPPING.get(setor_upper)
    if not setor_info:
        print("[AVISO] Setor '{}' nao mapeado no arquivo {}".format(setor_upper, filename))
        setor_info = {"id": setor_upper, "nome": setor}

    # Para LOG-MONDELEZ/UNILEVER, o nome do arquivo nao tem cor; usar escala_override.
    if escala is None and "escala_override" in setor_info:
        escala = setor_info["escala_override"]

    return {
        "setor_id": setor_info["id"],
        "setor_nome": setor_info["nome"],
        "escala": escala,
        "arquivo": filename,
    }


def extract_funcionarios(filepath):
    """
    Extrai lista de funcionarios de um arquivo Excel.
    """
    try:
        df = pd.read_excel(filepath)
    except Exception as e:
        print("[ERRO] Erro ao ler {}: {}".format(filepath, str(e)))
        return []

    funcionarios = []

    for _, row in df.iterrows():
        nome = _get_row_value(row, "nome")
        matricula = _get_row_value(row, "matricula")
        if pd.isna(nome) or pd.isna(matricula):
            continue

        if "Total" in str(_get_row_value(row, "status_total") or ""):
            continue

        # Tentar extrair ID HUAWEI (pode ter espaco no final, ou conter "-").
        id_huawei = None
        raw_id_huawei = _get_row_value(row, "id_huawei")
        if raw_id_huawei is not None:
            val = str(raw_id_huawei).strip()
            if val and val != "-":
                try:
                    id_huawei = str(int(float(val)))
                except (ValueError, TypeError):
                    pass

        # Tentar extrair ID WEON (pode ter espaco no final, ou conter "-").
        id_weon = None
        raw_id_weon = _get_row_value(row, "id_weon")
        if raw_id_weon is not None:
            val = str(raw_id_weon).strip()
            if val and val != "-":
                try:
                    id_weon = str(int(float(val)))
                except (ValueError, TypeError):
                    pass

        raw_status = _get_row_value(row, "status")
        raw_tipo_escala = _get_row_value(row, "tipo_escala")
        raw_supervisor = _get_row_value(row, "supervisor")
        raw_setor = _get_row_value(row, "setor")
        raw_obs = _get_row_value(row, "obs")

        funcionario = {
            "nome": str(nome).strip() if pd.notna(nome) else None,
            "matricula": _safe_matricula(matricula),
            "id_weon": id_weon,
            "id_huawei": id_huawei,
            "status": str(raw_status).strip().upper() if pd.notna(raw_status) else "ATIVO",
            "tipo_escala": str(raw_tipo_escala).strip() if pd.notna(raw_tipo_escala) else None,
            "supervisor": str(raw_supervisor).strip() if pd.notna(raw_supervisor) else None,
            "setor": str(raw_setor).strip() if pd.notna(raw_setor) else None,
            "obs": str(raw_obs).strip() if pd.notna(raw_obs) else None,
        }

        if funcionario["nome"] and funcionario["matricula"]:
            funcionarios.append(funcionario)

    return funcionarios


def import_funcionarios(db_path=None):
    """
    Principal: le todos os arquivos Excel e importa para o banco.
    Usa o mesmo caminho de banco que o runtime (connection.py).
    """
    from db.connection import get_connection

    excel_dir = Path(__file__).resolve().parent.parent / "instrucoes" / "lista-de-funcionarios"

    if not excel_dir.exists():
        print("[ERRO] Diretorio nao encontrado: {}".format(excel_dir))
        return

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Garantir que o schema do banco alvo esteja atualizado mesmo quando o script
        # for executado isoladamente, sem subir a aplicacao.
        from db.migrations import run_pending_migrations
        from db.schema_tools import ensure_schema_metadata_table

        ensure_schema_metadata_table(cursor)
        run_pending_migrations(cursor)
        conn.commit()

        print("[*] Processando arquivos em {}".format(excel_dir))
        print("[DB] Banco: {}\n".format(db_path))

        total_funcionarios = 0
        total_arquivos = 0
        erros = []
        reconciled_by_name = 0
        updated_by_matricula = 0
        inserted_new = 0

        by_matricula, by_normalized_name = _build_existing_lookup(cursor)

        excel_files = sorted(excel_dir.glob("*.xlsx"))

        for excel_file in excel_files:
            filename = excel_file.name
            if _should_skip_workbook(filename):
                print("[*] Ignorando {} (arquivo consolidado)".format(filename))
                continue

            print("[*] Processando {}...".format(filename), end=" ")

            file_info = parse_filename(filename)
            fallback_setor_id = file_info["setor_id"]
            fallback_escala = file_info["escala"]

            funcionarios = extract_funcionarios(excel_file)
            if not funcionarios:
                print("[!] Nenhum funcionario encontrado")
                continue

            importados = 0
            for func in funcionarios:
                try:
                    action = _upsert_funcionario(
                        cursor,
                        func,
                        fallback_setor_id,
                        fallback_escala,
                        by_matricula,
                        by_normalized_name,
                    )
                    if action == "reconciled_name":
                        reconciled_by_name += 1
                    elif action == "updated":
                        updated_by_matricula += 1
                    elif action == "inserted":
                        inserted_new += 1

                    importados += 1
                except Exception as e:
                    erros.append("{} - {}: {}".format(filename, func["nome"], str(e)))

            conn.commit()
            total_funcionarios += importados
            total_arquivos += 1
            print("[OK] {} funcionarios".format(importados))

        print("\n" + "=" * 60)
        print("[RESUMO] Importacao:")
        print("  - Arquivos processados: {}".format(total_arquivos))
        print("  - Total de funcionarios: {}".format(total_funcionarios))
        print("  - Atualizados por matricula: {}".format(updated_by_matricula))
        print("  - Reconciliados por nome: {}".format(reconciled_by_name))
        print("  - Novos inseridos: {}".format(inserted_new))

        if erros:
            print("\n[!] Erros encontrados ({}):".format(len(erros)))
            for erro in erros[:5]:
                print("    - {}".format(erro))
            if len(erros) > 5:
                print("    ... e mais {} erros".format(len(erros) - 5))

        cursor.execute("SELECT COUNT(*) as total FROM colaboradores")
        total_db = cursor.fetchone()["total"]

        cursor.execute("SELECT DISTINCT setor FROM colaboradores WHERE setor IS NOT NULL ORDER BY setor")
        setores = cursor.fetchall()

        cursor.execute("SELECT DISTINCT escala FROM colaboradores WHERE escala IS NOT NULL ORDER BY escala")
        escalas = cursor.fetchall()

        print("\n[DB] Estado do banco colaboradores:")
        print("  - Total de registros: {}".format(total_db))
        print("  - Setores: {}".format([s["setor"] for s in setores]))
        print("  - Escalas: {}".format([e["escala"] for e in escalas]))

        print("\n[OK] Importacao concluida!\n")
    finally:
        conn.close()


if __name__ == "__main__":
    import_funcionarios()
