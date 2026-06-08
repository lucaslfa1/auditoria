"""Levanta auditorias zeradas por senha que podem ser falso-positivo
de digitos ditados separadamente pelo STT.

Estrategia:
1. Busca audits com score=0 + summary mencionando senha (incluindo fatal_flags).
2. Para cada uma, varre a transcricao buscando padroes de digitos partidos
   (ex: "0, 2, 5, 5" ou "0 2 5 5" ou "02, 5, 5").
3. Lista as candidatas com trecho da transcricao para revisao manual.

NAO re-audita (sem custo Azure). Decisao de reauditar fica com Lucas
depois de inspecionar a lista.

Uso:
    python -m scripts.check_senha_zerada_falso_positivo [--days N]

Default: 30 dias.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import db.database as database  # noqa: E402

# Padroes do STT separando digitos em sequencia:
# - "0, 2, 5, 5" ou "0,2,5,5"
# - "0 2 5 5"
# - "0-2-5-5"
# - "02, 5, 5" (digitos parcialmente agrupados)
# Detecta 3+ tokens numericos (1-3 digitos cada) separados por virgula, espaco
# ou hifen, totalizando 3-12 digitos quando concatenados.
_RE_DIGITOS_PARTIDOS = re.compile(
    r"\b\d{1,3}\s*[,\-\s]\s*\d{1,3}\s*[,\-\s]\s*\d{1,3}(?:\s*[,\-\s]\s*\d{1,3}){0,3}\b"
)

_SENHA_HINTS = ("senha", "Senha", "SENHA")
_ZERAGEM_HINTS = ("zerada", "Nota zerada", "[ATENÇÃO", "violação não-negociável")


def _has_senha_signal(summary: str | None, details_json: str | None) -> bool:
    text = (summary or "").lower()
    if "senha" in text:
        return True
    if details_json:
        try:
            details = json.loads(details_json)
        except Exception:
            details = []
        if isinstance(details, list):
            for d in details:
                if not isinstance(d, dict):
                    continue
                label = str(d.get("label") or "").lower()
                criterion_id = str(d.get("criterionId") or "").lower()
                if d.get("status") == "fail" and ("senha" in label or "senha" in criterion_id):
                    return True
    return False


def _is_zerada(score: float | None, summary: str | None) -> bool:
    if score is not None and float(score) == 0.0:
        return True
    text = (summary or "")
    return any(h in text for h in _ZERAGEM_HINTS)


_RE_TIMESTAMP_LIKE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")


def _extrair_trechos_suspeitos(transcription_json: str | None) -> list[str]:
    if not transcription_json:
        return []
    try:
        segs = json.loads(transcription_json)
    except Exception:
        return []
    if not isinstance(segs, list):
        return []

    trechos: list[str] = []
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        # Excluir trechos com timestamps (ex: '2026-05-02') que dao falso match.
        if _RE_TIMESTAMP_LIKE.search(text):
            continue
        match = _RE_DIGITOS_PARTIDOS.search(text)
        if not match:
            continue
        # Filtro: tamanho concatenado da sequencia tem que parecer senha (3-6 digitos).
        # CPF tem 11 - exclui. Telefone tem 10-11 - exclui.
        if not _looks_like_dictado_curto(match.group(0)):
            continue
        falante = seg.get("speaker") or seg.get("falante") or "?"
        inicio = seg.get("start") or seg.get("startTime") or "?"
        trechos.append(f"[{inicio}|{falante}] {text}")
    return trechos


def _looks_like_dictado_curto(token: str) -> bool:
    """Quando os digitos concatenados batem com tamanho de senha (3-6)."""
    digits = re.sub(r"\D", "", token)
    return 3 <= len(digits) <= 6


_DIAG = {"total_rows": 0, "passou_zerada": 0, "passou_senha": 0, "passou_regex": 0}


def listar_candidatas(days: int) -> Iterable[dict]:
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id,
                   COALESCE(audit_date, timestamp) AS dt,
                   operator_name, sector_id, alert_label,
                   score, summary, details_json, transcription_json
            FROM audits
            WHERE discarded_at IS NULL
              AND COALESCE(audit_date, timestamp) >= (NOW() - (%s || ' days')::interval)::text
              AND score = 0
            ORDER BY COALESCE(audit_date, timestamp) DESC
            """,
            (str(days),),
        )
        rows = cursor.fetchall()
        _DIAG["total_rows"] = len(rows)
    finally:
        conn.close()

    for row in rows:
        if not _is_zerada(row.get("score"), row.get("summary")):
            continue
        _DIAG["passou_zerada"] += 1
        if not _has_senha_signal(row.get("summary"), row.get("details_json")):
            continue
        _DIAG["passou_senha"] += 1

        trechos = _extrair_trechos_suspeitos(row.get("transcription_json"))
        if not trechos:
            continue
        _DIAG["passou_regex"] += 1

        yield {
            "id": row["id"],
            "dt": row["dt"],
            "operator_name": row["operator_name"],
            "sector_id": row["sector_id"],
            "alert_label": row.get("alert_label"),
            "trechos_suspeitos": trechos,
            "summary_excerpt": (row.get("summary") or "")[:200],
        }


