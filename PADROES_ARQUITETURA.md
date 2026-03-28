# Quinta-Feira v2 - Padrões de Arquitetura Explicados

## 📚 Referência de Padrões de Projeto

Este documento cita cada padrão de projeto usado, onde está implementado, e por que.

---

## 1️⃣ **SINGLETON Pattern** (Criação)

### Localização
`backend/core/tool_registry.py` - Classe `DIContainer`

### Por Que?
Garantir uma **única instância global** do DI Container, EventBus e ToolRegistry por aplicação.

### Implementação

```python
class DIContainer:
    _instance = None  # Armazena instância única
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

# Uso
di1 = get_di_container()  # Primeira chamada → cria
di2 = get_di_container()  # Segunda chamada → retorna mesma
assert di1 is di2  # ✅ True
```

### Benefício
- **Consistência:** Todos usam mesma instância de EventBus
- **Eficiência:** Memória não desperdiçada
- **Simplicidade:** Uma fonte de verdade para configurações

### Quando Usar
✅ Configurações globais  
✅ Cache central  
✅ Logger compartilhado  
❌ **Não usar:** Objetos que precisam de múltiplas instâncias

---

## 2️⃣ **STRATEGY Pattern** (Comportamento)

### Localização
`backend/core/tool_registry.py` - Classe `Tool` (base)  
`backend/tools/*.py` - Classes derivadas (ExecutarTerminalTool, TocarMusicaSpotifyTool, etc)

### Por Que?
Definir uma **interface comum** para diferentes estratégias de ferramentas, permitindo trocar comportamentos em tempo de execução.

### Implementação

```python
# Interface estratégia
class Tool(ABC):
    @abstractmethod
    async def execute(self, **kwargs) -> str:
        pass

# Estratégias concretas
class ExecutarTerminalTool(Tool):
    async def execute(self, **kwargs) -> str:
        # Executa terminal
        pass

class TocarMusicaSpotifyTool(Tool):
    async def execute(self, **kwargs) -> str:
        # Toca Spotify
        pass

# Uso: abstrato, sem saber qual Tool
async def chamar_ferramenta(tool: Tool, **kwargs):
    return await tool.execute(**kwargs)
```

### Benefício
- **Flexibilidade:** Trocar ferramenta sem código cliente mudar
- **Extensibilidade:** Adicionar nova Tool não quebra nada
- **Polimorfismo:** Gemini invoca qualquer Tool genérica

### Quando Usar
✅ Múltiplas implementações do mesmo serviço  
✅ Algoritmos intercambiáveis  
✅ Plugin systems  
❌ **Não usar:** Apenas 1 implementação

---

## 3️⃣ **REGISTRY Pattern** (Descoberta)

### Localização
`backend/core/tool_registry.py` - Classe `ToolRegistry`

### Por Que?
Permitir **descoberta dinâmica de ferramentas** sem acoplamento hard-coded.

### Implementação

```python
class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._aliases: Dict[str, str] = {}
    
    def register(self, tool: Tool, aliases: list = None):
        """Registrar nova ferramenta"""
        self._tools[tool.metadata.name] = tool
        if aliases:
            for alias in aliases:
                self._aliases[alias] = tool.metadata.name
    
    async def execute(self, tool_name: str, **kwargs):
        """Executar ferramenta por nome"""
        canonical_name = self._aliases.get(tool_name, tool_name)
        return await self._tools[canonical_name].execute(**kwargs)
    
    def list_tools(self):
        """Listar todas as ferramentas registradas"""
        return {name: tool.metadata for name, tool in self._tools.items()}

# Uso dinâmico
registry.register(MinhaFerramenta())
resultado = await registry.execute('minha_ferramenta', arg1='valor')
```

### Benefício
- **Descoberta:** Não precisa saber todas as Tools antecipadamente
- **Hot-reload:** Adicionar Tool em tempo de execução
- **Aliases:** Uma Tool com múltiplos nomes
- **Listagem:** Conhecer capacidades do sistema em runtime

