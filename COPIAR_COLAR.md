# 🎯 COPIA E COLA - Comandos Prontos

## ⚡ Mais Rápido Possível (Copiar/Colar)

### 1️⃣ INSTALAR (Copiar isto tudo para PowerShell Admin)

```powershell
cd "C:\Users\mathe\Documents\assistente-ai"; .\instalar_silencioso.ps1
```

![Passo 1: Abrir PowerShell Admin (Win+X, depois A)]

---

### 2️⃣ TESTAR SCRIPT (Num novo PowerShell)

```powershell
cd "C:\Users\mathe\Documents\assistente-ai"
& ".\quinta_feira_silenciosa.vbs"
Start-Sleep -Seconds 3
netstat -ano | findstr :8080
```

**Esperado**: `TCP    127.0.0.1:8080    0.0.0.0:*    LISTENING`

---

### 3️⃣ TESTAR FRONTEND (Num novo CMD/PowerShell)

```bash
cd "C:\Users\mathe\Documents\assistente-ai\frontend"
npm run dev
```

Abrir `http://localhost:3000` e F12 → Console → Procurar `Port=8080`

---

## 📋 Ordem Exata

| # | Ação | Tempo |
|---|------|-------|
| 1 | Abrir PowerShell Admin | 5 seg |
| 2 | Paste `cd "C:\...\instalar_silencioso.ps1"` | 10 seg |
| 3 | Aguardar completion | 15 seg |
| 4 | Abrir novo PowerShell | 5 seg |
| 5 | Paste `cd "C:\..." && & ".\quinta_feira_silenciosa.vbs"` | 10 seg |
| 6 | Paste `netstat -ano \| findstr :8080` | 5 seg |
| 7 | Verificar LISTENING | 10 seg |
| 8 | Abrir novo CMD | 5 seg |
| 9 | Paste `cd "...\frontend" && npm run dev` | 10 seg |
| 10 | Abrir `localhost:3000` | 5 seg |
| **TOTAL** | **Tudo pronto!** | **80 seg** 🚀 |

---

## 🔍 Se Algo Estiver Errado

### Erro: "ExecutionPolicy"
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
```

### Erro: "Porta em uso"
```powershell
netstat -ano | findstr :8080
taskkill /F /PID <aquele PID>
```

### Erro: "pythonw not found"
```powershell
python -c "import sys; print(sys.executable)"
# Se não terminar em .venv\Scripts\python.exe, reinstalar venv
```

---

## ✅ Checklist

- [ ] PowerShell Admin aberto
- [ ] `instalar_silencioso.ps1` executado
- [ ] VBS testado (netstat mostra 8080)
- [ ] Frontend conecta (console mostra Port=8080)
- [ ] Pronto para reiniciar PC

---

## 🎉 Depois de Tudo

Reiniciar PC e:
```powershell
netstat -ano | findstr :8080
# Se vir LISTENING → Auto-start funciona! ✅
```

Abrir `http://localhost:3000` e deve conectar automaticamente!

---

**Boa sorte! 🚀**
