# Quinta-Feira v2 - Guia Rápido de Implementação

## ⚡ 5 Minutos para Começar

### 1. Setup Backend

```bash
# Windows PowerShell
cd c:\Users\mathe\Documents\assistente-ai\backend

# Criar venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt

# Configurar .env (copiar e preencher)
cp .env.example .env
# GEMINI_API_KEY=sk-...
# ELEVENLABS_API_KEY=sk-...
# Etc.
```

### 2. Iniciar Servidor

```bash
# Backend FastAPI
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2: Frontend Next.js
cd ..\frontend
npm run dev

# Abrir browser em http://localhost:3000
```

### 3. Teste Básico

```bash
# Terminal 3: Testar API
python teste_api.py
# ou
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{"message": "Olá"}'
```

---

## 🔧 Alterações Principais (v1 → v2)

| Aspecto | v1 | v2 |
|--------|----|----|
| Arquitetura | Monolítico (funções soltas) | Modular (Tool Registry + DI) |
| Ferramentas | Em `brain.py` | Em `tools/*.py` (plugáveis) |
| Dependências | Globais (singleton de `automacao`) | Injetadas via DI Container |
| Logs | Prints (sem estrutura) | EventBus (Córtex/Visão/Ação) |
| Segurança Terminal | Regex básico | Padrões aprimorados (+14 regras) |
| Visão | Sem compressão | WebP + Redimensionamento automático |
| Frontend | Barge-in básico | Barge-in com Cmd+K e Esc |
| Performance | Síncrono | Async/Await com asyncio |

---

## 📋 Checklist de Migração (se vinhas de v1)

- [ ] Atualizar imports em `main.py`: `from brain_v2 import QuintaFeiraBrain`
- [ ] Remover código antigo: `brain.py` pode ser descontinuado
- [ ] Testar modo **trusted-local** (QUINTA_SECURITY_PROFILE)
- [ ] Verificar ElevenLabs API key (áudio)
- [ ] Ativar logs táticos: `event_bus.get_events()`
- [ ] Frontend: substituir `page.tsx` por `page-v2.tsx` (ou copiar barge-in)

---

## 🎯 Padrões de Uso Comuns

### ✅ Excecutar Ferramenta Manualmente

```python
from backend.core import get_di_container

di = get_di_container()
registry = di.tool_registry

# Executar terminal tool
resultado = await registry.execute('terminal', 
    comando='Get-Process',
    justificacao='Listar processos ativos'
)
print(resultado)
```

### ✅ Subscrever a Logs

```python
from backend.core import get_di_container

di = get_di_container()
event_bus = di.event_bus

def log_acao(data):
    print(f"[AÇÃO] {data}")

event_bus.subscribe('action_terminal', log_acao)
# Agora todos os comandos serão logados
```

### ✅ Adicionar Ferramenta Customizada

```python
# 1. Criar classe em backend/tools/minha_tool.py
class MinhaFerramenta(Tool):
    async def execute(self, **kwargs) -> str:
        return "Resultado"

# 2. Registrar em inicializar_ferramentas()
from backend.tools.minha_tool import MinhaFerramenta
minha_tool = MinhaFerramenta()
registry.register(minha_tool, aliases=['alias1', 'alias2'])

# 3. Pronto! Gemini pode invocar automaticamente
```

---

## 🐛 Debug Comum

### Problema: "Tool não aparece"
```python
# Verificar
registry = get_di_container().tool_registry
print(registry.list_tools())
```

### Problema: "EventBus não emite"
```python
# Garantir que EventBus foi injetado
tool = registry.get_tool('minha_tool')
tool.set_event_bus(get_di_container().event_bus)
```

### Problema: "Áudio travado"
```javascript
// Frontend: Verificar console do navegador
console.log(isAudioPlaying)  // deve ser false após reprodução
// Clicar "PARAR" ou pressionar Esc
```

---

## 🚀 Deploy em Produção

### Backend (Windows Server via Task Scheduler)

```powershell
# Script: scripts/start_quinta_feira.ps1
$env:QUINTA_SECURITY_PROFILE = "strict"
$env:APP_ENV = "production"
$env:ENABLE_LONG_TERM_MEMORY = "false"

cd "C:\Users\mathe\Documents\assistente-ai\backend"
.\.venv\Scripts\Activate.ps1
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Frontend (Vercel/Netlify)

```bash
npm run build
npm start
# ou fazer deploy em https://vercel.com
```

### Variáveis de Ambiente (Produção)

```env
# Backend
APP_ENV=production
QUINTA_SECURITY_PROFILE=strict
ENABLE_LONG_TERM_MEMORY=false
GEMINI_API_KEY=***
ELEVENLABS_API_KEY=***
SPOTIFY_CLIENT_ID=***
SPOTIFY_CLIENT_SECRET=***

# Frontend
NEXT_PUBLIC_WS_URL=wss://seu-servidor.com/ws
NEXT_PUBLIC_ALLOWED_ORIGINS=https://seu-dominio.com
```

---

## 📈 Monitoramento

### Console de Logs em Tempo Real

```python
# Criar endpoint HTTP para visualizar logs
from fastapi import FastAPI

@app.get("/logs/events")
async def get_logs():
    event_bus = get_di_container().event_bus
    return event_bus.get_events(limit=100)

# Acessar em http://localhost:8000/logs/events
```

### Métricas

```python
# Contar invocações de ferramenta
events = event_bus.get_events('tool_completed', limit=1000)
tools_count = {}
for evt in events:
    tool = evt['data'].get('tool_name')
    tools_count[tool] = tools_count.get(tool, 0) + 1

print(tools_count)
# {'terminal': 45, 'spotify': 12, 'youtube': 8, ...}
```

---

## 🔐 Segurança Checklist

- [ ] GEMINI_API_KEY está em `.env` (nunca em git)
- [ ] `.env` está em `.gitignore`
- [ ] CORS está restrito em produção (`ALLOWED_ORIGINS`)
- [ ] Modo strict em produção (`QUINTA_SECURITY_PROFILE=strict`)
- [ ] Memória desativada em produção (`ENABLE_LONG_TERM_MEMORY=false`)
- [ ] Logs não expõem segredos
- [ ] Terminal tool valida todos os comandos

---

## 📞 Suporte

Se encontrar problemas:

1. Verificar logs: `event_bus.get_events()`
2. Testar ferramenta isoladamente
3. Verificar .env configurado
4. Executar: `python teste_api.py`
5. Abrir issue no GitHub com contexto completo

---

**Versão:** 2.0.0 Quick Start  
**Última atualização:** Março 2026
