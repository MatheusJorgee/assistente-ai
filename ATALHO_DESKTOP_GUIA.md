# 🖱️ ATALHO NA DESKTOP - Guia Rápido

## ✨ O Que Acabou de Ser Criado

**3 Scripts PowerShell para diferentes necessidades:**

### 1. **instalar_silencioso.ps1** 
   - Copia VBS para Startup (auto-start ao boot)
   - Modo: Mínimo (só Startup)

### 2. **criar_atalho_desktop.ps1** 
   - Cria atalho na Desktop (execução manual)
   - Modo: Só Desktop

### 3. **setup_completo.ps1** ⭐ RECOMENDADO
   - Instala no Startup + Cria atalho Desktop
   - Modo: Tudo em um!

---

## 🚀 Usar (Escolher uma opção)

### **OPÇÃO A: Tudo em Uma Vez** (⭐ Recomendado)

```powershell
# PowerShell como ADMIN (Win+X → A)
cd "C:\Users\mathe\Documents\assistente-ai"
.\setup_completo.ps1
```

**Isto faz**:
1. ✓ Instala VBS no Startup (auto-start)
2. ✓ Cria atalho na Desktop (execução manual)
3. ✓ Pronto! Duplo clique para iniciar

**Tempo**: 30 segundos ⏱️

---

### **OPÇÃO B: Só Startup** (sem Desktop)

```powershell
.\instalar_silencioso.ps1
```

---

### **OPÇÃO C: Só Desktop** (sem Startup)

```powershell
.\criar_atalho_desktop.ps1
```

---

## 📌 Atalho na Desktop - Como Usar

Depois de executar qualquer um dos scripts:

### **Duplo Clique em "Quinta-Feira.lnk"**
   - Backend inicia na porta 8080
   - Sem janela de console visível
   - Silenciosamente em background

### **Verificar se está rodando**
```powershell
netstat -ano | findstr :8080
# Deve mostrar: TCP    127.0.0.1:8080    LISTENING
```

### **Abrir Frontend**
```
http://localhost:3000
```

---

## 🎯 Depois da Instalação

### **Teste 1: Desktop (Agora)**
1. Desktop: Duplo clique em `Quinta-Feira.lnk`
2. Terminal: `netstat -ano | findstr :8080`
3. Esperado: LISTENING ✅

### **Teste 2: Frontend**
```bash
npm run dev  # em novo terminal
# Abrir http://localhost:3000
# F12 → Console → Procurar "Port=8080"
```

### **Teste 3: Auto-Start**
1. Reiniciar PC
2. Aguardar 10 segundos
3. `netstat -ano | findstr :8080`
4. Se LISTENING → Auto-start funciona ✅

---

## 📋 Ficheiros Criados

| Ficheiro | Função |
|----------|--------|
| `quinta_feira_silenciosa.vbs` | Script invisível (pythonw) |
| `Quinta-Feira.lnk` | Atalho na Desktop ⭐ |
| `setup_completo.ps1` | Instalar tudo de uma vez |
| `instalar_silencioso.ps1` | Só Startup |
| `criar_atalho_desktop.ps1` | Só Desktop |

---

## 🎓 Diferenças

| Método | Auto-Start | Atalho Desktop | Manual |
|--------|-----------|-----------------|--------|
| **Startup só** | ✓ Sim | ✗ Não | Não |
| **Desktop só** | ✗ Não | ✓ Sim | Duplo clique |
| **Completo** ⭐ | ✓ Sim | ✓ Sim | Duplo clique |

---

## ⚡ Começar Agora

```powershell
# Como Admin
cd "C:\Users\mathe\Documents\assistente-ai"
.\setup_completo.ps1
```

Depois: **Desktop** → Duplo clique em `Quinta-Feira.lnk`

✅ Pronto!

---

## 🆘 Troubleshooting

### Atalho não funciona
```powershell
# Verificar se VBS existe
Test-Path "C:\Users\mathe\Documents\assistente-ai\quinta_feira_silenciosa.vbs"

# Testar VBS direto
& "C:\Users\mathe\Documents\assistente-ai\quinta_feira_silenciosa.vbs"
```

### Porta 8080 não abre
```powershell
# Matar processos antigos
taskkill /F /IM python.exe
taskkill /F /IM pythonw.exe

# Tentar de novo
# Desktop → Duplo clique no atalho
```

---

**Pronto para começar!** 🎉
