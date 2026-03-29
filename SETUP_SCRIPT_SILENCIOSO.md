# 🚀 Setup Script Silencioso - Instruções

## ✅ O Que Foi Criado

### 1. **quinta_feira_silenciosa.vbs** (Script Invisível)
- 📁 Localização: `C:\Users\mathe\Documents\assistente-ai\quinta_feira_silenciosa.vbs`
- 🎯 Função: Iniciar backend na porta **8080** sem abrir janela preta
- ⚙️ Comando: `pythonw backend/start_hub.py --port 8080`
- 🔕 Modo: Totalmente silencioso (sem console visível)

### 2. **frontend/.env.local** (Variáveis de Porta)
- `NEXT_PUBLIC_WS_PORT=8080` ✓
- `NEXT_PUBLIC_WS_HOST=localhost` ✓
- Fallback em page.tsx: 8080 ✓

### 3. **Auditoria Frontend**
- ✓ page.tsx: Fallback porta mudado de 8000 → 8080 (linha 126)
- ✓ route.ts: Sem hardcodes de porta encontrados
- ✓ Lê env vars corretamente

---

## 🎯 Próximos Passos (2 Opções)

### **Opção 1: Automático (PowerShell)**

```powershell
# Executar como Administrador:
# 1. Abrir PowerShell como Admin (Win+X, depois A)
# 2. Colar este comando:

$vbsPath = "C:\Users\mathe\Documents\assistente-ai\quinta_feira_silenciosa.vbs"
$startupPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
Copy-Item $vbsPath $startupPath -Force
Write-Host "✓ Script copiado para Startup!" -ForegroundColor Green
```

**Resultado**: Quinta-Feira inicia automaticamente ao ligares o PC

---

### **Opção 2: Manual (Explorer)**

```
1. Abrir File Explorer (Win+E)
2. Navegar para:
   C:\Users\mathe\Documents\assistente-ai
   
3. Encontrar: quinta_feira_silenciosa.vbs

4. Copiar (Ctrl+C)

5. Colar em:
   C:\Users\mathe\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
   
6. Pronto! Script executará ao boot
```

---

## 🧪 Testar Script Antes de Startup

```bash
# Terminal PowerShell (sem admin)
cd C:\Users\mathe\Documents\assistente-ai
& ".\quinta_feira_silenciosa.vbs"

# Esperar 3 segundos e verificar:
# - Backend deve estar rodando na porta 8080
# - Nenhuma janela visível (script é silencioso)

# Confirmar:
netstat -ano | findstr :8080
# Deve mostrar conexão LISTENING em 8080
```

---

## 📋 Checklist Final

- [ ] VBS criado em `C:\Users\mathe\Documents\assistente-ai\`
- [ ] `.env.local` criado com `NEXT_PUBLIC_WS_PORT=8080`
- [ ] page.tsx fallback mudado para 8080
- [ ] Script testado (netstat mostra porta 8080)
- [ ] Script copiado para Startup (automático ou manual)
- [ ] PC reiniciado para confirmar auto-start
- [ ] Frontend conecta em `ws://localhost:8080/ws` ✅

---

## 🔧 Troubleshooting

### Problema: "VBS não executa"
```
Solução: 
1. Verificar se pythonw está em PATH
2. Abrir PowerShell como Admin
3. Executar: python -c "import sys; print(sys.executable)"
4. Confirmar que é a versão .venv
```

### Problema: "Porta 8080 ainda em conflito"
```
Solução:
1. Encontrar processo em porta 8080:
   netstat -ano | findstr :8080
   
2. Matar processo (substitui PID):
   taskkill /PID <PID> /F
   
3. Tentar novamente
```

### Problema: "Script não inicia ao boot"
```
Solução:
1. Verificar se script está em:
   C:\Users\mathe\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
   
2. Testar manualmente primeiro:
   & "C:\Users\mathe\Documents\assistente-ai\quinta_feira_silenciosa.vbs"
   
3. Se funcionar manualmente, reiniciar PC
```

---

## 🎯 Próximas Integrações

Depois do VBS estar no Startup, o sistema funcionará assim:

```
⚡ PC Liga
  ↓
 🟢 VBS executa silenciosamente (primeira ação)
  ↓
 🟢 Backend inicia na porta 8080
  ↓
 🟢 Frontend detecta ENV NEXT_PUBLIC_WS_PORT=8080
  ↓
 🟢 WebSocket conecta em ws://localhost:8080/ws
  ↓
 ✅ Quinta-Feira pronta para comandos
```

---

## 📞 Verificar Status

```bash
# Check porta 8080
netstat -ano | findstr :8080

# Check processo Python
tasklist | findstr python

# Check env var no frontend
npm run dev  # Verificar console para "[WS] Port=8080"
```

---

**Sistema migrado para porta 8080 com sucesso! 🚀**
