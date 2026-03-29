# ⚡ INÍCIO RÁPIDO - Setup Porta 8080 em 3 Passos

## 🎯 Missão: Mover Backend para 8080 + Auto-Start

**Status**: ✅ COMPLETO (Pronto para instalar)

---

## 3️⃣ PASSOS FINAIS (Para Você)

### PASSO 1: Instalar (30 seg)

```powershell
# Abrir PowerShell como ADMINISTRADOR
# (Win+X, depois A)

# Colar este comando:
$dst = "C:\Users\mathe\Documents\assistente-ai"; 
cd $dst; 
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force; 
.\instalar_silencioso.ps1
```

**Isto faz**: Copia `quinta_feira_silenciosa.vbs` para Windows Startup

---

### PASSO 2: Testar Manual (1 min)

```powershell
# Ainda em PowerShell (sem sair)

cd "C:\Users\mathe\Documents\assistente-ai"
& ".\quinta_feira_silenciosa.vbs"

# Esperar 3 segundos
# Depois abrir novo PowerShell e verificar:
netstat -ano | findstr :8080

# Esperado: TCP    127.0.0.1:8080         LISTENING
```

**Se vir LISTENING**: ✅ Script funciona!

---

### PASSO 3: Testar Frontend (2 min)

```bash
# Terminal novo (pode fechar o PowerShell anterior)

cd "C:\Users\mathe\Documents\assistente-ai\frontend"

npm run dev

# Abrir http://localhost:3000
# F12 → Console
# Procurar: "[WS] Port=8080" ou "Online"

# Se vir "Online": ✅ Frontend conectou!
```

---

## ✅ Pronto?

Se os 3 testes passaram:

```
1. ✓ Instalar executado
2. ✓ Porta 8080 aberta (netstat)
3. ✓ Frontend conectou (console)

Então: PRÓXIMA AÇÃO = Reiniciar PC
```

---

## 🔄 Após Reiniciar

```
1. Ligar PC
2. Aguardar 10 segundos
3. Abrir: netstat -ano | findstr :8080
4. Se ver LISTENING → Auto-start funciona! ✅
5. Abrir http://localhost:3000
6. Deve conectar automaticamente
```

---

## 📁 Arquivos Que Foram Criados

```
✓ quinta_feira_silenciosa.vbs       (Script invisível)
✓ frontend/.env.local              (Vars de porta)
✓ instalar_silencioso.ps1          (Automático)
✓ SETUP_SCRIPT_SILENCIOSO.md       (Instruções longas)
✓ INFRAESTRUTURA_PORTO_8080_COMPLETO.md (Completo)

Todos na raiz: C:\Users\mathe\Documents\assistente-ai\
```

---

## 🆘 Se Algo Falhar

### Erro: "ExecutionPolicy"
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
```

### Erro: "Porta 8080 em uso"
```bash
netstat -ano | findstr :8080
# Ver qual PID está usando
taskkill /F /PID <PID>
```

### Erro: "pythonw não encontrado"
```bash
python -c "import sys; print(sys.executable)"
# Verificar se está em .venv
```

### Erro: "VBS não copia para Startup"
```bash
# Fazer manualmente:
copy "C:\Users\mathe\Documents\assistente-ai\quinta_feira_silenciosa.vbs" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\"
```

---

## 📞 Mais Informações?

- **Instruções longas**: Ler `SETUP_SCRIPT_SILENCIOSO.md`
- **Arquitetura completa**: Ler `INFRAESTRUTURA_PORTO_8080_COMPLETO.md`
- **Debug**: Rodar `python backend/start_hub.py --port 8080` em terminal normal (não VBS)

---

**Pronto para começar?** 🚀

Executar:
```powershell
.\instalar_silencioso.ps1
```

Bonne chance! 🎉
