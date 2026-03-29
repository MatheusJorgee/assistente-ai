# 🚀 FASE 4 - Hub Distribuído, Ngrok e Fallback de Nuvem

## Objetivo
Permitir acesso ao Quinta-Feira de qualquer lugar do mundo via celular, com fallback automático para Modo Nuvem quando o PC está offline.

---

## 📋 Checklist de Implementação

### ✅ IMPLEMENTAÇÕES JÁ FEITAS

1. **Backend (start_hub.py)**
   - ✅ Script inicializa Uvicorn programaticamente
   - ✅ Configura túnel Ngrok automaticamente
   - ✅ Imprime URL pública para acesso remoto
   - ✅ Tratamento gracioso de Ctrl+C

2. **Frontend (page.tsx)**
   - ✅ Usa `NEXT_PUBLIC_WS_HOST` em vez de hardcode
   - ✅ Converte `https://` automaticamente para `wss://`
   - ✅ Detecção de PC offline (timeout 5s)
   - ✅ Ativa Modo Nuvem automaticamente
   - ✅ UI atualizada com indicadores de status

3. **Cloud Fallback (app/api/chat/route.ts)**
   - ✅ Rota serverless POST /api/chat
   - ✅ Usa Gemini SDK diretamente
   - ✅ System prompt avisando: "PC offline"
   - ✅ Sem acesso a ferramentas locais

4. **Configuração (.env.local.example)**
   - ✅ Variáveis de ambiente documentadas
   - ✅ Exemplos de todos os cenários

---

## 🔧 INSTALAÇÃO E CONFIGURAÇÃO

### Passo 1: Instalar Dependências

**Backend**:
```bash
cd backend
pip install pyngrok uvicorn
```

**Frontend**:
```bash
cd frontend
npm install @google/generative-ai
```

### Passo 2: Configurar Variáveis de Ambiente

**Backend (.env)**:
```bash
# Já deve ter GEMINI_API_KEY
# Adicionar token Ngrok (opcional, mas recomendado):
NGROK_AUTH_TOKEN=seu-token-aqui
```

**Obter token Ngrok**:
1. Ir a https://dashboard.ngrok.com/
2. Criar conta (gratuita)
3. Copiar token de autenticação
4. Adicionar ao .env do backend

**Frontend (.env.local)**:
Copiar `frontend/.env.local.example` para `frontend/.env.local` e preencher:

```env
# ===== CENÁRIO 1: PC Local =====
NEXT_PUBLIC_WS_HOST=127.0.0.1
NEXT_PUBLIC_WS_PORT=8000
NEXT_PUBLIC_WS_PATH=/ws

# ===== PARA CELULAR/REMOTO =====
# Depois que o start_hub.py imprime a URL:
# Usar aquela URL no lugar de 127.0.0.1

# ===== GEMINI KEY (para modo nuvem) =====
NEXT_GEMINI_API_KEY=copiar-do-.env-backend
```

---

## 🚀 COMO RODAR

### Cenário 1: PC Local (Testes)

**Terminal 1 - Backend**:
```bash
cd backend
python start_hub.py
```

Vai imprimir:
```
[UVICORN] Iniciando servidor em 127.0.0.1:8000...
[✓] Quinta-Feira Hub pronto! Iniciando Uvicorn...
```

**Terminal 2 - Frontend**:
```bash
cd frontend
npm run dev
```

Abrir: http://localhost:3000

---

### Cenário 2: Acesso Remoto via Ngrok

**Terminal 1 - Backend COM Ngrok**:
```bash
cd backend
python start_hub.py --public --ngrok-token seu-token-aqui
```

Vai imprimir:
```
[NGROK] Tuneando porta 8000...
[NGROK] ✓ Túnel estabelecido: https://xxxx-xxx-xxx-xxx.ngrok-free.app

📡 INFORMAÇÕES DE ACESSO
========================================
✓ Backend Local: http://127.0.0.1:8000
✓ Backend Público (Ngrok): https://xxxx-xxx-xxx-xxx.ngrok-free.app

📝 CONFIGURAR FRONTEND (.env.local):
========================================
NEXT_PUBLIC_WS_HOST=xxxx-xxx-xxx-xxx.ngrok-free.app
NEXT_PUBLIC_WS_PORT=443
NEXT_PUBLIC_WS_PATH=/ws
```

**Atualizar Frontend (.env.local)**:
```env
# Copiar exatamente o que o terminal imprimiu
NEXT_PUBLIC_WS_HOST=xxxx-xxx-xxx-xxx.ngrok-free.app
NEXT_PUBLIC_WS_PORT=443
NEXT_PUBLIC_WS_PATH=/ws
NEXT_GEMINI_API_KEY=sua-chave-aqui
```

**Terminal 2 - Frontend**:
```bash
cd frontend
npm run dev
```

**Celular**:
- Conectar ao mesmo WiFi ou usar dados móveis
- Abrir: http://localhost:3000 (se na mesma rede)
- Ou: https://seu-dominio.ngrok-free.app (remoto)

---

### Cenário 3: PC Offline (Modo Nuvem)

Se o PC desligar:
- Frontend tenta conectar ao WebSocket por 5 segundos
- Timeout → Ativa **Modo Nuvem**
- UI muda para amarelo: "🌐 MODO NUVEM"
- Mensagens vão para `/api/chat` (Gemini Serverless)

**Terminal - Frontend (continua rodando)**:
```bash
cd frontend
npm run dev
```

Celular consegue conversar mesmo sem PC!

---

## 🔍 DEBUGGING

### Ver logs em tempo real

**Backend**:
```bash
# Já vê no stdout quando rodar start_hub.py
export NEXT_PUBLIC_DEBUG=true  # Frontend com debug
```