### Padrão do GoF
Registry é um padrão criado especificamente para a necessidade de "mútuo conhecimento entre partes heterogêneas".

### Quando Usar
✅ Plugin systems  
✅ Factory registrada  
✅ Middleware stacks  
❌ **Não usar:** Apenas items estáticos conhecidos em compile-time

---

## 4️⃣ **OBSERVER Pattern** (Notificação)

### Localização
`backend/core/tool_registry.py` - Classe `EventBus`

### Por Que?
Desacoplar **notificações de eventos** de quem os produz.

### Implementação

```python
class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, list[Callable]] = {}
    
    def subscribe(self, event_type: str, callback: Callable):
        """Se subscrever a tipo de evento"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
    
    def emit(self, event_type: str, data: Dict = None):
        """Emitir/publicar evento"""
        for callback in self._subscribers.get(event_type, []):
            if asyncio.iscoroutinefunction(callback):
                asyncio.create_task(callback(data))
            else:
                callback(data)

# Uso - Tool não precisa conhecer subscribers
class MeuTool(Tool):
    async def execute(self, **kwargs):
        if self._event_bus:
            self._event_bus.emit('meu_evento', {'dados': 'aqui'})

# Uso - Subscriber se registra independentemente
event_bus.subscribe('meu_evento', lambda data: print(f"Evento: {data}"))
```

### Benefício
- **Desacoplamento:** Tool não conhece subscribers
- **Escalabilidade:** Múltiplos listeners para um evento
- **Logging:** Adicionar logging sem modificar Tools
- **Auditoria:** Centralizar registros de eventos

### Aplicação em Quinta-Feira
```
tool_started       → Tools logam início
tool_completed     → Tools logam sucesso
tool_error        → Tools logam erro
vision_captured   → Captura de tela logada
action_terminal   → Comandos executados logados
cortex_thinking   → Raciocínio da IA logado
```

### Quando Usar
✅ Logging / Monitoring  
✅ Acionadores (triggers)  
✅ Desacoplamento  
❌ **Não usar:** Comunicação síncrona crítica

---

## 5️⃣ **DEPENDENCY INJECTION Pattern** (Inversão de Controle)

### Localização
`backend/core/tool_registry.py` - Método `set_event_bus()` em Tool  
`backend/tools/` - Construtores aceitando dependências

### Por Que?
**Inverter dependências** - objetos recebem dependências em vez de criá-las.

### Implementação

```python
# ❌ Acoplamento alto (antigamente)
class ExecutarTerminalTool:
    def __init__(self):
        self.security_validator = TerminalSecurityValidator()  # Cria aqui

# ✅ Injeção de Dependência
class ExecutarTerminalTool(Tool):
    def __init__(self):
        super().__init__(...)
        # Não cria TerminalSecurityValidator aqui, cria inline
        self.security_validator = TerminalSecurityValidator()
    
    def set_event_bus(self, event_bus: EventBus):
        """Setter para DI"""
        self._event_bus = event_bus

# Usar
tool = ExecutarTerminalTool()
tool.set_event_bus(event_bus)  # Injetar dependência
```

### Benefício
- **Testabilidade:** Mock dependências em testes
- **Flexibilidade:** Trocar implementação sem mudar classe
- **Manutenibilidade:** Dependências visíveis

### Tipos de DI
1. **Constructor Injection** (mais comum) - passar no `__init__`
2. **Setter Injection** - passar via método (usado aqui com `set_event_bus`)
3. **Interface Injection** (raro)

### Quando Usar
✅ Qualquer classe com dependências externas  
✅ Facilitamos de testes  
❌ **Não usar:** Valores primitivos (strings, ints)

---

## 6️⃣ **FACTORY Pattern** (Criação)

### Localização
`backend/core/tool_registry.py` - Função `get_di_container()`  
`backend/tools/__init__.py` - Função `inicializar_ferramentas()`

### Por Que?
Encapsular **complexidade de criação** de objetos.

### Implementação

