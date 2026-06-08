"""Benchmark comparativo entre engines de transcricao.

Engines testados: fast, hybrid_dual, whisper, gpt4o_diarize.

Para cada combinacao (engine, audio) imprime:
- Wall clock
- Numero de segmentos
- Texto completo (rotulado por speaker)

Uso:
    python scripts/benchmark_engines.py [audio1.wav audio2.wav ...]

Sem argumentos, usa test_69.wav.
"""

import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Carrega .env
ENV_PATH = ROOT / "backend" / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

# Desliga selector pra medir engine puro
os.environ["TRANSCRIPTION_CANDIDATE_SELECTOR_ENABLED"] = "false"
# Libera hybrid_dual pra realmente rodar quando pedido
os.environ["AZURE_TRANSCRIPTION_ALLOW_LEGACY_HYBRID_DUAL"] = "true"
os.environ.setdefault("AI_PROVIDER_PRIORITY", "azure")


def _fmt_segments(segs):
    if not segs:
        return "<vazio>"
    return "\n".join(
        f"  [{s.get('speaker','?'):8s}] {s.get('text','').strip()}"
        for s in segs
    )


async def run_engine(engine: str, audio_bytes: bytes, audio_label: str):
    os.environ["AZURE_TRANSCRIPTION_ENGINE"] = engine
    from importlib import reload
    import core.transcription as t
    reload(t)

    label = f"{audio_label} :: {engine}"
    print(f"\n--- {label} ---", flush=True)
    t0 = time.monotonic()
    try:
        segs = await t.transcribe_audio(
            audio_bytes,
            mime_type="audio/wav",
            operator_name="Operador",
            driver_name="Motorista",
            alert=None,
            sector_id=None,
            return_metadata=False,
        )
    except Exception as exc:
        elapsed = time.monotonic() - t0
        tb = traceback.format_exc().splitlines()[-3:]
        print(f"FALHOU em {elapsed:.1f}s: {type(exc).__name__}: {exc}")
        for ln in tb:
            print(f"  {ln}")
        return {"engine": engine, "audio": audio_label, "elapsed": elapsed, "segs": [], "err": str(exc)}
    elapsed = time.monotonic() - t0
    text_concat = " ".join(s.get("text", "") for s in segs).strip()
    print(f"Tempo:     {elapsed:.1f}s")
    print(f"Segmentos: {len(segs)}")
    print(f"Chars:     {len(text_concat)}")
    print(_fmt_segments(segs))
    return {"engine": engine, "audio": audio_label, "elapsed": elapsed, "segs": segs, "chars": len(text_concat)}


async def main():
    if len(sys.argv) > 1:
        audios = [Path(a) for a in sys.argv[1:]]
    else:
        audios = [ROOT / "test_69.wav"]

    engines = ["fast", "hybrid_dual", "whisper", "gpt4o_diarize"]

    all_results = []
    for audio_path in audios:
        if not audio_path.exists():
            print(f"AVISO: {audio_path} nao existe, pulando")
            continue
        audio_bytes = audio_path.read_bytes()
        label = audio_path.name
        print(f"\n========== AUDIO: {label} ({len(audio_bytes)/1024:.1f} KB) ==========")
        for engine in engines:
            r = await run_engine(engine, audio_bytes, label)
            all_results.append(r)

    print("\n\n=========== RESUMO ===========")
    print(f"{'audio':40s} {'engine':14s} {'tempo':>7s} {'chars':>6s} {'segs':>4s}  status")
    for r in all_results:
        status = "OK" if "err" not in r else f"ERR: {r['err'][:40]}"
        print(f"{r['audio'][:40]:40s} {r['engine']:14s} {r['elapsed']:6.1f}s {r.get('chars', 0):6d} {len(r['segs']):4d}  {status}")


if __name__ == "__main__":
    asyncio.run(main())
