import asyncio
import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from brain_v2 import QuintaFeiraBrain

app = FastAPI(
    title="Quinta-Feira Modular Core v2",
    description="Backend FastAPI com Tool Registry e Injeção de Dependência"
)


def _parse_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


ALLOWED_ORIGINS = _parse_allowed_origins()
ALLOW_CREDENTIALS = os.getenv("ALLOW_CREDENTIALS", "false").lower() == "true"

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

brain = QuintaFeiraBrain()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    print(">>> [CONEXÃO] Dispositivo host conectado.")
    
    try:
        while True:
            # Recebemos a mensagem do host
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            
            user_input = data.get("payload", "")
            intent = data.get("type", "chat") 

            if intent == "chat":
                # O brain.ask devolve uma STRING no formato JSON perfeito: {"text": "...", "audio": "..."}
                resposta_json_string = await asyncio.to_thread(brain.ask, user_input)
                
                # CORREÇÃO ARQUITETURAL: Enviamos essa string diretamente! Sem criar "JSON dentro de JSON"
                await websocket.send_text(resposta_json_string)
                
    except WebSocketDisconnect:
        print(">>> [LIMPEZA] Host desconectado. Encerrando sessão sem rastros.")
    except Exception as e:
        print(f">>> [ERRO] Falha na orquestração: {e}")