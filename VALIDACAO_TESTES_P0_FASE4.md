# ✅ VALIDAÇÃO E TESTES: Bugs P0 + Fase 4

## Instruções para Validação Completa

---

## 🔴 TEST 1: Validar Bug 1 Fix (Tool Calling)

### Setup
```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate  # ou .\.venv\Scripts\Activate.ps1 (Windows)
pip install -r requirements.txt

# Iniciar backend
python start_hub.py
```

### Testes no Browser

**1. Teste Spotify** (se configurado)
```
Input:  "Toca The Weeknd Blinding Lights"
Expected: ▶ Tocando: The Weeknd - Blinding Lights
Test:   ✓ PASS se música toca (webhook Spotify)
        ✗ FAIL se mensagem "Como sou um assistente..."
```

**2. Teste YouTube**
```
Input:  "Coloca Dua Lipa no YouTube"
Expected: Sucesso! Encontrei e coloquei 'Dua Lipa' a tocar.
Test:   ✓ PASS se vídeo abre
        ✗ FAIL se mensagem nega capability
```

**3. Teste Terminal** (se seguro)
```
Input:  "Abre o Notepad"
Expected: Sucesso ao abrir Notepad
Test:   ✓ PASS se aplicativo abre
        ✗ FAIL se nega acesso
```

### Diagnóstico Avançado

```python
# No backend, verificar se ferramentas estão registradas:
from backend.brain_v2 import QuintaFeiraBrainV2

brain = QuintaFeiraBrainV2()
print(f"Ferramentas registradas: {brain.tool_registry.list_tools()}")
print(f"Chat session ferramentas: {brain.chat_session.config.tools}")  # Deve NOT estar vazio!
```

---

## 🔴 TEST 2: Validar Bug 2 Fix (Memory/Performance)

### Setup
```bash
# Ter o backend rodando
# Ter o frontend rodando (npm run dev)
# Abrir Gestor de Tarefas (Ctrl+Shift+Esc)
```

### Teste de Memory/CPU

**Pré-Teste**:
1. Abrir Gestor de Tarefas
2. Procurar por `msedge.exe` (processos)
3. Ver Memory inicial

**Teste de 10 Músicas**:
```
1. Enviar: "Toca música clássica"
   └─ Aguardar 30s (YouTube abrir)
   └─ Verificar RAM em Gestor: +150MB
   └─ Contar processos msedge: X

2. Enviar: "Próxima"
   └─ Aguardar 10s
   └─ Verificar RAM: +150MB (não +300MB!)
   └─ Contar processos msedge: X (não aumenta!)

3. Repetir 8x mais (total 10 músicas)
   └─ RAM deve manter-se ~150MB
   └─ Processos devem ser SEMPRE X
   └─ PC deve estar responsivo
```

### Resultado Esperado

```
ANTES (Bug):
Música 1:  msedge.exe +1 processo, RAM +150MB
Música 2:  msedge.exe +2 processos, RAM +300MB
Música 3:  msedge.exe +3 processos, RAM +450MB
...
Música 10: msedge.exe +10 processos, RAM +1500MB ❌ TRAVA

DEPOIS (Fix):
Música 1:  msedge.exe 1 processo, RAM +150MB
Música 2:  msedge.exe 1 processo, RAM +150MB ✓
Música 3:  msedge.exe 1 processo, RAM +150MB ✓
...
Música 10: msedge.exe 1 processo, RAM +150MB ✓ ESTÁVEL
```

### Validação Técnica

```bash
# Verificar se OSAutomation destrutor está funcionando:
# 1. Colocar breakpoint em OSAutomation.__del__()
# 2. Executar músicas 10x
# 3. Destrutor deve ser chamado ~10x
# 4. Cada vez, _cleanup_playwright() executa
```

---

## 🌐 TEST 3: Modo Nuvem (Cloud Fallback)

### Setup 1: Teste Local (PC Online)

```bash
# Ter backend rodando
# Ter frontend rodando
# Abrir http://localhost:3000 em browser
```

**Teste Online**:
```
1. Status: "CANAL ONLINE" (verde)
2. Enviar: "Toca música"
3. Deve conectar via WebSocket
4. Resposta rápida (<1s)
5. Ferramenta executa (música toca)
✓ PASS: Usa backend PC
```

### Setup 2: Teste Cloud Fallback (PC Offline Simulado)

```bash
# 1. Manter frontend rodando
# 2. PARAR backend (Ctrl+C em start_hub.py)
# 3. Obter erro no browser "Reconectando..."
```

**Teste Offline**:
```
1. Aguardar ~5s
2. Status muda: "MODO NUVEM (PC OFFLINE)" (amarelo)
3. Toast mostra: "🌐 Modo Nuvem ativado"
4. Enviar: "Quem foi Albert Einstein?"
5. Deve responder via API Rest (não via WS)
6. Resposta vem com sucesso
✓ PASS: Modo Nuvem funciona
```

### Verificação de Logs

**No Console do Browser** (F12 → Console):
```
[CONEXÃO] Tentando WebSocket: ws://127.0.0.1:8000/ws
[CONEXÃO] WebSocket fechado - ativando MODO NUVEM
[NUVEM] Enviando via API REST (PC offline)
[NUVEM] Resposta gerada: "Albert Einstein foi..."
```

