# 🎯 ARQUITETURA VISUAL - QUINTA-FEIRA v2.0 AUTO-START

---

## 📊 FLUXO COMPLETO (Do PC a Interface)

```
┌─────────────────────────────────────────────────────────────────┐
│                    QUINTA-FEIRA AUTO-START FLOW                 │
└─────────────────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════╗
║  TRIGGER (Escolhe 1)                                             ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  1️⃣  PC AUTO-BOOT                                               ║
║     └─ Windows Startup → quinta_feira.vbs                        ║
║                                                                  ║
║  2️⃣  DESKTOP SHORTCUT                                            ║
║     └─ Duplo clique "Quinta-Feira.lnk"                          ║
║                                                                  ║
║  3️⃣  MANUAL EXECUTION                                            ║
║     └─ & "quinta_feira.vbs" (PowerShell)                         ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
                              ↓
╔══════════════════════════════════════════════════════════════════╗
║  VBScript Execution (quinta_feira.vbs)                           ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  ⚙️  1. VALIDAÇÃO (50ms)                                         ║
║     └─ Verifica: backend/start_hub.py existe?                    ║
║        ❌ Se não → Msgbox error + Exit                           ║
║        ✅ Se sim → Continua                                      ║
║                                                                  ║
║  🔍 2. CHROME DETECTION (200ms)                                 ║
║     └─ Procura Chrome em 3 localizações:                         ║
║        ├─ C:\Program Files\Google\Chrome\Application\chrome.exe ║
║        ├─ C:\Program Files (x86)\Google\Chrome\...              ║
║        ├─ C:\Program Files\Chromium\Application\chrome.exe      ║
║        └─ PATH (fallback)                                        ║
║                                                                  ║
║  ⚡ 3. BACKEND START (1 segundo)                                ║
║     └─ Comando: pythonw backend/start_hub.py --port 8080        ║
║        └─ Flags: 0 (invisível) + async (não bloqueia)           ║
║                                                                  ║
║  ⏱️  4. SLEEP (3 segundos)                                      ║
║     └─ Razão: Uvicorm precisa de tempo para listen port 8080    ║
║        └─ Se não espera: Chrome connection refused!             ║
║                                                                  ║
║  🌐 5. CHROME LAUNCH (1 segundo)                                ║
║     └─ Comando: chrome.exe --app=http://localhost:3000          ║
║        └─ Flags: --app (app mode, sem browser UI)               ║
║                  --profile-directory=Default                     ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
                              ↓ (4-5 segundos total)
╔══════════════════════════════════════════════════════════════════╗
║  BACKEND INITIALIZATION (Simultâneo)                             ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Python Process Tree:                                            ║
║  └─ pythonw.exe (Windows native python)                          ║
║     └─ Invisível (sem console window)                            ║
║     └─ FastAPI Uvicorn                                           ║
║        ├─ Bind: 127.0.0.1:8080                                   ║
║        ├─ Tool Registry initialized                              ║
║        ├─ Triple Firewall active                                 ║
║        ├─ EventBus ready                                         ║
║        └─ WebSocket endpoint: /ws                                ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
                              ↓ (após sleep 3s)
╔══════════════════════════════════════════════════════════════════╗
║  CHROME LAUNCH (APP MODE)                                        ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Chrome Window:                                                  ║
║  ┌──────────────────────────────────────────────────┐            ║
║  │                                                  │            ║
║  │         QUINTA-FEIRA INTERFACE                  │            ║
║  │      (Sem barra de endereços)                    │            ║
║  │      (Sem abas)                                  │            ║
║  │      (Sem menu)                                  │            ║
║  │      (Parece app nativa)                         │            ║
║  │                                                  │            ║
║  └──────────────────────────────────────────────────┘            ║
║     ↑                                                             ║
║     Renders: http://localhost:3000 (Next.js Frontend)           ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
                              ↓
╔══════════════════════════════════════════════════════════════════╗
║  FRONTEND CONNECTION (Next.js 15)                                ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  Browser Context:                                                ║
║  └─ Next.js SSR rendered                                         ║
║     └─ Reads: process.env.NEXT_PUBLIC_WS_PORT                    ║
║        └─ Value: 8080 ✅                                         ║
║     └─ WebSocket Client                                          ║
║        └─ Connect: ws://localhost:8080/ws                        ║
║        └─ Status: "Online" ✅                                    ║
║                                                                  ║
║  Dependencies Loaded:                                            ║
║  ├─ Web Speech API (voice input)                                 ║
║  ├─ Audio playback (responses)                                   ║
║  ├─ Event listeners (keyboard shortcuts)                         ║
║  └─ Real-time updates (WebSocket)                                ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
                              ↓
╔══════════════════════════════════════════════════════════════════╗
║  BACKEND WEBSOCKET HANDLER                                       ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  /ws Endpoint (FastAPI):                                         ║
║  └─ Frame receive                                                ║
║     ├─ Type 1: SPEECH_INPUT (base64 audio)                      ║
║     │  └─ Triple Firewall validation                             ║
║     │  └─ Send to Gemini 2.5 Flash                              ║
║     │                                                            ║
║     ├─ Type 2: COMMAND (text)                                    ║
║     │  └─ Tool Registry lookup                                   ║
║     │  └─ Execute with safety checks                             ║
║     │                                                            ║
║     └─ Response: JSON frame                                      ║
║        ├─ status: "success" / "error"                            ║
║        ├─ data: { response, actions, ... }                       ║
║        └─ Send back to frontend                                  ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
                              ↓
╔══════════════════════════════════════════════════════════════════╗
║  ✅ SYSTEM OPERATIONAL                                           ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  User Can Now:                                                   ║
║  ✓ Speak (voice input)                                           ║
║  ✓ Type commands                                                 ║
║  ✓ Receive audio responses                                       ║
║  ✓ See real-time actions                                         ║
║  ✓ Control system (terminal, media, etc)                         ║
║                                                                  ║
║  Backend Status:                                                 ║
║  ✓ Uvicorm listening (port 8080)                                 ║
║  ✓ Tool Registry active                                          ║
║  ✓ Gemini 2.5 Flash ready                                        ║
║  ✓ Triple Firewall protecting                                    ║
║  ✓ Memory persisted                                              ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────┐
│                  ⏱️ TOTAL TIME: 4-5 SECONDS                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🗂️ LAYERED ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│              DESKTOP / SYSTEM LAYER                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Desktop Shortcut]  [Windows Startup]  [Manual Run]       │
│        (.lnk)              (shell:)          (CLI)          │
│         |                     |                |            │
│         └─────────────────────┴────────────────┘            │
│                       |                                     │
│              VBScript Executor                             │
│           (wscript.exe native)                             │
│                       |                                     │
└─────────────────────────────────────────────────────────────┘
                        |
┌─────────────────────────────────────────────────────────────┐
│          ORCHESTRATION LAYER (quinta_feira.vbs)             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Validação   →  2. Chrome Find  →  3. Backend Start    │
│                                                             │
│  4. Sleep 3s    →  5. Chrome Launch                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                     |                    |
        ┌────────────┘                    └────────────┐
        |                                              |
┌───────────────────────┐      ┌─────────────────────────────┐
│   BACKEND LAYER       │      │   UI LAYER                  │
│  (Port 8080)          │      │  (Port 3000)                │
├───────────────────────┤      ├─────────────────────────────┤
│                       │      │                             │
│  FastAPI Uvicorn      │      │  Chrome App Mode            │
│  ├─ /ws endpoint      │◄────►├─ Next.js Frontend           │
│  ├─ Tool Registry     │      │  ├─ WebSocket Client       │
│  │  └─ Tool 1         │      │  ├─ Voice Input (WebAPI)   │
│  │  └─ Tool 2         │      │  └─ Audio Output           │
│  │  └─ Tool N         │      │                             │
│  ├─ Gemini 2.5 Flash  │      │  No browser chrome:         │
│  ├─ Triple Firewall   │      │  - No address bar          │
│  ├─ EventBus          │      │  - No tabs                 │
│  └─ DIContainer       │      │  - No menu                 │
│                       │      │  → App-like appearance     │
│                       │      │                             │
└───────────────────────┘      └─────────────────────────────┘
        |                                   |
        └───────────────┬───────────────────┘
                        |
┌─────────────────────────────────────────────────────────────┐
│          RUNTIME SECURITY & MEMORY LAYER                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Triple Firewall:                                           │
│  ├─ Layer 1: Backend validation (Base64 audio)             │
│  ├─ Layer 2: Isolation (WebSocket frame limits)            │
│  └─ Layer 3: Frontend detection (debounced updates)        │
│                                                             │
│  TerminalSecurityValidator:                                 │
│  ├─ CRÍTICO: Bloqueado (format C:, rm -rf, etc)            │
│  ├─ MÉDIO: Confirmação (del /s, install service)           │
│  └─ BAIXO: Logging (whoami, Get-Process)                   │
│                                                             │
│  Memory Management:                                         │
│  ├─ Backend: <150MB target                                  │
│  ├─ Frontend: <50MB target                                  │
│  └─ Chrome: Native                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 WORKFLOW: DO TRIGGER AO SYSTEM UP

```
╔════════════════════════════════════════════════════════════╗
║  TRIGGER                                                   ║
║  (PC boot || duplo clique || manual run)                   ║
╚════════════════════════════════════════════════════════════╝
                          ↓ (0-1s)
