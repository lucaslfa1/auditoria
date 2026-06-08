"""Validacao e2e (read-only) do smart windowing (CLASSIFICATION_TRIM_LEADING_SILENCE).

Compara, em itens reais 'desconhecido' de logistica, a classificacao com a janela
de triagem SEM trim (legado) vs COM trim do silencio/URA inicial. Mostra se o trim
faz a IA sair de 'desconhecido' para um alerta valido.

NAO escreve no banco (so SELECT + chamadas Azure/GPT). Precisa de um ambiente com:
  - DATABASE_URL (Neon)             -> ja no .env
  - acesso ao GCS (google-cloud-storage + credenciais) -> p/ carregar o audio
  - credenciais Azure (Whisper + OpenAI) -> ja no .env

Uso:
  python scripts/validate_trim_leading_silence.py [N]
  (N = quantos itens validar; default 3)
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import database  # noqa: E402
from core.automation import load_classified_audio  # noqa: E402
from core.classification import (  # noqa: E402
    transcribe_for_classification,
    classify_with_gpt,
    align_classification_with_catalog,
    get_mime_type,
)

FLAG = "CLASSIFICATION_TRIM_LEADING_SILENCE"


async def _classify_with_trim(audio_bytes: bytes, mime: str, filename: str, trim: bool) -> dict:
    # transcribe_for_classification chama truncate_audio, que le a env FLAG.
    prev = os.environ.get(FLAG)
    os.environ[FLAG] = "true" if trim else "false"
    try:
        transc = await transcribe_for_classification(audio_bytes, mime)
    finally:
        if prev is None:
            os.environ.pop(FLAG, None)
        else:
            os.environ[FLAG] = prev
    c = await classify_with_gpt(transc, filename)
    c["_filename"] = filename
    c = align_classification_with_catalog(c)
    return {
        "alert": c.get("alert_id"),
        "sector": c.get("sector_id"),
        "conf": c.get("confidence"),
        "transc_len": len(transc or ""),
    }


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT input_hash, nome_arquivo,
               metadata_json::jsonb->>'classified_audio_path' AS path,
               metadata_json::jsonb->>'huawei_duration' AS dur
        FROM fila_revisao_classificacao
        WHERE alerta_previsto='desconhecido' AND setor_previsto='logistica'
        ORDER BY (metadata_json::jsonb->>'huawei_duration')::int ASC
        LIMIT %s
        """,
        (limit,),
    )
    items = cur.fetchall()
    conn.close()

    if not items:
        print("Nenhum item logistica 'desconhecido' encontrado.")
        return

    melhoraram = 0
    for it in items:
        ih, fn, path, dur = it["input_hash"], it["nome_arquivo"], it["path"], it["dur"]
        print("=" * 76)
        print(f"ITEM {fn[:58]} | dur={dur}s")
        try:
            audio = load_classified_audio(path, input_hash=ih)
        except Exception as exc:  # noqa: BLE001
            print(f"  >> ERRO ao carregar audio: {exc}")
            continue
        if not audio:
            print("  >> SEM AUDIO (path nao resolveu)")
            continue
        mime = get_mime_type(fn)
        try:
            off = await _classify_with_trim(audio, mime, fn, trim=False)
            on = await _classify_with_trim(audio, mime, fn, trim=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  >> ERRO na classificacao: {exc}")
            continue
        print(f"  SEM trim (legado): alerta={off['alert']:<22} conf={off['conf']} (transc {off['transc_len']}ch)")
        print(f"  COM trim         : alerta={on['alert']:<22} conf={on['conf']} (transc {on['transc_len']}ch)")
        if off["alert"] == "desconhecido" and on["alert"] not in ("desconhecido", None):
            melhoraram += 1
            print("  >> GANHO: trim tirou de 'desconhecido' para um alerta valido")
        elif off["alert"] != on["alert"]:
            print("  >> mudou de alerta (revisar manualmente)")
        else:
            print("  >> sem mudanca (truncamento nao era a causa neste item)")

    print("=" * 76)
    print(f"RESUMO: {melhoraram}/{len(items)} itens sairam de 'desconhecido' com o trim ligado.")


if __name__ == "__main__":
    asyncio.run(main())
