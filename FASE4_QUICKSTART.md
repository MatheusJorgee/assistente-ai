# 🚀 FASE 4 - QUICKSTART (5 MINUTOS)

## 1️⃣ VALIDAÇÃO (30s)

Verifique se tudo está OK:

```bash
python validar_fase4.py
```

Deve mostrar **✅ todos verdes**.

---

## 2️⃣ INSTALAR DEPENDÊNCIAS (2min)

### Backend

```bash
cd backend
pip install pyngrok>=5.2.0
pip install uvicorn>=0.27.0
pip install python-dotenv
```

### Frontend

```bash
cd frontend
npm install
npm install @google/generative-ai
```

---

## 3️⃣ CONFIGURAR (1min)

### Backend - .env

```bash
# Já deve estar configurado, verificar:
cd backend
echo $GEMINI_API_KEY  # Deve ter valor
```

Se não houver:
```bash
# Windows PowerShell
$env:GEMINI_API_KEY = "sua_chave_aqui"

# Linux/Mac
export GEMINI_API_KEY="sua_chave_aqui"
```

### Frontend - .env.local

```bash
cd frontend

# Copiar template
cp .env.local.example .env.local

# Editar para seu cenário:
# Opção 1: LOCAL (PC mesmo que celular)
NEXT_PUBLIC_WS_HOST=127.0.0.1
NEXT_PUBLIC_WS_PORT=8000

# Opção 2: REDE (PC em outro IP local)
NEXT_PUBLIC_WS_HOST=192.168.1.100
NEXT_PUBLIC_WS_PORT=8000

# Opção 3: NGROK (acesso de qualquer lugar)
NEXT_PUBLIC_WS_HOST=abc123.ngrok-free.app
NEXT_PUBLIC_WS_PORT=443

# Opção 4: Modo Nuvem (sem PC)
# Deixar os defaults, apenas garantir:
NEXT_GEMINI_API_KEY=sua_chave_aqui
```

---

## 4️⃣ EXECUTAR (1min)

### Terminal 1 - Backend

```bash
cd backend
python start_hub.py --public
```

Saída esperada:
```
[INFO] Iniciando Quinta-Feira Hub...
[NGROK] ✓ Túnel estabelecido: https://abc123.ngrok-free.app
📝 CONFIGURAR FRONTEND (.env.local):
   NEXT_PUBLIC_WS_HOST=abc123.ngrok-free.app
   NEXT_PUBLIC_WS_PORT=443
```

**Copiar o URL** → guardar para o .env.local

### Terminal 2 - Frontend

```bash
cd frontend
npm run dev
```

Saída esperada:
```
▲ Next.js 15.0.0
- Local:        http://localhost:3000
- Network:      http://192.168.1.100:3000
```

---

## 5️⃣ TESTAR

### Teste 1: Local (PC e celular na mesma rede)

1. Abrir navegador no **celular**
2. Ir para: `http://192.168.1.X:3000` (seu IP local)
3. Enviar mensagem
4. Deve responder ✅

**Status na UI**: "CANAL ONLINE" (verde)

### Teste 2: WiFi diferente (Ngrok)

1. Ter Internet (Ngrok)
2. Ser capaz de executar: `python start_hub.py --public --ngrok-token SEU_TOKEN`
3. Copiar URL pública
4. Editar `frontend/.env.local`:
   ```
   NEXT_PUBLIC_WS_HOST=abc123.ngrok-free.app
   NEXT_PUBLIC_WS_PORT=443
   ```
5. Recarregar: `npm run dev`
6. Acessar: `https://abc123.ngrok-free.app`
7. Enviar mensagem → Deve responder ✅

**Status na UI**: "CANAL ONLINE" (verde)

### Teste 3: PC Offline (Cloud Fallback)

1. Backend rodando em Terminal 1 ✅
2. Frontend conectado ✅
3. **Desligar o PC** (ou Ctrl+C no Terminal 1)
4. Esperar 5 segundos
5. Enviar mensagem no frontend
6. Deve responder via **Gemini serverless** ✅

**Status na UI**: "🌐 MODO NUVEM" (laranja)

⚠️ **IMPORTANTE**: Modo nuvem NÃO tem acesso a:
- ❌ Spotify
- ❌ YouTube  
- ❌ Terminal
- ❌ Automação

Mas FUNCIONA para chat normal.

---

## 6️⃣ TROUBLESHOOTING RÁPIDO

### ❌ "Port already in use"

```bash
# Matar processo na porta 8000
# Windows
taskkill /PID $(netstat -ano | findstr :8000 | awk '{print $5}') /F

# Linux/Mac
lsof -ti:8000 | xargs kill -9
```

### ❌ "NGROK não funciona"

```bash
# 1. Verificar token
echo $NGROK_AUTH_TOKEN

# 2. Ou passar direto:
python start_hub.py --public --ngrok-token seu_token_aqui
```

### ❌ "Frontend não conecta ao backend"

1. Verificar `.env.local`:
   ```bash
   cat frontend/.env.local
   ```
2. Confirmar valores:
   - `NEXT_PUBLIC_WS_HOST` = seu IP/domain
   - `NEXT_PUBLIC_WS_PORT` = 8000 (local) ou 443 (ngrok)
   - `NEXT_PUBLIC_WS_PATH` = /ws
3. Recarregar página (Ctrl+Shift+R hard refresh)

### ❌ "Modo nuvem não responde"

1. Verificar `GEMINI_API_KEY` e/ou `NEXT_GEMINI_API_KEY`
2. Confirmar na `.env.local`:
   ```bash
   cat frontend/.env.local | grep GEMINI
   ```
3. Se vazio, adicionar:
   ```bash
   NEXT_GEMINI_API_KEY=sua_chave_aqui
   ```

---

## 📊 VERIFICAÇÃO FINAL

```bash
# Ver se tudo está rodando:

# Terminal 1 (Backend)
python start_hub.py --public
# Deve mostrar ✓ Ngrok, ✓ Uvicorn running

# Terminal 2 (Frontend)  
npm run dev
# Deve mostrar ✓ Local e ✓ Network running

# Terminal 3 (Teste)
curl http://localhost:8000/health  # Must return 200
curl http://localhost:3000         # Must return 200
```

---

## ✅ SUCCESS CHECKLIST

- [ ] `validar_fase4.py` mostra todos verdes
- [ ] Backend conecta com Ngrok túnel
- [ ] Frontend consegue carregar (localhost:3000)
- [ ] Consegue enviar mensagem no celular
- [ ] Status mostra "CANAL ONLINE"
- [ ] Desligar PC → esperar 5s → modo nuvem ativa
- [ ] Status muda para "🌐 MODO NUVEM"
- [ ] Mesmo offline, consegue responder

---

## 🎉 DONE!

Sua Quinta-Feira agora é:
- ✅ **Global**: Acesso de qualquer WiFi
- ✅ **Resiliente**: Funciona mesmo offline
- ✅ **Transparente**: Usuário não vê a mudança
- ✅ **Inteligente**: Automático PC online/offline

**Próximos passos**:
1. Testar em produção
2. Ler [FASE4_HUB_DISTRIBUIDO_GUIA.md](FASE4_HUB_DISTRIBUIDO_GUIA.md) para cenários avançados
3. Configurar domain customizado (opcional)
4. Setup em servidor cloud permanente (opcional)

---

**Dúvidas?** → Ver `FASE4_HUB_DISTRIBUIDO_GUIA.md` seção Debugging
