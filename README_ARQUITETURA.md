# Quinta-Feira v2 - Arquitetura Refatorada

## 📋 Visão Geral

Quinta-Feira é um assistente virtual pessoal baseado em **arquitetura modular com injeção de dependência**, permitindo adicionar novas ferramentas sem modificar o núcleo do sistema.

### Principais Melhorias (v2)

✅ **Tool Registry Pattern** - Ferramentas plugáveis  
✅ **Dependency Injection Container** - Gerenciamento de dependências  
✅ **Event Bus (Observer)** - Logs táticos (Córtex, Visão, Ação)  
✅ **Segurança Aprimorada** - Regex para padrões destrutivos  
✅ **Compressão de Imagem** - WebP + redimensionamento automático  
✅ **Barge-in Melhorado** - Interrupção instantânea de áudio  
✅ **Async/Await** - Performance em asyncio  

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────┐
│         FastAPI WebSocket Server        │
│         (main.py: /ws endpoint)         │
└──────────────────┬──────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
   ┌────────────┐      ┌──────────────┐
   │ QuintaFeira│      │  DI Container│
   │  BrainV2  │◄─────►│ (Singleton)  │
   └─┬──────────┘      └──────────────┘
     │                        │
     ├────────────┬───────────┤
     │            │           │
     ▼            ▼           ▼
┌─────────┐ ┌──────────┐ ┌────────────┐
│Gemini   │ │EventBus  │ │ToolRegistry│
│(LLM)    │ │(Logs)    │ │(Strategies)│
└─────────┘ └──────────┘ └────────────┘
                              │
                ┌─────────────┴──────────────┐
                │                            │
                ▼                            ▼
         ┌────────────────────┐    ┌────────────────────┐
         │Terminal Tools      │    │Media Tools         │
         │- Exec PowerShell   │    │- Spotify Play      │
         │- Learn + Execute   │    │- YouTube Play      │
         │- Security Validate │    │- Media Control     │
         └────────────────────┘    │- Open/Search       │
                                   └────────────────────┘
                │                            │
                ▼                            ▼
         ┌────────────────────┐    ┌────────────────────┐
         │Vision Tools        │    │Memory Tools        │
         │- Capture Screen    │    │- Save Memory       │
         │- Compress (WebP)   │    │- Search Memory     │
         │- Analyze (Gemini)  │    │- Resolve Target    │
         └────────────────────┘    └────────────────────┘
```

---

## 📦 Estrutura de Pastas

```
backend/
├── core/
│   ├── __init__.py
│   └── tool_registry.py          # DI Container, Tool base, EventBus, Registry
├── tools/
│   ├── __init__.py               # inicializar_ferramentas()
│   ├── terminal_tools.py         # ExecutarTerminalTool, AprenderemExecutarTool
│   ├── media_tools.py            # Spotify, YouTube, Media Control, Open/Search
│   ├── vision_tools.py           # Capturar, Comprimir, Analisar com Gemini
│   └── memory_tools.py           # Guardar, Buscar, Resolver com aprendizado
├── brain_v2.py                   # QuintaFeiraBrainV2 (refatorado)
├── automation.py                 # OSAutomation (mantém compatibilidade)
├── database.py                   # BaseDadosMemoria (SQLite)
├── oracle.py                     # OraculoEngine (Gemini)
├── main.py                       # FastAPI WebSocket
└── requirements.txt              # Python dependencies
```

---

## 🔌 Como Adicionar Novas Ferramentas

### 1️⃣ Criar Classe Tool

```python
# backend/tools/notion_tools.py
import asyncio
from backend.core import Tool, ToolMetadata

