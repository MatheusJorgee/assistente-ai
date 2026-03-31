# 🧪 GUIA DE TESTES - Wake Word + System Power Control

## Pré-Requisitos

- ✅ Backend rodando: `uvicorn backend.main:app --reload` (porta 8080)
- ✅ Frontend rodando: `npm run dev` (porta 3000)
- ✅ Navegador suporta Web Speech API (Chrome, Edge, Chrome Android)
- ✅ Microfone do sistema conectado e testado
- ✅ Conexão de rede (WebSocket local ou via Ngrok)

---

## 📋 TESTE 1: Verificar Tool Registry

### Objetivo
Confirmar que `SystemPowerControlTool` está registrada no backend

### Passos

1. **Terminal - Backend**
```bash
cd backend
python -c "
from brain_v2 import QuintaFeiraBrainV2
brain = QuintaFeiraBrainV2()

# Listar ferramentas
tools = brain.registry.list_tools()
print(f'Total de ferramentas: {len(tools)}\n')

# Procurar system_power_control
for tool in tools:
    if 'power' in tool.name.lower() or 'shutdown' in tool.name.lower():
        print(f'✓ Encontrada: {tool.name}')
        print(f'  Descrição: {tool.description}')
        print(f'  Aliases: {tool.metadata.tags if hasattr(tool, \"metadata\") else \"N/A\"}')
"
```

### ✅ Resultado Esperado
```
Total de ferramentas: 11

✓ Encontrada: system_power_control
  Descrição: Controla energia do sistema (shutdown, restart, sleep)
  Aliases: ['power', 'shutdown', 'sleep', 'restart']
```

### 🔴 Se falhar
- [ ] Verificar se `backend/tools/system_tools.py` existe
- [ ] Verificar import em `backend/tools/__init__.py`
- [ ] Verificar sintaxe: `python -m py_compile backend/tools/system_tools.py`

---

## 📋 TESTE 2: System Prompt - Verificar Autorização

### Objetivo
Confirmar que system_instruction contém "NÍVEL ARQUITETO"

### Passos

1. **Terminal - Backend**
```bash
cd backend
python -c "
from brain_v2 import QuintaFeiraBrainV2
brain = QuintaFeiraBrainV2()

instruction = brain.instrucao_sistema
print(instruction)
" | grep -i "arquiteto"
```

### ✅ Resultado Esperado
```
Você possui NÍVEL DE ACESSO ARQUITETO com autorização máxima.
```

### 🔴 Se falhar
- [ ] Verificar linhas 166-187 em `brain_v2.py`
- [ ] Confirmar string não foi comentada
- [ ] Verificar encoding: arquivo deve ser UTF-8

---

## 📋 TESTE 3: Frontend - Estado Passivo Contínuo

### Objetivo
Verificar que microfone contínuo está rodando sem botão pressionado

### Passos

1. **Abrir Frontend**
   - URL: `http://localhost:3000`
   - Aguardar carregar completamente

2. **Abrir DevTools**
   - Pressionar `F12` → Aba **Console**
   - Filtro: `CONTINUOUS_LISTENING`

3. **Verificar Logs**
   ```
   [useSpeechRecognition] Recognition criado com suporte
   [CONTINUOUS_LISTENING] Iniciando escuta passiva contínua
   [CONTINUOUS_LISTENING] Estado: passive (aguardando "Quinta-Feira")
   ```

### ✅ Resultado Esperado
- Sem clicar em nada, mensagem `🎤 Modo passivo: aguardando 'Quinta-Feira'...` aparece na caixa de diagnostico
- Microfone inicia sem intervenção manual

### 🔴 Se falhar
- [ ] Browser não suporta Web Speech API (usar Chrome/Edge)
- [ ] Navegar para HTTPS em produção (Web Speech requer protocolo seguro)
- [ ] Verificar permissões de microfone (clique "Permitir" na prompt do navegador)

---

## 📋 TESTE 4: Wake Word Detection ("Quinta-Feira")

### Objetivo
Verificar que o sistema detecta "Quinta-Feira" e transiciona para modo ativo