**Frontend (browser)**:
```javascript
// Na console do navegador:
localStorage.setItem('debug', 'true');
location.reload();
```

### Verificar conectividade

```bash
# Testar WebSocket local
curl http://127.0.0.1:8000/ws

# Testar API de Cloud Fallback
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Olá"}'
```

---

## ⚡ TROUBLESHOOTING

### Problema 1: "WebSocket falhou com código 1006"

**Causa**: Timeout na conexão (PC offline ou lento)

**Solução**:
- Verificar se backend está rodando
- Aumentar timeout em `page.tsx` (linha ~120)

### Problema 2: "NEXT_GEMINI_API_KEY não configurada"

**Causa**: Falta API key

**Solução**:
```bash
# Copiar do backend:
cat backend/.env | grep GEMINI_API_KEY

# Adicionar ao .env.local do frontend:
NEXT_GEMINI_API_KEY=sua-chave-aqui
```

### Problema 3: "Ngrok expirou depois de 2 horas"

**Comportamento esperado**: URLs Ngrok expiram em 2 horas

**Solução**: Reconectar (gera nova URL):
```bash
python start_hub.py --public --ngrok-token seu-token
```

### Problema 4: "Modo Nuvem aparece, mas sem resposta"

**Causa**: Gemini API key ausente ou inválida

**Solução**:
```bash
# Verificar se NEXT_GEMINI_API_KEY está correto
grep NEXT_GEMINI_API_KEY frontend/.env.local

# Testar em http://localhost:3000/api/chat
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "teste"}'
```

---

## 📡 Fluxo de Funcionamento

```
┌─────────────────────────────────────────────────────┐
│ CELULAR/NAVEGADOR (Frontend Next.js)                │
│                                                     │
│ Tenta: WebSocket → Backend PC                       │
└─────────────┬───────────────────────────────────────┘
              │
              ├─→ CONECTADO (5s) ✅
              │   └─→ Usar WebSocket
              │       └─→ Acesso a Spotify, YouTube, Terminal
              │           (Ferramenta completo)
              │
              └─→ TIMEOUT (5s) ❌
                  └─→ MODO NUVEM ATIVADO 🌐
                      └─→ Usar REST API (/api/chat)
                          └─→ Apenas chat (sem ferramentas)

┌─────────────────────────────────────────────────────┐
│ SE PC VOLTAR ONLINE:                                │
│ Frontend tenta reconectar automaticamente           │
│ (máx 2 tentativas, depois modo nuvem permanente)   │
└─────────────────────────────────────────────────────┘
```

---

## 🎬 Demonstração Prática

### Passo-a-passo para testar:

1. **Iniciar Hub**:
   ```bash
   cd backend
   python start_hub.py --public
   ```

2. **Copiar URL Ngrok** (ex: `https://abc123.ngrok-free.app`)

3. **Configurar Frontend**:
   ```bash
   cat > frontend/.env.local << EOF
   NEXT_PUBLIC_WS_HOST=abc123.ngrok-free.app
   NEXT_PUBLIC_WS_PORT=443
   NEXT_PUBLIC_WS_PATH=/ws
   NEXT_GEMINI_API_KEY=seu-gemini-key
   EOF
   ```

4. **Rodar Frontend**:
   ```bash
   cd frontend
   npm run dev
   ```

5. **Testar em outro dispositivo**:
   - Celular/tablet em outro WiFi
   - Abrir: `https://seu-dominio.ngrok-free.app`
   - Deve conectar e funcionar normalmente

6. **Desligar PC (para testar Modo Nuvem)**:
   - Fechar `start_hub.py` (Ctrl+C)
   - Esperar 5 segundos
   - Frontend vai mudar para 🌐 MODO NUVEM
   - Conversa vai funcionar normalmente (sem Spotify/YouTube)

---

## 📊 Arquitetura Resumida

```
┌─ Backend ──────────────────────────┐
│ FastAPI (uvicorn) + Ngrok Tunnel  │
│ - Tool Calling (Gemini)            │
│ - Spotify/YouTube/Terminal         │
│ - WebSocket para frontend          │
└────────────────────────────────────┘
                ▲
                │ WebSocket (wss://)
                │
┌─ Frontend ─────────────────────────┐
│ Next.js React                      │
│ - page.tsx (conversação)           │
│ - /api/chat (fallback nuvem)       │
│ - VoiceControl (barge-in)          │
└────────────────────────────────────┘
                ▲
                │ HTTPS
                │
┌─ Celular ──────────────────────────┐
│ Navegador (qualquer lugar)         │
│ WiFi ou dados móveis               │
└────────────────────────────────────┘
```

---

## ✅ Validação Final

- [ ] `start_hub.py` roda sem erros
- [ ] Ngrok gera URL pública
- [ ] Frontend conecta ao WebSocket
- [ ] Consegue enviar/receber mensagens
- [ ] PC offline → ativa 🌐 MODO NUVEM
- [ ] Modo nuvem responde via Gemini
- [ ] Celular consegue acessar via HTTPS
- [ ] Voice control funciona
- [ ] Barge-in interrompe áudio

---

## 🎉 Conclusão

**Fase 4 completa!** 

A Quinta-Feira agora é:
- ✅ Acessível de qualquer lugar
- ✅ Híbrida (local + nuvem)
- ✅ Resiliente (PC offline = Modo Nuvem)
- ✅ Segura (Ngrok + HTTPS)

**Próximas fases sugeridas**:
- [ ] Suporte a múltiplos dispositivos
- [ ] Persistência de chat em BD
- [ ] Notificações push
- [ ] Modo dark/light melhorado
- [ ] Histórico sincronizado
