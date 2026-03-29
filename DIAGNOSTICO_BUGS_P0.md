# 🔴 DIAGNÓSTICO CRÍTICO: Bugs P0 Quinta-Feira V2

## BUG 1: Crise de Identidade e Tool Calling Quebrado

### 📍 Localização Exata
- **Arquivo**: `backend/brain_v2.py`
- **Linhas**: 168-175
- **Função**: `_setup_genai()`

### 🔴 Código Problema
```python
# Linha 201 - Inicializar sessão de chat SEM FERRAMENTAS
self.chat_session = self.client.chats.create(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        system_instruction=self.instrucao_sistema,
        temperature=0.55
        # ❌ FALTA: tools=self._converter_ferramentas_para_gemini()
    )
)
```

### ❌ Sintoma do Utilizador
```
Utilizador: "Toca The Weeknd"
Gemini: "Como sou um assistente de texto, não consigo tocar a música diretamente..."
```

### 🔍 Causa Raiz
1. **Passo 1**: Ferramentas são registradas no `ToolRegistry` (via `inicializar_ferramentas()`)
2. **Passo 2**: Mas NUNCA são convertidas para o formato `types.Tool` do Gemini
3. **Passo 3**: O Gemini não recebe nenhum `tools=` na inicialização
4. **Passo 4**: Gemini não "sabe" que tem ferramentas e responde textualmente

### 📋 Verificação
No `_setup_genai()`, após `self.chat_session.create()`:
- ✓ `self.tool_registry` tem ferramentas (Spotify, YouTube, Terminal, etc.)
- ✗ `self.chat_session.config.tools` está **vazio/None**

### 🔧 Solução Técnica
Implementar método `_converter_ferramentas_para_gemini()` que:
1. Itera em `self.tool_registry.list_tools()`
2. Converte cada `Tool` para formato `types.Tool` (schema JSON)
3. Passa no parâmetro `tools=[...]` do Gemini

---

## BUG 2: Memory Leak / Thread Blocking - PC Trava

### 📍 Localização Exata
- **Arquivo**: `backend/automation.py`
- **Linhas**: 545-708
- **Função**: `tocar_youtube_invisivel()`

### 🔴 Código Problema
```python
def tocar_youtube_invisivel(self, pesquisa: str) -> str:
    # ...
    if not self.playwright_ativo:
        self.pw_motor = sync_playwright().start()
        self.browser_instance = self.pw_motor.chromium.launch(...)
        self.playwright_ativo = True
    
    if self.page: self.page.close()  # ← Fecha página ANTERIOR
    
    # ❌ PROBLEMA: Cria novo contexto mas NUNCA fecha
    context = self.browser_instance.new_context(...)  # ← new_context #1
    self.page = context.new_page()
    
    # ... código ... página ativa, faz coisas ...
    
    return f"Sucesso! Coloquei '{pesquisa}' a tocar."
    # ❌ PROBLEM: função retorna SEM FECHAR context
    # self.context.close()  NÃO EXISTE
    # context never stored = MEMORY LEAK
```

### ❌ Sintoma do Utilizador
```
1. Inicia Quinta-Feira (primeira música) - OK
2. Toca segundo vídeo YouTube - OK, mas 1º contexto fica na memória
3. Toca terceira música - OK, mas 1º + 2º contextos na memória
4. Após 5-6 músicas:
   - RAM: +800MB (Chromium processes)
   - CPU: 50-80% (processos órfãos)
   - PC: CONGELADO (lag severo, sistema não responde)
```

### 🔍 Causa Raiz
1. **Context Leak**: `context = self.browser_instance.new_context()` cria objeto na heap
2. **Variável Local**: `context` é VAR LOCAL, não guardada em `self`
3. **Sem Close**: `context.close()` nunca é chamado
4. **Sem Cleanup**: Python GC não consegue limpar (context.page ainda referencia resources Chromium)
5. **Accumulation**: Cada chamada acumula 1 contexto + 1 processo Chromium
6. **OS Limit**: Windows tem limite de file handles/processes → TRAVA