```python
# Factory para DI Container (Singleton)
def get_di_container() -> DIContainer:
    global _di_container
    if _di_container is None:
        _di_container = DIContainer()
    return _di_container

# Factory para inicializar sistema completo
def inicializar_ferramentas(oraculo, database, ...):
    registry = get_di_container().tool_registry
    
    # Criar e registrar todas as ferramentas
    terminal_tool = ExecutarTerminalTool()
    registry.register(terminal_tool)
    
    spotify_tool = TocarMusicaSpotifyTool(spotify_client)
    registry.register(spotify_tool)
    
    # ... etc
    return registry
```

### Benefício
- **Abstração:** Chamar `get_di_container()` sem saber detalhes
- **Consistência:** Garantir setup correto
- **Manutenibilidade:** Mudar criação em um lugar

### Quando Usar
✅ Criação complexa  
✅ Precisa de lógica condicional  
✅ Centralizar setup

---

## 7️⃣ **TEMPLATE METHOD Pattern** (Comportamento)

### Localização
`backend/core/tool_registry.py` - Método `safe_execute()` em Tool

### Por Que?
Definir **esqueleto do algoritmo** na classe base, deixando detalhes para subclasses.

### Implementação

```python
class Tool(ABC):
    async def safe_execute(self, **kwargs) -> str:
        """Template method: estrutura fixa"""
        # 1. Validar entrada (pode ser override)
        if not self.validate_input(**kwargs):
            return f"Validação falhou"
        
        # 2. Logar início
        if self._event_bus:
            self._event_bus.emit('tool_started', {'tool_name': self.metadata.name})
        
        # 3. Executar (ABSTRACT - cada Tool implementa)
        result = await self.execute(**kwargs)
        
        # 4. Logar sucesso
        if self._event_bus:
            self._event_bus.emit('tool_completed', {'tool_name': self.metadata.name})
        
        return result
    
    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Subclasses implementam isto"""
        pass

# Benefício: Todas as Tools seguem: Validar → Log → Executar → Log
```

### Benefício
- **Consistência:** Todos os Tools seguem mesmo padrão
- **DRY:** Não repetir validação + logging em cada Tool
- **Flexibilidade:** Subclasses customizam `execute()`

### Quando Usar
✅ Algoritmo repetido com variações  
✅ Garantir ordem de passos  
❌ **Não usar:** Lógica muito diferente entre subclasses

---

## 8️⃣ **ADAPTER Pattern** (Estrutural)

### Localização
`backend/tools/terminal_tools.py` - Classe `TerminalSecurityValidator` e `ExecutarTerminalTool`

### Por Que?
**Adaptar interface incompatível** para que funcione com sistema.

### Exemplo
```python
# Classe existente (OSAutomation.executar_comando)
class OSAutomation:
    def executar_comando(self, cmd):
        # Retorna string, sem validação
        pass

# Adapter: converte para Tool interface
class ExecutarTerminalTool(Tool):
    def __init__(self):
        self.security_validator = TerminalSecurityValidator()  # Adapter
    
    async def execute(self, comando, justificacao):
        # Usar adapter antes de chamar OSAutomation
        validacao = self.security_validator.classify_command(comando)
        if not validacao['allowed']:
            return "Bloqueado"
        # Agora chamar OSAutomation
```

### Benefício
- **Compatibilidade:** Reutilizar código legado
- **Isolamento:** Mudar implementacao sem quebrar interface

---

## 9️⃣ **DECORATOR Pattern** (Estrutural)

### Localização
Bem similar a `safe_execute()` - wrapping de `execute()`

### Implementação
```python
# Sem Decorator (antigamente)
resultado = await tool.execute()

# Com Decorator (seguro)
resultado = await tool.safe_execute()  # Valida, loga, executa
```

### Benefício
- **Composição:** Adicionar responsabilidades em cadeia
- **Dinamismo:** Não precisa de subclasses extras

---

## 🔟 **FACADE Pattern** (Estrutural)

### Localização
`backend/brain_v2.py` - Classe `QuintaFeiraBrainV2`