╔════════════════════════════════════════════════════════════╗
║  WIN: Execute fifth_feira.vbs                              ║
║  └─ VBScript engine (native Windows)                       ║
╚════════════════════════════════════════════════════════════╝
                          ↓ (50ms)
╔════════════════════════════════════════════════════════════╗
║  VALIDATE: File check                                      ║
║  └─ backend/start_hub.py exists? ✅ YES → Continue         ║
║                                ❌ NO → Error msgbox        ║
╚════════════════════════════════════════════════════════════╝
                          ↓ (200ms)
╔════════════════════════════════════════════════════════════╗
║  DETECT: Find Chrome                                       ║
║  └─ Loop 3 common paths + PATH variable                    ║
║  └─ Result: strChromePath = "chrome.exe" path              ║
╚════════════════════════════════════════════════════════════╝
                          ↓ (0-1s)
╔════════════════════════════════════════════════════════════╗
║  SPAWN: Backend (invisível)                                ║
║  └─ pythonw backend/start_hub.py --port 8080              ║
║  └─ Flags: 0 (hidden) + False (async/non-blocking)         ║
╚════════════════════════════════════════════════════════════╝
                          ↓ (3s)
╔════════════════════════════════════════════════════════════╗
║  WAIT: Uvicorm readiness                                   ║
║  └─ WScript.Sleep(3000) in milliseconds                    ║
║  └─ Ensures port 8080 is listening                         ║
╚════════════════════════════════════════════════════════════╝
                          ↓ (~1s)
