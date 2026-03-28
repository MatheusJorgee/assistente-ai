# 🚀 Guia de Setup - Quinta-Feira Fase 3

## O Que Foi Adicionado

### Frontend (v2.1+)
- ✅ react-markdown + remark-gfm para renderizar markdown
- ✅ Chat interface modernizado com tipografia melhorada
- ✅ Streaming de respostas em tempo real
- ✅ Error handling e status display
- ✅ Auto-scroll e timestamps

### Backend (v2.1+)
- ✅ `process_manager.py` - Controle de contexto de mídia por aplicativo
- ✅ `main_v2_dispositivos.py` - Backend com device hub e LAN support
- ✅ REST API para dispositivos e processos
- ✅ WebSocket com device routing
- ✅ Exposição em 0.0.0.0 para rede local

### Scripts
- ✅ `start_quintafeira.vbs` - Inicializador silencioso
- ✅ `stop_quintafeira.vbs` - Encerrador limpo
- ✅ `start_quintafeira_v2.ps1` - Gerenciador PowerShell completo

### Documentação
- ✅ `ARQUITETURA_FASE3.md` - Padrões e segurança
- ✅ `README.md` - Consolidado e limpo
- ✅ `GUIA_SETUP_FASE3.md` - Este arquivo

---

## ⚙️ Instalação Passo a Passo

### 1. Atualizar dependências Python

```bash
cd backend
pip install -r requirements.txt
```

**Novas dependências:**
- `psutil` - Detecção de processos
- `pygetwindow` - Controle de janelas Windows
- `react-markdown` / `remark-gfm` - Frontend (já no package.json)

### 2. Escolher qual main.py usar

Você pode usar **uma das duas opções**:

#### Opção A: Backend Legado (v2.0)
```bash
# Manter como está
python main.py
# WebSocket única conexão, Host apenas
# http://localhost:8000/ws
```

#### Opção B: Backend Novo (v2.1+ com Fase 3) - **RECOMENDADO**
```bash
# Renomear arquivo
mv main.py main_v20_legado.py
mv main_v2_dispositivos.py main.py

# Start
python main.py
# Múltiplos dispositivos, LAN support
# Endpoints REST: /api/devices, /api/processes
# WebSocket: /api/chat/ws, /api/device/{id}/ws
```

### 3. Configurar variáveis de ambiente

Criar/atualizar `backend/.env`:

```bash
# Backend Config
HOST=0.0.0.0                    # Para LAN (ou 127.0.0.1 para localhost)
PORT=8000
DEBUG=false

# CORS (adicionar IPs da LAN)
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://${SEU_PC_IP}:3000

# APIs (se usar)
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...
DATABASE_URL=sqlite:///database.db
```

### 4. Instalar dependências frontend

```bash
cd frontend
npm install  # Instala react-markdown e remark-gfm
npm run dev  # Inicia em http://localhost:3000
```

### 5. Iniciar Backend

**Opção A: Modo desenvolvimento**
```bash
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

**Opção B: Daemonizado (sem terminal visível)**

Windows:
```batch
# VBS silencioso
cscript scripts\start_quintafeira.vbs

# Ou PowerShell
.\scripts\start_quintafeira_v2.ps1 -Action start
```

Linux/Mac:
```bash
nohup python backend/main.py > backend/quintafeira.log 2>&1 &
```

### 6. Testar conexão

```bash
# Health check
curl http://localhost:8000/api/health

# Listar dispositivos
curl http://localhost:8000/api/devices

# Listar processos com mídia
curl http://localhost:8000/api/processes
```

---

## 📱 Acessar pelo Celular (LAN)

### 1. Descobrir IP do PC

```powershell
# Windows
ipconfig
# Procurar "IPv4 Address: 192.168.x.x"

# Linux/Mac
ifconfig
# Procurar "inet 192.168.x.x"
```

### 2. No celular (mesmo WiFi)

Abrir navegador e acessar:
```
http://192.168.x.x:3000
```

Exemplo: `http://192.168.1.100:3000`

### 3. Testar comandos

```
User: "Pausa o vídeo no Brave"

Backend:
1. Detecta Edge/Brave processo
2. Identifica mídia tipo VIDEO
3. Pausa apenas esse processo
4. Spotify/Music em outro navegador continua
```

---

## 🔍 Estrutura de Pastas Atualizada

```
assistente-ai/
├── README.md                          ← Consolidado
├── ARQUITETURA_FASE3.md              ← Novo: padrões e segurança
├── GUIA_SETUP_FASE3.md               ← Este arquivo
│
├── backend/
│   ├── main.py                       ← ATUALIZADO (v2.1+)
│   ├── main_v20_legado.py            ← Backup v2.0
│   ├── main_v2_dispositivos.py       ← Novo (v2.1+ com Fase 3)
│   ├── process_manager.py            ← NOVO: Process + Media Context
│   ├── brain_v2.py                   ← v2.1 Brain (mantém)
│   ├── requirements.txt               ← ATUALIZADO (psutil, etc)
│   ├── .env.example                  ← Template
│   ├── teste_sistema_v21.py          ← v2.1 tests (7 testes)
│   └── teste_novas_features.py       ← Feature tests (7 testes)
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx                  ← ATUALIZADO (markdown)
│   │   ├── layout.tsx                ← Mantém
│   │   └── globals.css               ← Mantém
│   ├── package.json                  ← ATUALIZADO (react-markdown)
│   └── tsconfig.json
│
├── scripts/
│   ├── start_quintafeira.ps1         ← Original (mantém)
│   ├── start_quintafeira.vbs         ← NOVO: VBS silencioso
│   ├── start_quintafeira_v2.ps1      ← NOVO: PowerShell completo
│   ├── stop_quintafeira.vbs          ← NOVO
│   └── install_startup_task.ps1      ← Original (mantém)
│
└── primeira_versao/                  ← v2.0 Backup
    ├── brain.py, brain_v2.py
    ├── falar.py, teste_api.py
    └── ...
```

