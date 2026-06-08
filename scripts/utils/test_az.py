import os
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv("backend/.env")

client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
    api_key=os.getenv("AZURE_OPENAI_KEY", ""),
    api_version="2025-01-01-preview"
)

try:
    print(f"Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT')}")
    print(f"Deployment: {os.getenv('AZURE_OPENAI_DEPLOYMENT')}")
    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=10
    )
    print("SUCCESS!")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"ERROR: type={type(e)} message={e}")

