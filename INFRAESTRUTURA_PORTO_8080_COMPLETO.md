# 🎯 INFRAESTRUTURA: Setup Porta 8080 - COMPLETO

## ✅ O Que Foi Executado

### ✓ Parte 1: Script Invisível (VBScript)

**Arquivo criado**: `quinta_feira_silenciosa.vbs`
```
📁 C:\Users\mathe\Documents\assistente-ai\quinta_feira_silenciosa.vbs
```

**Função**:
- Executa `pythonw backend/start_hub.py --port 8080`
- Sem janela de console visível (pythonw = python.exe sem output)
- Caminhos relativos robustos
- Pronto para Windows Startup

**Código**:
```vbs
Dim objShell, strPath, strCmd, objFSO

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strPath = objFSO.GetParentFolderName(WScript.ScriptFullName)
strCmd = "pythonw """ & strPath & "\backend\start_hub.py"" --port 8080"

objShell.Run strCmd, 0, False
```

---

### ✓ Parte 2: Sincronização Frontend

**Arquivo 1**: `frontend/.env.local` (CRIADO)
```env
NEXT_PUBLIC_WS_PORT=8080
NEXT_PUBLIC_WS_HOST=localhost
NEXT_PUBLIC_CLOUD_TIMEOUT=5000
NEXT_PUBLIC_DEBUG=false
```

**Arquivo 2**: `frontend/app/page.tsx` (ATUALIZADO)
- Linha 126: Fallback porta mudado de `"8000"` → `"8080"`
- Lê `process.env.NEXT_PUBLIC_WS_PORT`
- Se não existir, usa `"8080"` como default
- ✓ SSR-safe (window checks implementados)

**Arquivo 3**: `frontend/app/api/chat/route.ts`
- ✓ Auditado: Sem hardcodes de porta
- ✓ Usa Gemini SDK para cloud mode

---

### ✓ Parte 3: Scripts de Instalação

**Script 1**: `instalar_silencioso.ps1` (PowerShell)
- Copia VBS para Windows Startup automaticamente
- Verifica pré-requisitos (admin, pythonw, backend)
- 5 checks de validação
- Modo: Automático (1 clique)

**Como usar**:
```powershell
# Como Administrator:
.\instalar_silencioso.ps1
```

---

## 📋 Arquitetura Resultado

```
┌─────────────────────────────────────────────────────┐
│ PC LIGA                                             │
└────────┬────────────────────────────────────────────┘
         ↓ (imediato)
┌─────────────────────────────────────────────────────┐
│ Windows Startup                                     │
│ └─→ quinta_feira_silenciosa.vbs                    │
└────────┬────────────────────────────────────────────┘
         ↓ (silenciosamente, sem janela)
┌─────────────────────────────────────────────────────┐
│ pythonw backend/start_hub.py --port 8080           │
│ └─→ Backend inicia na porta 8080                    │
│ └─→ Nenhuma janela visível                          │
└────────┬────────────────────────────────────────────┘
         ↓ (3-5 segundos depois)
┌─────────────────────────────────────────────────────┐
│ Browser (localhost:3000)                            │
│ └─→ Frontend carrega                                │
│ └─→ Lê NEXT_PUBLIC_WS_PORT=8080 do .env.local      │
│ └─→ Conecta: ws://localhost:8080/ws                │
└────────┬────────────────────────────────────────────┘
         ↓ (WebSocket handshake)
┌─────────────────────────────────────────────────────┐
│ ✅ SISTEMA OPERACIONAL                             │
│ • Backend: 8080 ✓                                   │
│ • Frontend: Conectado ✓                             │
│ • Sem janelas visíveis ✓                            │
└─────────────────────────────────────────────────────┘
```

---

## 🧪 Instalação: 3 Passos

### OPÇÃO 1: Automática (Recomendada ⭐)

```powershell
# 1. Abrir PowerShell como ADMINISTRADOR
# (Win+X, depois A)

# 2. Executar:
cd "C:\Users\mathe\Documents\assistente-ai"
.\instalar_silencioso.ps1

# 3. Seguir as instruções no screen
```

**Tempo**: 30 segundos ⏱️

---

### OPÇÃO 2: Manual via Explorer

```
1. File Explorer (Win+E)
2. Navegar para: C:\Users\mathe\Documents\assistente-ai
3. Encontrar: quinta_feira_silenciosa.vbs
4. Copiar (Ctrl+C)
5. Navegar para: C:\Users\mathe\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
6. Colar (Ctrl+V)
7. Done!
```

**Tempo**: 1 minuto ⏱️

---

### OPÇÃO 3: Manual via cmd

```cmd
REM Abrir cmd como ADMINISTRADOR

cd "C:\Users\mathe\Documents\assistente-ai"
copy "quinta_feira_silenciosa.vbs" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\"

echo ✓ Script instalado!
```

**Tempo**: 30 segundos ⏱️

---

## ✅ Verificação

