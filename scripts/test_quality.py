import sys
import os
import asyncio
import json

# Setup paths to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from core.transcription import transcribe_audio, AI_PROVIDER_PRIORITY
from services import AZURE_SPEECH_KEY

async def test_transcription():
    audio_path = r"C:\Users\lucas.afonso\projetos\auditoria\ligacoes\test_download_1776135340-404299.wav"
    
    if not os.path.exists(audio_path):
        print(f"Erro: Arquivo {audio_path} não encontrado.")
        return
        
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
        
    print("Iniciando transcrição de teste com o orquestrador global...")
    print(f"Provider: {AI_PROVIDER_PRIORITY}")
    print(f"Azure Key Configured: {bool(AZURE_SPEECH_KEY)}")
    
    try:
        segments, metadata = await transcribe_audio(
            audio_file=audio_bytes,
            mime_type="audio/wav",
            operator_name="Operador Teste",
            driver_name="Motorista",
            return_metadata=True
        )
        
        print("\n=== METADATA DO ORQUESTRADOR ===")
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
        
        print("\n=== TRANSCRICAO RESULTANTE ===")
        for seg in segments:
            print(f"[{seg.get('start', '00:00')} - {seg.get('end', '00:00')}] {seg.get('text', '')}")
            
    except Exception as e:
        print(f"Erro durante o teste: {e}")

if __name__ == "__main__":
    asyncio.run(test_transcription())