---

## 🛠️ Troubleshooting

### Backend não inicia

```bash
# 1. Verificar Python
python --version  # Deve ser 3.10+

# 2. Verificar venv
.\backend\.venv\Scripts\activate

# 3. Verificar installation
pip list | grep -i psutil uvicorn
# Deve aparecer todas

# 4. Verificar porta
netstat -ano | findstr :8000
# Se ocupada: taskkill /PID {PID} /F

# 5. Logs detalhados
python main.py 2>&1 | Tee-Object -FilePath backend\error.log
```

### Frontend não conecta ao backend

```bash
# 1. Verificar backend rodando
curl http://localhost:8000/api/health

# 2. Verificar CORS no console browser
# DevTools → console (F12)
# Procurar "CORS policy" erro

# 3. Verificar porta 3000
netstat -ano | findstr :3000

# 4. Limpar cache frontend
cd frontend && npm cache clean --force
```

### LAN não funciona

```bash
# 1. Verificar IP
ipconfig /all
# Anote IPv4 address (ex: 192.168.1.100)

# 2. Verificar firewall Windows
# Painel de Controle → Windows Defender Firewall
# → Permitir outro aplicativo
# → Adicionar python.exe com porta 8000

# 3. Testar do celular
# Acessar: http://192.168.1.100:8000/api/health
# Deve retornar JSON

# 4. Se não funcionar, debug:
python main.py --host 0.0.0.0 2>&1 | tee debug.log
```

### Process Manager não detecta aplicativos

```bash
# 1. Verificar se ProcessManager iniciou
curl http://localhost:8000/api/processes

# 2. Se vazio, o sistema pode estar:
#    - Rodando sem nome "edge.exe", "brave.exe"
#    - Em uso exclusivo (permissões)

# 3. Testar detecção manual
python -c "
from process_manager import create_process_manager
import asyncio

async def test():
    pm = create_process_manager()
    processes = await pm.scan_processes()
    for pid, info in list(processes.items())[:10]:
        print(f'{info.name} - {info.process_type}')

asyncio.run(test())
"
```

---

## 📊 Validação Completa

Checklist para validar tudo funciona:

- [ ] Backend inicia sem erros
- [ ] Frontend conecta ao backend
- [ ] `/api/health` retorna 200 OK
- [ ] `/api/devices` retorna array vazio
- [ ] `/api/processes` retorna lista de processos
- [ ] WebSocket `/api/chat/ws` conecta
- [ ] Markdown renderiza corretamente em respostas
- [ ] Celular acessa http://192.168.x.x:3000
- [ ] Celular consegue enviar mensagens
- [ ] Backend daemonizado (sem terminal visível)

---

## 🚀 Próximos Passos

### Imediato (v2.1.1)
- [ ] Integração real com YouTube (Selenium/Playwright)
- [ ] Integração real com WhatsApp via pywhatkit
- [ ] Persistência de sessions em BD

### Próximo (v2.2)
- [ ] Autenticação com JWT
- [ ] Message encryption TLS 1.3
- [ ] Rate limiting por device
- [ ] Audit logging centralizado

### Futuro (v2.3+)
- [ ] Mobile app nativa
- [ ] Multi-language support
- [ ] Dashboard de analytics
- [ ] Plugin system

---

## 📞 Context Awareness - Exemplos Práticos

### Exemplo 1: Controle Smart de Áudio

```typescript
// User: "Pausa tudo menos YouTube"

Backend Response:
1. Scans all processes
2. Finds: [Chrome(YouTube), Spotify, Discord]
3. Pauses: Spotify, Discord
4. Keeps: YouTube playing
5. Sends notification to all devices
```

### Exemplo 2: Device Routing

```typescript
// Mobile user: "Abre Steam no PC"

Backend Response:
1. Routes command to Desktop device
2. Desktop receives WebSocket message
3. JavaScript abre Steam
4. Send confirmation back to mobile
```

### Exemplo 3: Markdown Rendering

```
User: "Lista minhas músicas favoritas"

Response (Markdown):
# Minhas Músicas Favoritas

## 2024 - Playlist Favoritos
- **Bohemian Rhapsody** - Queen (5:55)
- **Imagine** - John Lennon (3:03)
- **Stairway to Heaven** - Led Zeppelin (8:02)

## Recentes
| Música | Artista | Duração |
|--------|---------|---------|
| Blinding Lights | The Weeknd | 3:20 |
```

---

## ✅ Conclusão

Você agora tem:

1. ✅ Frontend moderno com markdown
2. ✅ Backend escalável com múltiplos dispositivos
3. ✅ Controle por contexto de mídia
4. ✅ Daemonização automática
5. ✅ Acesso via rede local
6. ✅ Documentação completa
7. ✅ Testes validando tudo

**Sistema pronto: 🟢 FASE 3 COMPLETA**

Para dúvidas, consulte:
- `README.md` - Visão rápida
- `ARQUITETURA_FASE3.md` - Detalhespadrões
- `backend/process_manager.py` - Docstrings no código
- `backend/main_v2_dispositivos.py` - API definitions

Bom uso! 🎉
