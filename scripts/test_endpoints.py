import asyncio
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# load environment
BASE_DIR = Path(r"d:\auditoria\backend")
load_dotenv(BASE_DIR / ".env", override=True)

sys.path.append(str(BASE_DIR))
from services import transcribe_audio_azure, evaluate_with_azure
from schemas import AuditAlert, AuditCriterion

async def main():
    try:
        print("Testando transcrição via Azure SpeechToText...")
        audio_path = r"d:\sentinel-open\part1.wav"
        if not os.path.exists(audio_path):
            print(f"Arquivo não encontrado: {audio_path}")
            return

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        
        transcription = transcribe_audio_azure(audio_bytes, "Operador Lucas", "Motorista João")
        print("Transcrição Concluída!")
        print(json.dumps(transcription, ensure_ascii=False, indent=2)[:500] + "...\n")
    except Exception as e:
        print(f"ERRO NO SPEECH: {e}")
        return
        
    try:
        print("\nTestando avaliação via Azure OpenAI (GPT-4o)...")
        crit1 = AuditCriterion(id="1", label="Identificação", weight=10.0, description="Operador deve falar o nome do motorista e o próprio nome.")
        alert = AuditAlert(id="a", label="Teste", context="Auditoria de teste, o operador liga para verificar rota.", criteria=[crit1])
        
        evaluation = await evaluate_with_azure(transcription, alert, alert.criteria, "Lucas")
        print("Avaliação Concluída!")
        print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"ERRO NO OPENAI: {e}")

    try:
        from classification import classify_audio
        print("\nTestando classificação geral (NLP GPT-4o)...")
        classification_result = await classify_audio(audio_bytes, "part1.wav")
        import dataclasses
        print("Classificação Concluída:")
        print(json.dumps(dataclasses.asdict(classification_result), ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"ERRO NA CLASSIFICAÇÃO: {e}")

if __name__ == "__main__":
    asyncio.run(main())
