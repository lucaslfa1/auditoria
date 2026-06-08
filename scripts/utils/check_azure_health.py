import os
import requests
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv("backend/.env", override=True)

def check_azure_openai(endpoint, key, deployment, name):
    if not endpoint or not key:
        print(f"❌ {name}: Chaves ausentes no .env")
        return
    
    try:
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=key,
            api_version="2024-06-01"
        )
        # Teste básico
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": "teste de ping"}],
            max_tokens=5
        )
        print(f"✅ {name} ({deployment}): Conectado com sucesso!")
    except Exception as e:
        print(f"❌ {name} ({deployment}): FALHA de conexão - {type(e).__name__}: {e}")

def check_text_analytics(endpoint, key):
    if not endpoint or not key:
        print(f"❌ Text Analytics: Chaves ausentes no .env")
        return
    
    url = f"{endpoint.rstrip('/')}/language/:analyze-text?api-version=2024-11-01"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/json"
    }
    body = {
        "kind": "SentimentAnalysis",
        "parameters": {"modelVersion": "latest"},
        "analysisInput": {"documents": [{"id": "1", "language": "pt", "text": "Teste incrível!"}]}
    }
    try:
        response = requests.post(url, headers=headers, json=body)
        if response.status_code == 200:
            print(f"✅ Text Analytics: Conectado com sucesso!")
        else:
            print(f"❌ Text Analytics: Erro HTTP {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Text Analytics: FALHA de rede - {e}")

if __name__ == "__main__":
    print(f"=== TESTE RÁPIDO DE CRENDENCIAIS AZURE ({os.getcwd()}) ===\n")
    
    # 1. GPT-4o
    check_azure_openai(
        os.getenv("AZURE_OPENAI_ENDPOINT"),
        os.getenv("AZURE_OPENAI_KEY"),
        os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "1. GPT-4o Principal"
    )
    
    # 2. Whisper Legado
    check_azure_openai(
        os.getenv("AZURE_WHISPER_ENDPOINT"),
        os.getenv("AZURE_WHISPER_KEY"),
        os.getenv("AZURE_WHISPER_DEPLOYMENT", "whisper"),
        "5. Whisper Legado"
    )
    
    # 3. Text Analytics
    check_text_analytics(
        os.getenv("AZURE_TEXT_ANALYTICS_ENDPOINT"),
        os.getenv("AZURE_TEXT_ANALYTICS_KEY")
    )
    
    # 4. Azure Speech (ponto rápido, se falhar auth token levanta excessão se a região tiver errada)
    speech_region = os.getenv("AZURE_SPEECH_REGION")
    speech_key = os.getenv("AZURE_SPEECH_KEY")
    if speech_region and speech_key:
        resp = requests.post(
            f"https://{speech_region}.api.cognitive.microsoft.com/sts/v1.0/issueToken",
            headers={"Ocp-Apim-Subscription-Key": speech_key}
        )
        if resp.status_code == 200:
             print(f"✅ Speech Services ({speech_region}): Autorizado com sucesso!")
        else:
             print(f"❌ Speech Services: FALHA HTTP {resp.status_code}")
    else:
        print(f"❌ Speech Services: Chaves ausentes no .env")

    print("\nLembrete: O modelo de Diarização da Foundry ('gpt-4o-transcribe-diarize') é difícil de testar via texto, então rodaremos ele nos testes gerais de áudio depois.")
