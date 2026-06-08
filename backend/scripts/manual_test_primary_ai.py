import os

from dotenv import load_dotenv
from google import genai


load_dotenv()

try:
    print("Importing AI client...")
    api_key = os.getenv("AI_API_KEY")
    model_name = os.getenv("AI_MODEL") or "gemini-2.5-flash"
    client = genai.Client(api_key=api_key)
    print("Client created successfully.")
    print(f"API Key present: {bool(api_key)}")

    print("Testing configured text generation model...")
    response = client.models.generate_content(
        model=model_name,
        contents="Hello, world!",
    )
    print(f"Response: {response.text}")
except Exception as exc:
    print(f"Error: {exc}")
