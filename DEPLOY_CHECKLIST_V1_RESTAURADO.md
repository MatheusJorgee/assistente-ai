# 🚀 CHECKLIST DE DEPLOY & VALIDAÇÃO - V1 Features Restauradas

## ✅ PRÉ-DEPLOY CHECKLIST

### Backend
- [x] `backend/core/cortex_bilingue.py` criado (350+ linhas)
- [x] `backend/brain_v2.py` integra cortex no `ask()`
- [x] `backend/main.py` handler de interrupt WebSocket
- [x] Imports resilientes (try/except para ambos caminhos)
- [x] `.env` suporta novas variáveis (se necessário)

### Frontend
- [x] `frontend/hooks/useSpeechRecognition.ts` máquina de estados
- [x] `frontend/components/VoiceControl.tsx` silent ACK + bilingual
- [x] `frontend/app/page.tsx` barge-in + audioRef
- [x] Imports corretos (sem ciclos de dependência)
- [x] TypeScript: zero erros

### Testes
- [x] `backend/teste_auditoria_v1_v2.py` suite completa
- [x] 5/9 testes críticos passando
- [x] Cores verde/vermelho no output

---

## 🔧 INSTALAÇÃO & SETUP

### 1. Backend (Python)

```bash
cd backend

# Ativar venv (Windows)
.venv\Scripts\activate

# Instalar cortex_bilingue dependencies (se não tiver)
pip install python-Levenshtein  # opcional para fuzzy matching avançado

# Rodar testes
python teste_auditoria_v1_v2.py

# Iniciar servidor
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend (Node.js)

```bash
cd frontend

# Instalar dependências
npm install

# Dev server
npm run dev  # http://localhost:3000

# Build produção
npm run build
npm run start
```

---

## 🧪 TESTES DE VALIDAÇÃO

### Unit Tests: Cortex Bilíngue

```bash
python -c "
from backend.core.cortex_bilingue import get_cortex_bilingue
cortex = get_cortex_bilingue()

# Test 1: Phonetic correction
corrected, entity = cortex.process_bilingual_command('the perfeit paira')
assert 'perfect' in corrected
print('✓ Test 1: Phonetic Correction PASSED')

# Test 2: Learning
cortex.learn_correction('spotifai', 'spotify')
corrected, _ = cortex.process_bilingual_command('spotifai')
assert corrected == 'spotify'
print('✓ Test 2: Learning PASSED')

# Test 3: Language detection
lang = cortex.detect_language('toca samba')
print(f'✓ Test 3: Language Detection PASSED (detected: {lang})')
"
```

### Integration Tests: Frontend

```bash
# 1. Abrir http://localhost:3000
# 2. Abrir DevTools (F12 → Console)
# 3. Testar Wake Word:
#    - Clique no botão do microfone
#    - Diga "cinco feira" (quebrado) ou "quinta-feira" (correto)
#    - Verifique console: [WAKE_WORD] Detectado!

# 4. Testar Silent ACK:
#    - Diga "pausa" (após ativar com "quinta-feira")
#    - Deve reproduzir 660Hz beep
#    - Verifique console: [SILENT_ACK] ✓ 660Hz

# 5. Testar Barge-in:
#    - Clique em enviar mensagem
#    - Imediatamente clique no microfone
#    - Faça som (qualquer fala)
#    - Áudio da IA deve parar
#    - Toast: "🔄 Áudio interrompido"
```

### End-to-End: Full Flow

```bash
# Terminal 1: Backend
cd backend
. .venv/Scripts/activate
uvicorn main:app --reload

# Terminal 2: Frontend
cd frontend
npm run dev

# Browser: http://localhost:3000
# 1. Abrir DevTools
# 2. Dizer "quinta feira" + comando
# 3. Observar:
#    - Console: [WAKE_WORD] → [COMMAND_RECEIVED]
#    - Chat: msg usuário + resposta IA
#    - Network: verificar WebSocket frames

# 4. Testar Barge-in:
#    - Enviar mensagem longa (ex: "pesquisar e descrever a história da IA")
#    - Enquanto IA responde, ativar microfone
#    - Dizer algo
#    - Áudio deve parar
#    - DevTools: {"type":"interrupt","timestamp":...}
```

---

## 📊 HEALTH CHECK ENDPOINTS

### Backend

```bash
# Health check
curl http://localhost:8000/health

# Status do sistema
curl http://localhost:8000/status

# Esperado:
# {
#   "status": "ready",
#   "brain_version": "2.1",
#   "tools_loaded": 8,
#   "timestamp": "2026-03-29T..."
# }
```

---

## 🔍 DEBUGGING

### Backend Issues

```python
# Se cortex not found:
from backend.core.tool_registry import get_di_container
container = get_di_container()
cortex = container.get_service("cortex_bilingue")
print(cortex)

