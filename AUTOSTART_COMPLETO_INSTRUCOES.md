# 🚀 QUINTA-FEIRA AUTO-START COMPLETO - INSTRUÇÃO RÁPIDA

## ✨ O Que É Isto?

Um ficheiro **quinta_feira.vbs** que faz **TUDO automaticamente** quando liges o PC:

```
PC Liga
  ↓ (1 segundo)
Backend inicia (silenciosamente)
  ↓ (3 segundos de espera)
Chrome abre mostrando o app (interface bonita)
  ↓
✅ PRONTO! Interface já visível, sem fazer nada
```

---

## ⚡ INSTALAR (2 Passos)

### **PASSO 1: Abrir Startup**
- Pressionar: **Win + R**
- Digitar: `shell:startup`
- Pressionar: **Enter**

(Uma pasta deve abrir-se)

---

### **PASSO 2: Copiar Ficheiro**

**Na pasta que abriu:**
1. Copiar ficheiro: `quinta_feira.vbs` 
   - Localização: `C:\Users\mathe\Documents\assistente-ai\quinta_feira.vbs`

2. Colar na pasta Startup (Win+R → shell:startup)

3. **Pronto!** 🎉

---

## 🧪 TESTAR ANTES

(Opcional, mas recomendado)

**Duplo clique em `quinta_feira.vbs` (em qualquer lugar)**

Esperado:
- Backend inicia sem mostrar janela
- Chrome abre com a interface (sem barra de endereços)
- Tudo funciona? ✅

---

## 🎯 DEPOIS DE INSTALAR

### **Próxima Vez que Ligares o PC:**

1. Windows inicia
2. Automaticamente:
   - Backend começa a rodar (porta 8080)
   - Chrome abre mostrando interface
3. Tu podes começar a usar imediatamente ✅

---

## 🔧 CUSTOMIZAÇÃO (Se Usares Vercel)

Se estiveres a usar frontend em Vercel (não localhost):

**Editar `quinta_feira.vbs`:**

Encontrar a linha (perto do fim):
```vbs
strChromeCmd = """" & strChromePath & """ --app=http://localhost:3000 --profile-directory=Default"
```

Trocar `http://localhost:3000` por:
```vbs
strChromeCmd = """" & strChromePath & """ --app=https://seu-app.vercel.app --profile-directory=Default"
```

(Substitui `seu-app.vercel.app` pelo teu domínio Vercel)

---

## 📋 O que o Script Faz

| Ação | Tempo |
|------|-------|
| Inicia backend (pythonw) | Imediato |
| Aguarda servidor estar pronto | 3 segundos |
| Abre Chrome em modo app | +1 segundo |
| **Total** | **~4 segundos** ⚡ |

---

## ✅ Checklist

- [ ] Ficheiro `quinta_feira.vbs` existe em `C:\Users\mathe\Documents\assistente-ai\`
- [ ] Win+R → `shell:startup` abriu pasta
- [ ] Copiei `quinta_feira.vbs` para Startup
- [ ] Testei (duplo clique) e funcionou
- [ ] Reiniciei PC e tudo funcionou automaticamente

---

## 🆘 Se Não Funcionar

### Chrome não abre?
- Verificar se Chrome está instalado
- Ou abrir manualmente: `http://localhost:3000`

### Backend não inicia?
- Verificar se `.venv` foi criado
- Terminal: `python -m venv .venv`

### Nada acontece ao duplo clique?
- Possível permissões. Clic direito → "Executar como Administrador"

---

## 💡 Dicas

**Para PARAR o backend:**
```
taskkill /F /IM python.exe
```

**Para VER os logs do backend:**
```
python backend/start_hub.py --port 8080
(em vez de pythonw)
```

**Para REMOVER do auto-start:**
- Win+R → `shell:startup`
- Apagar `quinta_feira.vbs`

---

## 🎉 Resultado Final

**Sem instalar:**
- Tens que fazer tudo manualmente
- Terminal 1: Backend
- Terminal 2: Frontend
- Browser: localhost:3000
- 🤦 Chato!

**Com instalar:**
- PC liga
- Tudo inicia sozinho
- Chrome abre automaticamente
- 🚀 Perfeito!

---

**Pronto? Instala agora!** 🚀