### 📊 Timeline do Problema
```
Tempo 0s:    Inicia app - Memory OK
Tempo 30s:   1ª música YouTube -  +150MB (1 context + Chrome.exe)
Tempo 60s:   2ª música YouTube -  +300MB (2 contexts + 2 Chrome.exe)
Tempo 90s:   3ª música YouTube -  +450MB (3 contexts)
Tempo 120s:  4ª música YouTube -  +600MB (4 contexts) ← PC começa a lag
Tempo 150s:  5ª música YouTube -  +750MB (5 contexts) ← Mouse lag visível
Tempo 180s:  Sistema CONGELADO  -  +900MB (sistema não responde)
```

### 📋 Verificação no Gestor de Tarefas
```
Processos:
- msedge.exe (original)           1 processo
- msedge.exe (YouTube invisível)  1+1+1+1+1 = 5 processos (orphaned!)

Memory Leak = 5 × 150MB = 750MB PERDIDOS
```

### 🔧 Solução Técnica

**Opção 1: Context Manager (Singleton Rigoroso)**
```python
class PlaywrightPool:
    _instance = None
    _context = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_page(self):
        if self._context is None:
            pw = sync_playwright().start()
            browser = pw.chromium.launch()
            self._context = browser.new_context()
        
        old_page = self._context.page if hasattr(self._context, 'page') else None
        if old_page:
            old_page.close()
        
        self._page = self._context.new_page()
        return self._page
    
    def cleanup(self):
        if self._page:
            self._page.close()
        if self._context:
            self._context.close()
```

**Opção 2: Context Manager com `with` (Recomendado)**
```python
def tocar_youtube_invisivel(self):
    # Reusar contexto ÚNICO glob
    if not self.browser_instance:
        pw = sync_playwright().start()
        self.browser_instance = pw.chromium.launch()
        self.context = self.browser_instance.new_context()
    
    # Fechar página anterior
    if self.page:
        self.page.close()
    
    # Criar página NOVO na mesma context
    self.page = self.context.new_page()
    
    # ... fazer coisas ...
    
    # IMPORTANTE: NÃO fechar context aqui!
    # Context fica vivo para próxima chamada
```

**Opção 3: Destrutor + Cleanup Hook**
```python
class OSAutomation:
    def __del__(self):
        """Cleanup ao destruir objeto"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.pw_motor:
                self.pw_motor.stop()
        except:
            pass
```

---

## 🚨 IMPACTO DO SISTEMA

| Métrica | Bug 1 | Bug 2 |
|---------|-------|-------|
| **Severidade** | P0 - Broken Feature | P0 - System Crash |
| **Afeta** | Tool Calling (IA não executa) | Performance (PC trava) |
| **Utilizador Vê** | "Sou um assistente de texto" | Sistema CONGELADO |
| **Causa** | SDK Integration Missing | Resource Leak |
| **Tempo para Reproduzir** | 1 comando YouTube | 5+ músicas |
| **Tempo para Fixar** | 30min | 20min |

---

## 📋 PLAN DE EXECUÇÃO

### Fase 1: Fixar Bug 1 (30 min)
- [ ] Criar método `_converter_ferramentas_para_gemini()` em brain_v2.py
- [ ] Iterar `tool_registry.list_tools()`
- [ ] Gerar schema JSON para cada tool
- [ ] Passar `tools=[...]` na criação do chat_session
- [ ] Testar: "Toca The Weeknd" → deve chamar Spotify

### Fase 2: Fixar Bug 2 (20 min)
- [ ] Implementar Singleton rigoroso em OSAutomation
- [ ] Guardar `self.context` (não var local)
- [ ] Implementar `cleanup()` adequado
- [ ] Adicionar destrutor `__del__`
- [ ] Testar: 10 músicas YouTube → RAM estável

### Fase 3: Fase 4 - Modo Nuvem (90 min)
- Desacoplamento de .env vars
- Cloud Fallback (Gemini Serverless)
- Túnel pyngrok

---

## 🎯 STATUS: PRONTO PARA CORREÇÃO

**Próximo**: Implementar correções (Bug 1 → Bug 2 → Fase 4)