╔════════════════════════════════════════════════════════════╗
║  LAUNCH: Chrome App Mode                                   ║
║  └─ chrome.exe --app=http://localhost:3000                 ║
║  └─ Flags: --profile-directory=Default                     ║
║  └─ Result: Window opens (no chrome UI)                    ║
╚════════════════════════════════════════════════════════════╝
                          ↓ (~500ms)
╔════════════════════════════════════════════════════════════╗
║  CONNECT: Frontend WebSocket                               ║
║  └─ Browser connects: ws://localhost:8080/ws               ║
║  └─ Backend accepts connection                             ║
╚════════════════════════════════════════════════════════════╝
                          ↓
╔════════════════════════════════════════════════════════════╗
║  ✅ READY FOR INTERACTION                                  ║
║                                                            ║
║  Total Time: ~4-5 seconds ⚡                              ║
║                                                            ║
║  Backend Status: 🟢 Online (port 8080)                     ║
║  Frontend Status: 🟢 Online (port 3000)                    ║
║  WebSocket Status: 🟢 Connected                            ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
```

---

## 📁 FILE DEPENDENCY TREE

```
INSTALLATION LAYER:
└─ setup_completo.ps1 (installs everything)
   ├─ Is Admin? Check
   ├─ .venv exists? Check
   ├─ pythonw exists? Check
   ├─ backend/start_hub.py exists? Check
   ├─ Copy quinta_feira.vbs → shell:startup
   │  └─ Result: Auto-boot enabled ✅
   └─ Copy quinta_feira.vbs → Desktop
      └─ Create .lnk shortcut
         └─ Result: Desktop access ✅

