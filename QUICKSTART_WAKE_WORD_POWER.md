# ⚡ QUICKSTART - Wake Word + System Power Control (5 Min Setup)

## 🚀 Iniciar o Sistema (20 segundos)

### Terminal 1 - Backend
```bash
cd backend
pip install -r requirements.txt  # Se não instalado ainda
uvicorn main:app --reload
# ✓ Servidor rodando em http://localhost:8080
```

### Terminal 2 - Frontend
```bash
cd frontend
npm install  # Se não instalado ainda
npm run dev
# ✓ Interface em http://localhost:3000
# ✓ Abre automaticamente no navegador
```

---

## 🎤 Usar Imediatamente

### Cenário 1: Desligar Computador

```
1. Abrir http://localhost:3000
2. Falar no Microfone: "Quinta-Feira"
   → Sistema responde com beep e ativa modo ativo (🔴)
3. Falar: "Desliga o computador"
   → IA confirma: "✓ Desligando em 10 segundos"
4. WINDOWS: Digitar em Command: shutdown /a
   → "Retirada do encerramento programado"
5. LINUX: Digitar: sudo shutdown -c
   → Encerramento cancelado
```

### Cenário 2: Reiniciar Computador

```
1. Falar: "Quinta-Feira"
2. Falar: "Reinicia o computador"
   → Confirmação: "✓ Reiniciando em 10 segundos"
3. Cancelar: shutdown /a (Windows) ou sudo shutdown -c (Linux)
```

### Cenário 3: Put to Sleep

```
1. Falar: "Quinta-Feira"
2. Falar: "Dorme"
   → Computador entra em sleep/suspensão
   → Acordar com movimento de mouse/teclado
```

### Cenário 4: Comando de Mídia + Voz

```
1. Falar: "Quinta-Feira, abre YouTube e reproduz lofi"
   → YouTube abre e começa automático
2. Falar: "Aumenta volume"
3. Falar: "Pausa"
```

---

## 🔧 Validar Instalação (30 segundos)

### Check 1: Backend Tools
```bash
cd backend
python -c "
from brain_v2 import QuintaFeiraBrainV2
brain = QuintaFeiraBrainV2()
tools = brain.registry.list_tools()
power_tools = [t.name for t in tools if 'power' in t.name.lower()]
print(f'✓ {len(tools)} ferramentas registradas')
print(f'✓ Power control: {power_tools}')
"
```

**Saída esperada:**
```
✓ 11 ferramentas registradas
✓ Power control: ['system_power_control']
```

### Check 2: System Prompt Authorization
```bash
cd backend
python -c "
from brain_v2 import QuintaFeiraBrainV2
brain = QuintaFeiraBrainV2()
has_auth = 'ARQUITETO' in brain.instrucao_sistema
print('✓ Authorization: ENABLED' if has_auth else '✗ Authorization: MISSING')
"
```

### Check 3: Frontend State Machine
1. Abrir DevTools (F12) → Console
2. Procurar por:
   ```
   [CONTINUOUS_LISTENING] listeningMode: 'passive'
   ```
   ✓ Se ver = funcionando

---

## 🎯 Testar End-to-End (2 min)

### Via Voz (Recomendado)

```
1. Ir para http://localhost:3000
2. Microphone Device Check:
   - Clique no ícone 🎤
   - Aceitar permissão de microfone
   - Deve aparecer "🎤 Modo passivo: aguardando 'Quinta-Feira'..."

3. Test Wake Word:
   - Fale: "Quinta-Feira"
   - Deve mudarpara 🔴 vermelho
   - Deve aparecer "🔴 Modo ativo: gravando comando em janela de 3.2s..."

4. Test Command:
   - Fale: "qual é a hora?"
   - IA responde com hora atual
   - Deve voltar ao modo passivo 🎤 automático

5. Test Power Control (⚠️ USE DELAY >30S):
   - Fale: "desliga em 60 segundos"
   - Backend log deve mostrar: [tool_started] system_power_control
   - RÁPIDO: No Windows: shutdown /a (para cancelar)
```

### Via Texto (Mais Seguro)

```
1. Na interface, usar box "Digite seu comando"
2. Enviar: "qual é a hora?"
   → IA responde
3. Enviar: "abrir youtube e tocar lo-fi"
   → YouTube abre

NÃO TESTAR POWER CONTROL VIA TEXTO ACIDENTALMENTE!
```