def _dump_senha_contexts(days: int) -> None:
    """Inspeciona TODAS as zeradas com sinal de senha, sem filtro de regex.

    Util para entender como o STT esta transcrevendo a senha de fato.
    """
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, COALESCE(audit_date, timestamp) AS dt,
                   operator_name, sector_id, alert_label,
                   summary, transcription_json
            FROM audits
            WHERE discarded_at IS NULL
              AND COALESCE(audit_date, timestamp) >= (NOW() - (%s || ' days')::interval)::text
              AND score = 0
            ORDER BY COALESCE(audit_date, timestamp) DESC
            """,
            (str(days),),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    print(f"\n[DUMP] {len(rows)} auditoria(s) zerada(s) nos ultimos {days} dias.")
    print("Mostrando trechos com 'senha' ou digitos isolados ao lado:\n")
    for row in rows:
        if not row.get("transcription_json"):
            continue
        try:
            segs = json.loads(row["transcription_json"])
        except Exception:
            continue
        if not isinstance(segs, list):
            continue

        print(f"== audit_id={row['id']} | {row['dt']} | {row['operator_name']} | {row['sector_id']} | {row['alert_label']} ==")
        print(f"   summary: {(row.get('summary') or '')[:200]}")
        senha_found = False
        for i, seg in enumerate(segs):
            if not isinstance(seg, dict):
                continue
            text = str(seg.get("text") or "")
            if "senha" in text.lower() or re.search(r"\d", text):
                falante = seg.get("speaker") or seg.get("falante") or "?"
                inicio = seg.get("start") or "?"
                if "senha" in text.lower() or _RE_DIGITOS_PARTIDOS.search(text):
                    senha_found = True
                    print(f"   [{inicio}|{falante}] {text}")
        if not senha_found:
            print("   (nenhum trecho com 'senha' ou digitos)")
        print("-" * 100)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30, help="Janela em dias (default 30)")
    parser.add_argument("--dump", action="store_true", help="Mostra trechos completos sem filtro de regex")
    args = parser.parse_args()

    if args.dump:
        _dump_senha_contexts(args.days)
        return 0

    candidatas = list(listar_candidatas(args.days))
    print(f"\n[DIAG] Total score=0 nos ultimos {args.days} dias: {_DIAG['total_rows']}")
    print(f"[DIAG] Passou filtro zerada: {_DIAG['passou_zerada']}")
    print(f"[DIAG] Passou filtro senha:  {_DIAG['passou_senha']}")
    print(f"[DIAG] Passou regex digitos: {_DIAG['passou_regex']}")
    if not candidatas:
        print(f"\nNenhuma auditoria zerada por senha com digitos partidos nos ultimos {args.days} dias.")
        return 0

    print(f"\nEncontradas {len(candidatas)} auditoria(s) suspeita(s) nos ultimos {args.days} dias:\n")
    print("=" * 100)
    for c in candidatas:
        print(f"audit_id: {c['id']}")
        print(f"  data:        {c['dt']}")
        print(f"  operador:    {c['operator_name']}")
        print(f"  setor:       {c['sector_id']}")
        print(f"  alerta:      {c['alert_label']}")
        print(f"  summary:     {c['summary_excerpt']}")
        print(f"  trechos suspeitos ({len(c['trechos_suspeitos'])}):")
        for t in c['trechos_suspeitos'][:5]:
            print(f"    - {t}")
        if len(c['trechos_suspeitos']) > 5:
            print(f"    ... e mais {len(c['trechos_suspeitos']) - 5} trechos")
        print("-" * 100)

    print(f"\nTotal: {len(candidatas)} candidata(s) a re-auditoria com prompt v1.3.90.")
    print("Inspecione manualmente e decida quais re-auditar (custo Azure ~$0.01 por audit).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
