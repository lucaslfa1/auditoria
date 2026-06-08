import asyncio
import os
import sys
import json
import traceback
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(r"d:\auditoria\backend")
load_dotenv(BASE_DIR / ".env", override=True)
sys.path.append(str(BASE_DIR))

from services import (
    transcribe_audio, evaluate_with_ai_priority, result_from_raw,
    AI_PROVIDER_PRIORITY, AI_API_KEY, AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT, AZURE_SPEECH_KEY
)
from schemas import AuditAlert, AuditCriterion

async def main():
    print(f"AI_PROVIDER_PRIORITY: {AI_PROVIDER_PRIORITY}")
    print(f"AI_API_KEY: {'SET' if AI_API_KEY else 'NOT SET'}")
    print(f"AZURE_OPENAI_KEY: {'SET' if AZURE_OPENAI_KEY else 'NOT SET'}")
    print(f"AZURE_OPENAI_ENDPOINT: {AZURE_OPENAI_ENDPOINT or 'NOT SET'}")
    print(f"AZURE_SPEECH_KEY: {'SET' if AZURE_SPEECH_KEY else 'NOT SET'}")
    print()

    audio_path = r"d:\sentinel-open\part1.wav"
    if not os.path.exists(audio_path):
        print(f"Audio not found: {audio_path}")
        return

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    # Step 1: Transcription
    print("=== STEP 1: Transcrição ===")
    try:
        transcription = await transcribe_audio(audio_bytes, "audio/wav", "Lucas", None)
        print(f"OK - {len(transcription)} segments")
        for seg in transcription[:3]:
            print(f"  {seg.get('start','?')} - {seg.get('text','')[:80]}")
    except Exception as e:
        print(f"FALHOU: {e}")
        traceback.print_exc()
        return

    # Step 2: Evaluation
    print("\n=== STEP 2: Avaliação ===")
    crit1 = AuditCriterion(id="1", label="Identificação", weight=10.0, description="Operador se identifica com nome, setor e empresa")
    crit2 = AuditCriterion(id="2", label="Cordialidade", weight=10.0, description="Operador é cordial e educado")
    alert = AuditAlert(id="4.1.1", label="Alerta Prioritário", context="Ligação de alerta prioritário ao motorista", criteria=[crit1, crit2])

    try:
        evaluation = await evaluate_with_ai_priority(transcription, alert, alert.criteria, "Lucas")
        print(f"OK - Evaluation keys: {list(evaluation.keys())}")
        print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"FALHOU: {e}")
        traceback.print_exc()
        return

    # Step 3: Build result
    print("\n=== STEP 3: Resultado Final ===")
    try:
        result = result_from_raw(evaluation, alert.criteria, transcription, "Lucas", "001")
        print(f"Score: {result.score} / {result.maxPossibleScore}")
        print(f"Summary: {result.summary[:200]}")
        print(f"Details: {len(result.details)} items")
        for d in result.details:
            print(f"  [{d.status}] {d.label}: {d.obtainedScore}/{d.weight} - {d.comment[:60]}")
    except Exception as e:
        print(f"FALHOU: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