class CriarNotionPageTool(Tool):
    """Ferramenta para criar páginas no Notion."""
    
    def __init__(self, notion_client=None):
        super().__init__(
            metadata=ToolMetadata(
                name="notion_create",
                description="Cria página no Notion com título e conteúdo",
                version="1.0.0",
                tags=["productivity", "notion"]
            )
        )
        self.notion_client = notion_client
    
    def validate_input(self, **kwargs) -> bool:
        return 'titulo' in kwargs and 'conteudo' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Args:
            titulo (str): Título da página
            conteudo (str): Conteúdo
            database_id (str): ID do Notion Database
        
        Returns:
            str: URL da página criada ou erro
        """
        titulo = kwargs.get('titulo', '')
        conteudo = kwargs.get('conteudo', '')
        database_id = kwargs.get('database_id', '')
        
        try:
            # Sua lógica aqui
            page = await asyncio.to_thread(
                self.notion_client.databases.query,
                **{'database_id': database_id}
            )
            
            if self._event_bus:
                self._event_bus.emit('tool_completed', {
                    'tool_name': 'notion_create',
                    'result': f"Página '{titulo}' criada"
                })
            
            return f"✓ Página criada: {titulo}"
            
        except Exception as e:
            return f"[ERRO Notion] {str(e)}"
```

### 2️⃣ Registrar no Inicializador

```python
# backend/tools/__init__.py (adicionar ao fim)

def inicializar_ferramentas(...):
    # ... code existente ...
    
    # Nova ferramenta
    from backend.tools.notion_tools import CriarNotionPageTool
    
    notion_client = criar_cliente_notion()  # sua função
    notion_tool = CriarNotionPageTool(notion_client)
    registry.register(notion_tool, aliases=['notion', 'create_page'])
```

### 3️⃣ Brain usa automaticamente

A ferramenta aparece no `tool_registry.list_tools()` e o Gemini pode invocá-la via tool calling!

---

## 📊 Sistema de Logs Táticos (EventBus)

### Eventos Disponívels

```python
# Subscrever a eventos
event_bus = get_di_container().event_bus

# Evento: Ferramenta iniciada
event_bus.subscribe('tool_started', lambda data: print(f"Tool: {data['tool_name']}"))

# Evento: Ferramenta completada
event_bus.subscribe('tool_completed', callback)

# Evento: Erro em ferramenta
event_bus.subscribe('tool_error', callback)

# Evento: Captura de visão
event_bus.subscribe('vision_captured', callback)

# Evento: Ação no terminal
event_bus.subscribe('action_terminal', callback)

# Evento: Pensamento do córtex (LLM reasoning)
event_bus.subscribe('cortex_thinking', callback)
```

### Emitir Eventos (dentro de Tool)

```python
class MinhaFerramenta(Tool):
    async def execute(self, **kwargs) -> str:
        if self._event_bus:
            # Emitir evento
            self._event_bus.emit('cortex_thinking', {
                'step': 'meu_passo',
                'reasoning': 'Explicação do que estou pensando'
            })
        
        # ... lógica ...
        
        if self._event_bus:
            self._event_bus.emit('tool_completed', {
                'tool_name': 'minha_ferramenta',
                'result': 'Sucesso!'
            })
```

### Console para Debugging

```python
# Obter eventos do buffer
event_bus = get_di_container().event_bus
eventos = event_bus.get_events(event_type='tool_completed', limit=50)
for evt in eventos:
    print(f"{evt['type']}: {evt['data']}")
```

---

## 🔒 Segurança do Terminal

A ferramenta `ExecutarTerminalTool` usa `TerminalSecurityValidator` com 3 níveis de risco:

### **CRITICAL** ❌
- `format C:` - Destruição de disco
- `delete shadow copies` - Limpeza de evidências
- `rm -rf /` - Apagamento recursivo
- Bypass de UAC/privilégios

### **MEDIUM** ⚠️
Requer confirmação em modo `strict`:
- `del /s /f` - Apagamento com flags
- `install service` - Instalação de serviço

### **LOW** ✓
Apenas logging:
- `whoami` - Verificação de usuário

```python
# Validação customizada
security_validator = TerminalSecurityValidator(security_profile="trusted-local")
validacao = security_validator.classify_command("rm -rf /home/user/docs")
print(validacao['risco'])  # "CRÍTICO"
print(validacao['reason'])  # "Apagamento recursivo"
```

---

## 🖼️ Otimização de Visão

### Compressão Automática

```
Original:   1920x1080 PNG  = ~3MB
↓ (Redimensiona se > 1280px)
↓ (Converte para WebP com qualidade 70)
↓
Comprimida: 1280x720 WebP  = ~150KB

Economia: 95% de redução!
```

**Variáveis de ambiente:**
```bash
VISION_COMPRESSION_QUALITY=70      # 1-100 (default 70)
VISION_MAX_DIMENSION=1280          # pixels (default 1280)
```

### Detecção de Monitor em Foco

```python
from backend.tools.vision_tools import CapturarVisaoTool

capture_tool = CapturarVisaoTool()
screenshot_base64 = await capture_tool.safe_execute()

# EventBus emite:
{
    'monitor_index': 0,
    'monitor_dims': (0, 0, 1920, 1080),
    'compression_ratio': 20.5,  # Quanto foi reduzido
    'quality': 70
}
```

---

## 🎤 Barge-in (Interrupção de Áudio)

### Frontend Melhorado

Arquivo: `frontend/app/page-v2.tsx`

**Features:**
- `Cmd+K` ou `Ctrl+K`: Ativar microfone (interrompe áudio da IA)
- `Esc`: Parar áudio em andamento
- `Enter`: Enviar mensagem
- Visual feedback: 🔊 (áudio), 🎤 (escutando), ⏳ (processando)

**BARGE-IN em Ação:**

```javascript
// Quando usuário começa a falar
recognition.onstart = () => {
  // *** Interromper áudio em andamento ***
  interromperAudio();  // Pausa + limpa buffer
  setIsListening(true);
};
```

---

## ⚡ Performance & Asyncio

### Padrões Usados

1. **asyncio.to_thread()** para I/O bloqueante
```python
resultado = await asyncio.to_thread(funcao_sync, argumentos)
```

2. **Criar tasks sem aguardar** para EventBus
```python
if asyncio.iscoroutinefunction(callback):
    asyncio.create_task(callback(data))  # Fire and forget
```

3. **Timeouts** em operações longas
```python
resultado = await asyncio.wait_for(
    my_async_func(),
    timeout=30  # Segundos
)
```

---

## 📝 Exemplo Completo: Adicionar Calendario

### Passo 1: Tool Class

```python
# backend/tools/calendar_tools.py
from backend.core import Tool, ToolMetadata
import asyncio

class AdicionarEventoCalendarioTool(Tool):
    def __init__(self, calendar_client=None):
        super().__init__(
            metadata=ToolMetadata(
                name="calendar_add",
                description="Adiciona evento ao calendário",
                version="1.0.0",
                tags=["productivity", "calendar"]
            )
        )
        self.calendar_client = calendar_client
    
    def validate_input(self, **kwargs) -> bool:
        return 'evento' in kwargs and 'data' in kwargs
    
    async def execute(self, **kwargs) -> str:
        evento = kwargs.get('evento')
        data = kwargs.get('data')
        
        if self._event_bus:
            self._event_bus.emit('cortex_thinking', {
                'step': 'adding_calendar_event',
                'event': evento,
                'date': data
            })
        
        try:
            await asyncio.to_thread(
                self.calendar_client.events.insert,
                calendarId='primary',
                body={'summary': evento, 'start': {'dateTime': data}}
            )
            
            return f"✓ Evento '{evento}' adicionado em {data}"
        
        except Exception as e:
            return f"[ERRO Calendário] {str(e)}"
```

### Passo 2: Registrar

```python
# backend/tools/__init__.py
def inicializar_ferramentas(..., calendar_client=None, ...):
    # ...
    calendar_tool = AdicionarEventoCalendarioTool(calendar_client)
    registry.register(calendar_tool, aliases=['calendar', 'add_event'])
```

### Passo 3: Usar no Frontend

Usuário diz: "Agenda uma reunião com Python amanhã às 10"
→ Gemini invoca ferramenta → Calendário atualizado!

---

## 🚀 Starting the System

### Backend
```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate  # Windows PowerShell
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # http://localhost:3000
```

---

## 📚 Referências Padrões

| Padrão | Arquivo | Uso |
|--------|---------|-----|
| **Strategy** | `core/tool_registry.py` | Cada Tool é uma Strategy |
| **Observer** | `core/tool_registry.py` | EventBus implementa Observer |
| **Singleton** | `DIContainer` | Uma instância global por app |
| **Dependency Injection** | `core/`, `tools/` | Injetar dependências nas Tools |
| **Registry** | `ToolRegistry` | Registrar/descobrir Tools dinamicamente |
| **Factory** | `get_di_container()` | Criar DI Container único |

---

## 🐛 Troubleshooting

### "Ferramenta não encontrada"
```
Verificar: registry.list_tools()
Se vazia, chamar inicializar_ferramentas() com todas as dependências
```

### "EventBus não recebe eventos"
```
Certifique-se de:
1. tool.set_event_bus(event_bus) foi chamado
2. Subscrição foi feita antes de emitir
3. Callback é assíncrono? Use asyncio.create_task()
```

### "Áudio não toca no frontend"
```
Verificar:
1. ElevenLabs API key configurada?
2. Fallback para pyttsx3 funciona?
3. Base64 está válido?
4. CORS permite acesso?
```

---

## 📖 Próximos Passos

- [ ] Adicionar suporte a plugins em tempo de execução (hot-reload)
- [ ] Dashboard de logs táticos em tempo real
- [ ] Testes unitários para cada Tool
- [ ] Documentação de API OpenAPI expandida
- [ ] Suporte a múltiplos LLMs (Claude, OpenAI, etc)
- [ ] Persistência de EventBus em arquivo/DB

---

**Versão:** 2.0.0  
**Última atualização:** Março 2026  
**Arquiteto:** Matheus + Quinta-Feira AI  