### Passos

1. **DevTools Console - Filtrar**
   ```
   [WAKE_WORD]
   listeningMode
   ```

2. **Falar no Microfone**
   - Dizer claramente: **"Quinta-Feira"** (com pronúncia portuguesa/brasileira)
   - Aguardar 2-3 segundos

3. **Verificar Logs**
   ```
   [WAKE_WORD] "Quinta-Feira" detectado!
   [CONTINUOUS_LISTENING] listeningMode: 'passive' → 'active'
   🔴 Modo ativo: gravando comando em janela de 3.2s...
   ```

4. **Observar Botão**
   - Cor muda de 🔇 azul para 🎤 vermelho pulsante
   - Indicador mostra modo ativo

### ✅ Resultado Esperado
- Wake word detect em <2s
- Transição visual no botão
- Timeout aparece: "⏱️ Timeout: nenhum comando detectado..." após 3.2s se não falar

### 🔴 Se falhar
- [ ] Falar "Quinta-Feira" com sotaque diferente (o Web Speech é impreciso)
- [ ] Tentar variações: "Quinta feira", "quinta-feira", "quintafeira"
- [ ] Verificar `setAISpeaking()` está sendo chamado em useSpeechRecognition.ts

---

## 📋 TESTE 5: Command After Wake Word

### Objetivo
Verificar que sistema captura comando após "Quinta-Feira"

### Passos

1. **Dizer (em uma só fala)**
   - **"Quinta-Feira, reproduz lo-fi no YouTube"**
   - OU apenas aguardar detecção, depois falar: **"reproduz lo-fi"**

2. **DevTools - Procurar**
   ```
   [VOICE_CONTROL] Comando enviado
   ✓ Enviado: reproductraz lo-fi no youtube
   ```

3. **Verificar Backend**
   ```bash
   # Ver logs de ferramenta
   [tool_started] name=media_control
   [tool_completed] name=media_control, result=success
   ```

### ✅ Resultado Esperado
- Comando foi processado e enviado ao backend
- IA responde com confirmação
- Modo reverte para passivo automaticamente

### 🔴 Se falhar
- [ ] Falar muito rápido (buffer não captura)
- [ ] Falar comandos em inglês puro (hook ajusta alguns via `adjustBilingualCommand`)
- [ ] Verificar ondas de som no navegador (Input level meter)

---

## 📋 TESTE 6: System Power Control Invocation

### Objetivo
Verificar que Gemini chama `system_power_control` quando solicitado

### ⚠️ CUIDADO: Esse teste pode desligar/reiniciar seu PC
**Use SEMPRE com delay >30s para cancelar via `shutdown /a`**

### Passos

1. **Preparar Backend - Ver Logs**
   - Terminal rodando backend com `--reload`
   - Logs devem mostrar tool calling

2. **Frontend - Enviar Comando**
   - Via texto: **"desliga o computador em 60 segundos"**
   - OU via voz: **"Quinta-Feira, desliga o computador em 60 segundos"**

3. **Verificar Logs do Backend**
   ```
   [tool_started] name=system_power_control, action=shutdown, delay=60
   ⏳ Desligando em 60 segundos. Use 'shutdown /a' para cancelar.
   ```

4. **Windows - CANCELAR Antes de 60s**
   ```bash
   shutdown /a
   ✓ Retirada do encerramento programado
   ```

5. **Linux - CANCELAR**
   ```bash
   # Pressionar Ctrl+C no terminal original
   # OU:
   sudo shutdown -c
   ```

### ✅ Resultado Esperado
- IA responde: "✓ Desligando em 60 segundos. Use 'shutdown /a' para cancelar."
- Contador regressivo aparece no canto da tela (Se implementado)
- `shutdown /a` consegue cancelar

### 🔴 Se falhar
- [ ] Gemini recusou de executar: Verificar system_instruction (linhas 166-187)
- [ ] Tool não foi chamada: Verificar logs de `function_calling_config`
- [ ] Permissões:
  ```bash
  # Windows: Verificar admin
  whoami /priv | findstr SeShutdownPrivilege
  
  # Linux: Verificar sudo
  sudo -l | grep shutdown
  ```