**Na resposta JSON** (Network tab):
```json
{
  "success": true,
  "response": "Albert Einstein foi...",
  "mode": "cloud",
  "model": "gemini-2.5-flash",
  "timestamp": "2026-03-29T..."
}
```

---

## 🚀 TEST 4: Ngrok Public Tunnel

### Setup

```bash
# 1. Instalar pyngrok
pip install pyngrok

# 2. Login/obter token Ngrok
# Criar conta em: https://dashboard.ngrok.com/
# Copiar Auth Token

# 3. Iniciar hub com público
python backend/start_hub.py --public --ngrok-token seu_token_aqui
```

### Output Esperado

```
[NGROK] ✓ Túnel estabelecido!
[NGROK] 🌐 URL Pública: https://abc123.ngrok.io

📝 CONFIGURAR FRONTEND:
NEXT_PUBLIC_WS_HOST=abc123.ngrok.io
NEXT_PUBLIC_WS_PORT=443
```

### Teste de Acesso Remoto

**De outro PC/Dispositivo**:
```
1. Obtém URL: https://abc123.ngrok.io
2. Edita frontend/.env.local:
   NEXT_PUBLIC_WS_HOST=abc123.ngrok.io
3. Recarrega frontend
4. Deve conectar ao backend remoto
5. WebSocket status: "CANAL ONLINE"
6. Comandos funcionam normalmente
✓ PASS: Acesso remoto via Ngrok OK
```

---

## 📊 TEST 5: Integração Completa (E2E)

### Cenário: Usuario Matheus

```
Dia 1:
  - PC ligado, 5 músicas YouTube
  - Sem travamentos ✓
  - Tool calling trabalhando ✓
  
Dia 2 (PC desligado):
  - Abre frontend no celular
  - Backend não liga (PC offline)
  - Status: "MODO NUVEM"
  - Conversa normal (Google + biologia)
  - Sem acesso a Spotify/YouTube ✓
  
Dia 3 (PC ligado remotamente):
  - Inicia start_hub.py --public
  - Obtém URL Ngrok
  - De outro lugar, acessa via URL pública
  - Toca música, executa comandos
  - Workshop funciona totalmente ✓
```

---

## 🔧 Troubleshooting

### Problem 1: "Como sou um assistente..."
```
Causa: Tool calling não injetado
Solução: Verificar brain_v2._converter_ferramentas_para_gemini()
         Confirmar: config_chat.tools = ferramentas_gemini
```

### Problem 2: PC trava após 5 músicas
```
Causa: Contexts Playwright não fechados
Solução: Verificar OSAutomation.context = self.context (guardado)
         Confirmar cleanup (destrutor __del__)
         Reiniciar app
```

### Problem 3: Modo nuvem não ativa
```
Causa: WebSocket não reconhece offline
Solução: Parar backend manualmente
         Verificar ws.onclose listener
         Confirmar enviarModoNuvem() é chamada
```

### Problem 4: Ngrok não conecta
```
Causa: Token inválido ou pyngrok não instalado
Solução: pip install pyngrok
         Verificar token: https://dashboard.ngrok.com/
         Testar: python -c "from pyngrok import ngrok; print(ngrok.__version__)"
```

---

## 📋 Checklist Final de Validação

### Bug 1: Tool Calling
- [ ] Spotify toca música
- [ ] YouTube abre vídeo
- [ ] Terminal abre apps
- [ ] Nenhuma mensagem "como um assistente"
- [ ] System prompt doutrina inquebrável log

### Bug 2: Memory/Performance
- [ ] 10 músicas sem trava
- [ ] RAM estável (~150MB constante)
- [ ] Processos msedge = 1 (não aumentam)
- [ ] Gestor de Tarefas responsivo
- [ ] Cleanup destrutor é executado

### Fase 4.1: Env Vars
- [ ] .env.local.example criado
- [ ] Frontend lê NEXT_PUBLIC_WS_HOST
- [ ] Frontend lê NEXT_PUBLIC_WS_PORT
- [ ] Frontend lê NEXT_PUBLIC_API_URL

### Fase 4.2: Cloud Fallback
- [ ] Status muda para "MODO NUVEM" offline
- [ ] API /api/chat responde
- [ ] Gemini serverless funciona
- [ ] System prompt nuvem limitador
- [ ] Reconexão automática

### Fase 4.3: Ngrok Tunnel
- [ ] start_hub.py inicia uvicorn
- [ ] Ngrok túnel estabelecido
- [ ] URL pública exibida
- [ ] Acesso remoto funciona
- [ ] URL expira/renova normal

---

## 🎯 Resultado Esperado

```
✅ SISTEMA OPERACIONAL
✅ BUGS P0 CORRIGIDOS
✅ FASE 4 IMPLEMENTADA
✅ PRONTO PARA PRODUÇÃO
```

---

## 📞 Contacto em Caso de Erro

Se encontrar problemas não listados aqui:

1. Verificar logs completos
2. Consultar DIAGNOSTICO_BUGS_P0.md
3. Revisar CORRECAO_P0_E_FASE4_RESUMO.md
4. Procurar por [ERROR] ou [❌] nos outputs

---

**Data de Validação**: 29 de Março de 2026  
**Validador**: Arquiteto Sênior  
**Status**: ✅ PRONTO PARA TESTE
