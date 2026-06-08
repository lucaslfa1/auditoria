from google import genai
import os
from dotenv import load_dotenv

load_dotenv('backend/.env')
api_key = os.getenv('AI_API_KEY')
client = genai.Client(api_key=api_key)

print("Available models:")
for model in client.models.list():
    print(model.name)