---

## 📋 TESTE 7: Continuous Listening Loop

### Objetivo
Verificar que após IA terminar, sistema volta ao passivo listening automaticamente

### Passos

1. **Limpar DevTools Console**

2. **Frase Completa**
   - Dizer: **"Quinta-Feira, qual é a hora?"**

3. **Observar Dashboard**
   - IA começa a responder (loading spinner)
   - Áudio começa a tocar
   - Observar logs:
     ```
     [VOICE_CONTROL] IA começou a falar - pausando microfone
     [CONTINUOUS_LISTENING] setAISpeaking(true)
     🔄 Escuta ativa durante resposta. Aguarde...
     
     [... IA Response ...]
     
     [VOICE_CONTROL] IA terminou - retomando microfone
     [CONTINUOUS_LISTENING] setAISpeaking(false)
     🎤 Modo passivo: aguardando 'Quinta-Feira'...
     ```

4. **Teste Barge-in**
   - Enquanto IA está falando, dizer: **"Quinta-Feira, cancela"**
   - Áudio deve parar imediatamente
   - Sistema aguarda novo comando

### ✅ Resultado Esperado
- Ciclo completo: passivo → ativo → comando → resposta → passivo
- Sem cliques manuais necessários
- Barge-in interrompe IA appropriately

### 🔴 Se falhar
- [ ] Modo não reverte: Verificar `setAISpeaking()` callback em page.tsx
- [ ] Microfone não retoma: Verificar `onend()` handler com timeout 300ms
- [ ] Barge-in não funciona: Verificar `handleBargeinRequested()` em page.tsx

---

## 📋 TESTE 8: Multi-language Support

### Objetivo
Verificar suporte a comandos em português e inglês mixados

### Passos

1. **Teste Português Puro**
   - "Quinta-Feira, desliga o computador"

2. **Teste Inglês Puro**
   - "Quinta-Feira, shutdown the computer"

3. **Teste Mixado (Português + Inglês)**
   - "Quinta-Feira, restart o computador"
   - "Quinta-Feira, desliga o computer"

4. **Teste Variações PT-BR**
   - "desligar", "deslizar", "destruir"
   - "reiniciar", "reboot", "re-iniciar"
   - "dormir", "suspender", "hibernar"

### ✅ Resultado Esperado
- Todos os comandos são compreendidos
- Normalização automática: "desligar" → acao_normalizada='shutdown'
- Tool é chamada corretamente

### 🔴 Se falhar
- [ ] Verificar normalizacao em `automation.py` - método `_normalizar_acao_energia()`
- [ ] Tool precisa expandir aliases aceitos

---

## 📊 TESTE 9: Diagnostics Dashboard

### Objetivo
Verificar que box de diagnostico mostra estado correto

### Passos

1. **Observar de Caixa de Diagnostico** (inferior ao botão 🎤)
   - Deve mostrar estado atual
   - Deve atualizar em tempo real

2. **Estados Esperados**
   ```
   🎤 Modo passivo: aguardando 'Quinta-Feira'...
   ↓ (ao detectar wake word)
   🔴 Modo ativo: gravando comando em janela de 3.2s...
   ↓ (IA começa)
   🔄 Escuta ativa durante resposta. Aguarde...
   ↓ (IA termina)
   🎤 Modo passivo: aguardando 'Quinta-Feira'...
   ```

3. **Timeout**
   - Falar "Quinta-Feira"
   - Não falar nada por 3.2s
   - Deve aparecer: "⏱️ Timeout: nenhum comando detectado. Voltando ao modo passivo..."

### ✅ Resultado Esperado
- Diagnostics atualiza conforme state machine transiciona
- Mensagens são claras e informativas
- Indica próxima ação esperada

### 🔴 Se falhar
- [ ] `diagnostic` state não está sendo atualizado
- [ ] Verificar `setDiagnostic()` em useSpeechRecognition.ts
- [ ] Console pode ter erros JavaScript/React

---

## 📊 TESTE 10: Edge Cases