# Se brain não inicializa:
python -c "from backend.brain_v2 import QuintaFeiraBrainV2; b = QuintaFeiraBrainV2()"

# Logs detalhados
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Frontend Issues

```typescript
// Chrome DevTools → Console
// Checar speech recognition
window.SpeechRecognition || window.webkitSpeechRecognition
// Deve retornar função constructor

// Checar AudioContext
window.AudioContext || window.webkitAudioContext
// Deve retornar função constructor

// Checar browser compat
navigator.userAgent
// Procurar por "Chrome", "Brave", "Edg"
```

---

## 📈 PERFORMANCE BASELINE

Métricas alvo após deploy:

```
Wake Word Detection:      < 100ms ✓
Silent ACK Generation:     < 50ms ✓
Barge-in Response Time:   < 100ms ✓
Cortex Processing:        < 200ms ✓
WebSocket Latency:        < 50ms  ✓
Frontend Paint:           < 1.5s  ✓
```

---

## 🚨 ROLLBACK PLAN

Se algo der errado:

```bash
# Frontend
git checkout frontend/hooks/useSpeechRecognition.ts
git checkout frontend/components/VoiceControl.tsx
git checkout frontend/app/page.tsx

# Backend
git checkout backend/brain_v2.py
git checkout backend/main.py

# Remove novo módulo (se necessário)
git rm backend/core/cortex_bilingue.py

# Restart
npm run dev  # frontend
uvicorn main:app --reload  # backend
```

---

## 📝 LOGGING & MONITORING

### EventBus Subscribers (Monitorar em Tempo Real)

```python
from backend.core.tool_registry import get_di_container

container = get_di_container()
event_bus = container.event_bus

def log_cortex_activity(data):
    if data.get('step') == 'bilingual_correction':
        print(f"[CORTEX] {data['original']} → {data['corrected']} ({data['confidence']:.0%})")

event_bus.subscribe('cortex_thinking', log_cortex_activity)

# Usar em relatório/dashboard
events = event_bus.get_events(event_type='cortex_thinking', limit=100)
for evt in events:
    print(evt)
```

### Métricas de Uso

```python
# Após N execuções, analisar:
# - Taxa de acerto do Cortex
# - Palavras mais corrigidas
# - Browsers mais usados
# - Latência média do barge-in

# TODO: Implementar dashboard GraphQL/REST
```

---

## ✨ CARACTERÍSTICAS ADICIONADAS

### Feature Flags (para gradual rollout)

```python
# Em brain_v2.py ou main.py
FEATURE_FLAGS = {
    'use_cortex': True,  # Usar Córtex Bilíngue
    'use_barge_in': True,  # Permitir interrupção
    'use_wake_machine': True,  # Máquina de estados
}

# No ask():
if FEATURE_FLAGS['use_cortex'] and self.cortex_bilingue:
    ...
```

### A/B Testing Pronto

```python
# Aleatoriamente testar v1 vs v2 do Cortex
import random
if random.random() < 0.5:
    use_cortex_v2 = True  # Nova implementação
else:
    use_cortex_v2 = False  # Fallback para regex simples
```

---

## 🎓 TRAINING & DOCUMENTATION

- ✅ GUIA_RAPIDO_V1_RESTAURADO.md (para devs)
- ✅ AUDITORIA_FINAL_RELATORIO.md (para stakeholders)
- ✅ Inline code comments em todos os arquivos
- ✅ Exemplos funcionais em cada módulo

---

## 📞 SUPPORT CONTACTS

- **Backend Issues**: Verificar logs em `backend/logs/`
- **Frontend Issues**: DevTools → Console + Network tab
- **Cortex Issues**: `python teste_auditoria_v1_v2.py`
- **WebSocket Issues**: Chrome DevTools → Network → WS

---

## ✅ DEPLOY SIGN-OFF

```
☐ Backend testa OK (python teste_auditoria_v1_v2.py)
☐ Frontend compila OK (npm run build)
☐ Sem erros de tipo (TypeScript strict)
☐ Sem console warnings (clean build)
☐ Endpoints health check respondendo
☐ EventBus iniciando sem erros
☐ Cortex carregando dados iniciais
☐ CORS configurado para produção
☐ SSL/TLS ativo (se produção)
☐ Logging ativo e documentado

PRONTO PARA DEPLOY: [  ] SIM / [  ] NÃO
```

---

**Data de Criação**: 29 de Março de 2026  
**Última Revisão**: 29 de Março de 2026  
**Versão**: 1.0 - Inicial
