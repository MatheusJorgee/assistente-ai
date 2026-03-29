# 🚀 COMO RODAR A QUINTA-FEIRA v2.0

## Setup Inicial

### 1. Criar ambiente virtual
```bash
python -m venv .venv
```

### 2. Ativar ambiente virtual
**Windows (PowerShell)**:
```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD)**:
```cmd
.venv\Scripts\activate.bat
```

**Linux/Mac**:
```bash
source .venv/bin/activate
```

### 3. Instalar dependências
```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente
```bash
# Copy o template de .env
cp backend/.env.example backend/.env

# Edite backend/.env e adicione suas chaves reais:
# - GEMINI_API_KEY (obrigatório)
# - SPOTIFY_CLIENT_ID/SECRET (opcional, requer Premium)
# - ELEVENLABS_API_KEY (opcional)
```

---

## Rodando o Sistema

### Terminal 1 - Backend (FastAPI + WebSocket)
```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Esperado em console:
```
✓ [SISTEMA] Quinta-Feira Brain v2 Inicializada com sucesso
✓ [SISTEMA] Ferramentas disponíveis: 12
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Terminal 2 - Frontend (Next.js)
```bash
cd frontend
npm install  # primeira vez apenas
npm run dev
```

Esperado em console:
```
▲ Next.js 15.0.0
- ready started server on [::]:3000, url: http://localhost:3000
```

---

## Testando Conexão

1. Abra http://localhost:3000 no navegador
2. Abra DevTools (F12)
3. Vá a Network → WS (WebSockets)
4. Você deve ver conexão: `ws://localhost:8000/ws`
5. Digite uma mensagem e envie
6. Verifique resposta da IA em tempo real

---

## Troubleshooting

### ModuleNotFoundError: No module named 'backend'
✅ **CORRIGIDO** em v2.0.1
- Agora temos `backend/__init__.py`
- Imports com fallback em main.py, brain_v2.py e tools/__init__.py

### WebSocket connection failed
- Verifique se backend está rodando em http://127.0.0.1:8000
- Verifique ALLOWED_ORIGINS em backend/.env
- Abra DevTools para ver erro específico

### GEMINI_API_KEY not found
- Crie backend/.env com sua chave
- Rode `echo "Teste"` para verificar variáveis carregadas

### Erro ao conectar Spotify
- Spotify é opcional (apenas para Premium)
- Sistema funciona com YouTube mesmo sem Spotify
- Se quiser: registre app em https://developer.spotify.com

---

## Estrutura de Pastas

```
assistente-ai/
├── backend/
│   ├── __init__.py           ✨ NOVO - torna backend um package
│   ├── main.py               (import resiliente)
│   ├── brain_v2.py           (import resiliente)
│   ├── .env.example          ✨ NOVO - template de config
│   ├── core/
│   │   ├── __init__.py
│   │   └── tool_registry.py
│   ├── tools/
│   │   ├── __init__.py       (import resiliente)
│   │   ├── media_tools.py
│   │   └── ...
│   ├── automation.py
│   ├── database.py
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   └── page.tsx          (interface redesenhada)
│   └── package.json
└── README.md
```

---

## Recursos Principais

✨ **Quinta-Feira v2.0** oferece:

- **Tool Registry Pattern**: Ferramentas plugáveis
- **Dependency Injection**: Sem acoplamento
- **Event Bus**: Logs táticos em tempo real
- **WebSocket Bidirecional**: Chat em tempo real
- **Gemini 2.5 Flash**: LLM poderoso
- **Tool Calling**: Automação inteligente
- **Visão Computacional**: Análise de screenshots
- **Memória de Longo Prazo**: SQLite persistido
- **Modo voz**: Speech recognition + TTS

---

## Development

### Rodar testes
```bash
cd backend
python teste_sistema_v2.py
```

### Recarregar auto (watch mode)
```bash
uvicorn main:app --reload
```

### Limpar cache Python
```bash
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

---

## Production (Recomendado)

```bash
# Backend
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000

# Frontend
npm run build
npm start
```

---

**Version**: 2.0.1  
**Last Updated**: 28/03/2026  
**Status**: ✅ Funcionando