RUNTIME LAYER:
└─ quinta_feira.vbs (orchestrator)
   ├─ Validate: backend/start_hub.py
   ├─ Detect: chrome.exe (3 paths + PATH)
   ├─ Spawn: pythonw backend/start_hub.py
   │  └─ Dependencies:
   │     ├─ backend/core/tool_registry.py
   │     ├─ backend/tools/*.py
   │     ├─ backend/.env
   │     └─ backend/requirements.txt
   ├─ Sleep: 3000ms
   └─ Launch: chrome --app=http://localhost:3000
      └─ Dependencies:
         ├─ frontend/.env.local (NEXT_PUBLIC_WS_PORT=8080)
         ├─ frontend/app/page.tsx (line 126: wsPort || "8080")
         └─ frontend/app/layout.tsx (SSR safe)

DOCUMENTATION LAYER:
├─ COMECE_AQUI.md (entry point)
├─ AUTOSTART_COMPLETO_INSTRUCOES.md (user-friendly)
├─ SETUP_FINAL_CHECKLIST.md (complete reference)
├─ RESUMO_EXECUTIVO_SESSION.md (what was done)
└─ ARQUITETURA_VISUAL.md (this file)
```

---

## 🎯 CADA COMPONENTE: RAZÃO & IMPACTO

| Componente | Razão | Impacto |
|-----------|-------|--------|
| **VBScript** | Native Windows, sem deps | Universal, sempre funciona |
| **pythonw** | Invisível (sem console) | Produção-grade silencioso |
| **3s wait** | Uvicorm bind time | 100% conexão sucesso |
| **Chrome --app** | Native UI feel | Melhor UX (sem browser chrome) |
| **Path discovery** | Chrome instalação variável | Robustez em qualquer PC |
| **.env.local** | Next.js env vars | Frontend synced ao backend |
| **Fallback port** | Extra safety | Nunca tenta porta errada |
| **Startup folder** | Windows auto-run | Auto-boot no reboot |
| **Desktop .lnk** | Manual access | Fácil one-click |

---

## 🔐 SECURITY LAYERS

```
INPUT LAYER:
├─ Voice (Web Speech API)  →  Base64 encode
|                               ↓
|                         Triple Firewall Layer 1
|                         ├─ Size check (max 5MB)
|                         ├─ Format check (base64)
|                         └─ Content validation

PROCESSING LAYER:
├─ Command parsing      →  Gemini 2.5 Flash
|                          ↓
|                    Tool Registry
|                    ├─ Lookup command
|                    ├─ Validate params
|                    └─ Execute safely

EXECUTION LAYER:
├─ Terminal execution   →  TerminalSecurityValidator
|                          ├─ Regex 23 patterns
|                          ├─ CRÍTICO: Bloqueado
|                          ├─ MÉDIO: Confirmação
|                          └─ BAIXO: Logging

OUTPUT LAYER:
└─ Response to client   →  Triple Firewall Layer 3
                           ├─ Frame size limit
                           ├─ Debounce updates
                           └─ Rate limiting
```

---

**VERSÃO**: v2.0 Auto-Start Complete
**ESTADO**: Production Ready ✅
**TEMPO**: 4-5 segundos boot-to-ready