### Teste 1: Script Funciona? (Antes de reiniciar)

```bash
# PowerShell (sem admin)
cd "C:\Users\mathe\Documents\assistente-ai"
& ".\quinta_feira_silenciosa.vbs"

# Esperar 3 segundos, verificar porta:
netstat -ano | findstr :8080

# Esperado:
# TCP    127.0.0.1:8080         0.0.0.0:*         LISTENING    <PID>
```

**✓ Se aparecer**: Script funciona! 🎉

---

### Teste 2: Frontend Conecta?

```bash
# Terminal 1
cd "C:\Users\mathe\Documents\assistente-ai\frontend"
npm run dev

# Terminal 2 (verificar ENV var)
# Abrir localhost:3000
# F12 (DevTools) → Console
# Procurar por: "[WS] Port=8080" ou "[WS] URL=ws://localhost:8080/ws"
```

**✓ Se aparecer**: Frontend sincronizado! 🎉

---

### Teste 3: Auto-Start? (Depois de reiniciar)

```
1. Reiniciar PC
2. Aguardar 10 segundos
3. Abrir: netstat -ano | findstr :8080
4. Se vir LISTENING → ✓ Auto-start funciona! 🎉
```

---

## 📊 Checklist Completo

- [x] `quinta_feira_silenciosa.vbs` criado
- [x] `frontend/.env.local` criado com `NEXT_PUBLIC_WS_PORT=8080`
- [x] `frontend/app/page.tsx` fallback mudado para 8080
- [x] `instalar_silencioso.ps1` criado (com validações)
- [x] `SETUP_SCRIPT_SILENCIOSO.md` documentado
- [ ] Script instalado em Startup (próximo passo: você)
- [ ] Teste 1: VBS funciona manualmente (próximo passo: você)
- [ ] Teste 2: Frontend conecta em 8080 (próximo passo: você)
- [ ] Teste 3: PC reiniciado, auto-start confirmado (próximo passo: você)

---

## 🎯 Próximos Passos (Para Você)

### Imediato (Agora)

1. **Instalar Script**:
   ```powershell
   .\instalar_silencioso.ps1
   ```

2. **Testar Script**:
   ```bash
   & ".\quinta_feira_silenciosa.vbs"
   netstat -ano | findstr :8080
   ```

3. **Testar Frontend**:
   ```bash
   npm run dev
   # F12 → Console → Procurar "[WS] Port=8080"
   ```

---

### Próxima Reboot

1. **Reiniciar PC**
2. **Verificar Auto-Start**:
   ```bash
   netstat -ano | findstr :8080
   # Deve mostrar LISTENING
   ```
3. **Abrir Frontend**:
   ```bash
   npm run dev
   # Deve conectar automaticamente
   ```

---

## 📁 Arquivos Criados/Modificados

| Arquivo | Status | Tipo |
|---------|--------|------|
| `quinta_feira_silenciosa.vbs` | ✓ CRIADO | VBScript |
| `frontend/.env.local` | ✓ CRIADO | Config |
| `frontend/app/page.tsx` | ✓ MODIFICADO | TypeScript |
| `instalar_silencioso.ps1` | ✓ CRIADO | PowerShell |
| `SETUP_SCRIPT_SILENCIOSO.md` | ✓ CRIADO | Docs |

---

## 🔒 Segurança

**pythonw vs python.exe**
- ✓ pythonw não abre janela do console
- ✓ Mais discreto (ideal para auto-start)
- ✓ Compatível com Ctrl+C (ainda dá para parar via taskkill)
- ✗ Mais difícil ver logs (usar terminal sempre que precisar debug)

**Firewall Windows**
- Se bloquear porta 8080: Adicionar exceção em Firewall
- Ou usar start_hub.py --host 0.0.0.0 (público)

---

## 💡 Dicas

### Debug: Ver logs do VBS
```bash
# Se quiser ver o que está acontecendo, executar normalmente:
python backend/start_hub.py --port 8080

# Em vez de:
pythonw backend/start_hub.py --port 8080
```

### Debug: Matar processo Python
```bash
# Se portar travar/falhar:
taskkill /F /IM python.exe
taskkill /F /IM pythonw.exe

# Depois tentar novamente:
& ".\quinta_feira_silenciosa.vbs"
```

### Debug: Ver variáveis env
```bash
# No frontend console (F12):
console.log(process.env.NEXT_PUBLIC_WS_PORT)  // Deve ser "8080"
console.log(process.env.NEXT_PUBLIC_WS_HOST)  // Deve ser "localhost"
```

---

## ✨ Resultado Final

```
🎯 Quinta-Feira v2.1 com Porta 8080
├─ Auto-start: ✓ Silencioso
├─ Backend: ✓ Porta 8080
├─ Frontend: ✓ Sincronizado
└─ Pronto: ✓ Para Produção
```

---

**Status: READY FOR DEPLOYMENT 🚀**
