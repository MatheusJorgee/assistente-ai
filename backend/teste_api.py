import os
import google.generativeai as genai
from dotenv import load_dotenv

# Carrega a sua chave do .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERRO: Chave API não encontrada no .env")
    exit()

genai.configure(api_key=api_key)

print("Consultando os servidores do Google...\n")
print("Modelos liberados para a sua chave:")

# Lista todos os modelos que servem para gerar texto (chat)
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f" -> {m.name}")
except Exception as e:
    print(f"Erro ao consultar: {e}")