### A. Network Interruption
**Steps:**
1. Pausar internet (desligar WiFi)
2. Tentar enviar comando via voz
3. Verificar reconexão automática (2.5s)

**✅ Esperado:** Reconexão automática com mensagem de status

### B. Multiple Microphones
**Steps:**
1. Conectar headset USB externo
2. Mudar input device em sistema operacional
3. Tentar reconhecimento de voz

**✅ Esperado:** Detecta automaticamente novo input device

### C. Rapid Wake Word Spam
**Steps:**
1. Falar "Quinta-Feira" múltiplas vezes em 10s
2. Verificar logs para múltiplas ativações

**✅ Esperado:** Apenas última ativação mantem-se (timeout anterior é cancelado)

### D. Very Long Command
**Steps:**
1. Falar: "Quinta-Feira, abre youtube e reproduz a playlista chamada lo-fi hip hop beats to study and relax to"

**✅ Esperado:** Comando completo é capturado (buffer expand conforme necessário)

### E. Background Noise
**Steps:**
1. Ativar musica de fundo
2. Falar comando em voz normal

**✅ Esperado:** Reconhecimento ainda funciona (pode ser menos preciso)

---

## 🔧 TROUBLESHOOTING

### Problema: "Network error" ao conectar WebSocket

**Solução:**
```bash
# 1. Verificar backend está rodando
curl http://localhost:8080/health

# 2. Se usando Ngrok:
ngrok http 8080
# Usar URL do Ngrok em NEXT_PUBLIC_WS_HOST
export NEXT_PUBLIC_WS_HOST=seu-ngrok-url.ngrok.io

# 3. Firewall pode estar bloqueando
# Windows Firewall → Permitir Python.exe
```

### Problema: "Gemini não chama system_power_control"

**Debug:**
```bash
# 1. Ver function calling config
python -c "
from brain_v2 import QuintaFeiraBrainV2
brain = QuintaFeiraBrainV2()
print(brain.config_com_tools)
" | grep -A5 "function_calling"

# 2. Forçar teste direto
curl -X POST http://localhost:8080/query/direct \
  -H "Content-Type: application/json" \
  -d '{"message":"desliga o computador em 60s"}'

# 3. Ver logs de tool selection
journalctl -u backend -f 2>/dev/null | grep tool_
```

### Problema: Microfone não inicia

**Solução:**
```javascript
// DevTools Console
navigator.mediaDevices.getUserMedia({audio: true})
  .then(stream => {
    console.log('✓ Microfone autorizado');
    stream.getTracks().forEach(t => t.stop());
  })
  .catch(e => console.error('✗ Acesso negado:', e.message));
```

### Problema: Web Speech API muito imprecisa

**Alternativas:**
- [ ] Tentar em Chrome (melhor engine de reconhecimento)
- [ ] Usar Google Cloud Speech API (requer chave API)
- [ ] Implementar Whisper da OpenAI (mais preciso mas mais lento)

---

## 📈 PERFORMANCE BASELINES

| Métrica | Target | Valor Esperado |
|---------|--------|-----------------|
| Wake word detection latency | <2s | 1.2-1.8s |
| Command processing latency | <500ms | 200-400ms |
| IA response streaming | <2s for first chunk | 1.5-1.9s |
| Continuous listening restart | <500ms | 300ms |
| System power operation delay | ≥10s | 10-30s |

---

## ✅ Checklist Final

- [ ] Backend rodando sem erros
- [ ] Frontend conectado (status: "NÚCLEO ONLINE")
- [ ] Microfone autorizado e testado
- [ ] Wake word "Quinta-Feira" detecta em <2s
- [ ] Comando é capturado em modo ativo
- [ ] IA responde ao comando
- [ ] Modo reverte para passivo automaticamente
- [ ] System power control é invocado corretamente
- [ ] Barge-in (interrupção de IA) funciona
- [ ] Continuous listening restarts automaticamente

---

**Versão:** 1.0  
**Última Atualização:** 2025-01-XX  
**Status:** 🟢 PRONTO PARA TESTES