---

## 📊 Verificar Logs em Tempo Real

### Backend Logs
Terminal já mostra:
```
INFO:     Started server process [xxxxx]
GET /ws HTTP/1.1" 101 
[tool_started] name=system_power_control
[tool_completed] name=system_power_control
```

### Frontend DevTools
Pressionar `F12` → Console e filtrar:
- `[WAKE_WORD]` - Para wake word events
- `[VOICE_CONTROL]` - Para state transitions
- `[CONTINUOUS_LISTENING]` - Para listening mode
- `[BARGE_IN]` - Para interrupções

---

## ⚠️ Troubleshooting Rápido

| Problema | Solução |
|----------|---------|
| Microfone não inicia | Aceitar permissão (popup no navegador). Se não aparecer, usar HTTPS |
| Wake word não detecta | Falar mais claro/alto. Tentar "Quinta Feira" sem hífen |
| Comando não envia | Verificar conectividade WebSocket (status "NÚCLEO ONLINE") |
| Gemini recusa desligar | Verificar system_instruction tem "NÍVEL ARQUITETO" (brain_v2.py:166) |
| Microfone paralisa | Atualizar Chrome/Edge. Caso persista, reiniciar aba |
| Backend erro ao importar | Verificar `backend/tools/system_tools.py` existe |

---

## 🔐 Segurança - Lembrete

⚠️ **System Power Control Enabled!**

- Sistema **NÃO** pede confirmação de desligamento
- Sempre usa delay mínimo de 10 segundos (cancelável)
- Considere restringir acesso a localhost ou VPN
- Para produção, implementar:
  - [ ] Rate limiting (máx 3 ações/hora)
  - [ ] IP whitelist
  - [ ] Logging de auditoria
  - [ ] PIN de confirmação opcional

---

## 📚 Documentação Completa

Para mais detalhes, consulte:

- **[WAKE_WORD_SYSTEM_POWER_CONTROL_FINAL.md](WAKE_WORD_SYSTEM_POWER_CONTROL_FINAL.md)** - Arquitetura completa
- **[TESTES_WAKE_WORD_POWER_CONTROL.md](TESTES_WAKE_WORD_POWER_CONTROL.md)** - 10 testes detalhados
- **[README_ARQUITETURA.md](backend/README_ARQUITETURA.md)** - Tool Registry padrão
- **[brain_v2.py](backend/brain_v2.py)** - Linhas 166-187 (System Prompt)

---

## 🎓 Exemplos de Comandos

| Comando | Efeito |
|---------|--------|
| "Quinta-Feira" | Ativa modo ativo (3.2s para comando) |
| "Quinta-Feira, desliga" | Desliga em 10s (cancelável com `shutdown /a`) |
| "Quinta-Feira, reinicia" | Reinicia em 10s |
| "Quinta-Feira, dorme" | Suspende sistema |
| "Quinta-Feira, qual é a hora?" | Lê hora atual |
| "Quinta-Feira, abre YouTube" | Abre YouTube no navegador |
| "Quinta-Feira, tocar lo-fi" | Reproduz lo-fi no YouTube |
| "Quinta-Feira, aumenta volume" | Volume +10% |
| "Quinta-Feira, pausa" | Pausa mídia atual |
| "Quinta-Feira, próxima música" | Próxima faixa |

---

## ✅ Checklist - Sistema Pronto

- [ ] Backend rodando (porta 8080)
- [ ] Frontend rodando (porta 3000)
- [ ] Microfone conectado e testado
- [ ] Navegador suporta Web Speech (Chrome/Edge)
- [ ] `SystemPowerControlTool` aparece no registry
- [ ] System prompt contém "NÍVEL ARQUITETO"
- [ ] Wake word "Quinta-Feira" detecta em <2s
- [ ] Comando é capturado após wake word
- [ ] IA responde e modo volta ao passivo
- [ ] System power control nunca é recusado
- [ ] Continuous listening sempre ativo

---

**🚀 Pronto! Seu sistema Quinta-Feira com controle de energia está online.**

Para começar agora: `uvicorn backend.main:app --reload` + `npm run dev` + Fale "Quinta-Feira"

---

**Versão:** 1.0 - QUICKSTART  
**Data:** 2025-01-XX  
**Status:** ✅ PRONTO PARA USO