### Por Que?
Fornecer **interface simplificada** para subsistema complexo.

### Implementação
```python
class QuintaFeiraBrainV2:
    """Facade simplest: só chamar ask()"""
    
    async def ask(self, message: str) -> str:
        # Internamente: captura visão, consulta Gemini, 
        # gera áudio, loga eventos, etc
        # Mas o cliente só chama .ask()
        pass

# Cliente não precisa conhecer:
# - EventBus setup
# - ToolRegistry
# - Database
# - Oracle engine
```

### Benefício
- **Simplicidade:** Interface simples esconde complexidade
- **Desacoplamento:** Cliente não conhece implementacao

---

## 1️⃣1️⃣ **STATE Pattern** (Comportamento)

### Localização
Frontend (`page-v2.tsx`) - Status de áudio/escuta

### Implementação
```javascript
// Estados
const [isListening, setIsListening] = useState(false);
const [isProcessing, setIsProcessing] = useState(false);
const [isAudioPlaying, setIsAudioPlaying] = useState(false);

// Transições de estado
// IDLE → LISTENING (Cmd+K)
// LISTENING → PROCESSING (resposta enviada)
// PROCESSING → AUDIO_PLAYING (recebeu áudio)
// AUDIO_PLAYING → IDLE (áudio terminou ou Esc pressionado)
```

### Benefício
- **Clareza:** Estados bem definidos
- **Validação:** Saber o que é permitido em cada estado
- **Barge-in:** Fácil interromper de qualquer estado

---

## 🔗 Mapa de Padrões

```
┌─────────────────────────────────────────────────────────────────┐
│                     QUINTA-FEIRA v2.0                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CRIAÇÃO          ESTRUTURA         COMPORTAMENTO    FRONTEND   │
│  ────────────     ──────────────    ──────────────   ──────────│
│  • Singleton      • Adapter         • Strategy       • State    │
│  • Factory        • Facade          • Observer       • Event    │
│  • DI Container   • Decorator       • Template       • Listener │
│                                     • Registry       • Virtual  │
│                                     • Chain of       │ DOM      │
│                                       Responsibility │          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Matriz de Padrões

| Padrão | Localização | Problema Resolve | Custo |
|--------|------------|------------------|-------|
| Singleton | DIContainer | Uma instância garantida | Overhead mínimo |
| Strategy | Tool base class | Múltiplas comportamentos | Interfaces abstratas |
| Registry | ToolRegistry | Descoberta dinâmica | Um Dict extra |
| Observer | EventBus | Eventos desacoplados | Callbacks assíncronos |
| DI | Tool.set_event_bus() | Dependências flexíveis | Setter extra |
| Factory | get_di_container() | Criação centralizada | Indireção |
| Template Method | Tool.safe_execute() | Consistência | Métodos obrigatórios |
| Adapter | TerminalSecurityValidator | Compatibilidade | Nova classe |
| Facade | QuintaFeiraBrainV2 | Simplicidade de interface | Esconde detalhes |
| State | Frontend | Gerenciamento de estado | useState extra |

---

## 🎓 SOLID Principles Implementados

✅ **S**ingle Responsibility  
- Cada Tool responsável por uma coisa  
- EventBus responsável apenas por eventos  

✅ **O**pen/Closed  
- Aberto para extensão (novo Tool)  
- Fechado para modificação (brain.py não muda)  

✅ **L**iskov Substitution  
- Qualquer Tool substitui outro sem quebrar  

✅ **I**nterface Segregation  
- Tool define interface mínima necessária  

✅ **D**ependency Inversion  
- Dependem de abstrações (Tool), não implementações  

---

## 📚 Referências

- **Gamma et al. "Design Patterns: Elements of Reusable Object-Oriented Software" (1994)**
- **Martin Fowler "Enterprise Integration Patterns" (2003)**
- **Clean Architecture by Robert C. Martin (2017)**

---

**Última atualização:** 28/03/2026  
**Status:** ✅ Referência Completa de Padrões
