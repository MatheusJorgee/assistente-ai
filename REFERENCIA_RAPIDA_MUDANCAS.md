# 🎯 REFERÊNCIA RÁPIDA - Mudanças Exatas por Arquivo

## 1. backend/brain_v2.py

### Mudança 1: System Prompt Agressivo (linhas ~165-195)

**Arquivo**: `backend/brain_v2.py`
**Método**: `_setup_genai()`
**Antes (INEFICAZ)**:
```python
DOUTRINA INQUEBRÁVEL - FERRAMENTAS DISPONÍVEIS
Se você tem uma ferramenta para fazer algo, NUNCA diga que não pode fazer.
- Não diga "Como sou um assistente de texto, não consigo..."
- Não diga "Não tenho acesso para..."
- Não diga "Desculpe, mas não posso..."
REGRA: Se está na lista de ferramentas, EXECUTE SILENCIOSAMENTE.
```

**Depois (AGRESSIVO)** ✅:
```python
🚨 DOUTRINA INQUEBRÁVEL - FERRAMENTAS (ENFORCE AGRESSIVAMENTE)
REGRA ABSOLUTA: Se você tem uma ferramenta para fazer algo, EXECUTE-A IMEDIATAMENTE.
NÃO EXPLIQUE O QUE PODES FAZER. SÓ FAZ.

PROIBIÇÕES ABSOLUTAS:
✗ "Como assistente de texto, não consigo..."
✗ "Como uma IA, não tenho acesso..."
✗ "Desculpe, mas não posso..."
✗ "Não tenho a capacidade de..."

SUBSTITUIÇÃO OBRIGATÓRIA:
- Pedir música → Toca IMEDIATAMENTE via Spotify/YouTube (não diga "posso tocar")
- Pedir screenshot → Captura IMEDIATAMENTE
- Pedir automação → Executa IMEDIATAMENTE (se for seguro)
- Pedir busca → Executa IMEDIATAMENTE

REGRA: Qualquer negação é FALSA. Se está na lista de ferramentas, tem capacidade.
```

---

### Mudança 2: Loop de Tool Calling (linhas ~488-650)

**Arquivo**: `backend/brain_v2.py`
**Método**: `async def ask(self, message: str)`

**Antes (NÃO TRATA FUNCTION_CALLS)**:
```python
response = await asyncio.to_thread(
    self.chat_session.send_message,
    pacote_envio,
    types.GenerateContentConfig(temperature=temperatura)
)

texto_resposta = response.text  # ← PROBLEMA: ignora function_calls!
```

**Depois (TRATA FUNCTION_CALLS)** ✅:
```python
# ===== LOOP TOOL CALLING (ReAct Pattern) =====
historico_conversas = []
texto_resposta = ""
max_tool_iterations = 5
iteration = 0

while iteration < max_tool_iterations:
    iteration += 1
    
    # Enviar para Gemini (primeira vez: pacote_envio, depois: histórico)
    if iteration == 1:
        envio_atual = pacote_envio
    else:
        envio_atual = historico_conversas
    
    response = await asyncio.to_thread(
        self.chat_session.send_message,
        envio_atual,
        types.GenerateContentConfig(temperature=temperatura)
    )
    
    self.event_bus.emit('cortex_thinking', {
        'step': f'gemini_iteration_{iteration}',
        'has_function_calls': bool(response.function_calls)
    })
    
    # ✓ CRÍTICO: Verificar se há function calls na resposta
    if hasattr(response, 'function_calls') and response.function_calls:
        # Processar cada function call
        for fn_call in response.function_calls:
            fn_name = getattr(fn_call, 'name', 'unknown')
            fn_args = getattr(fn_call, 'args', {})
            
            self.event_bus.emit('cortex_thinking', {
                'step': 'executing_tool',
                'tool_name': fn_name,
                'iteration': iteration
            })
            
            try:
                # Obter ferramenta do registry
                tool = self.tool_registry.get_tool(fn_name)
                if tool:
                    # Executar com await se for async
                    if asyncio.iscoroutinefunction(tool.execute):
                        tool_result = await tool.execute(**fn_args)
                    else:
                        tool_result = await asyncio.to_thread(tool.execute, **fn_args)
                    
                    self.event_bus.emit('tool_completed', {
                        'tool_name': fn_name,
                        'result': str(tool_result)[:100]
                    })
                    
                    # Adicionar ao histórico para continuar conversa
                    historico_conversas.append({
                        "role": "model",
                        "parts": [{"functionCall": {
                            "name": fn_name,
                            "args": fn_args if isinstance(fn_args, dict) else {}
                        }}]
                    })
                    
                    historico_conversas.append({
                        "role": "user",
                        "parts": [{"functionResponse": {
                            "name": fn_name,
                            "response": {
                                "result": str(tool_result),
                                "success": True
                            }
                        }}]
                    })
                else:
                    # Ferramenta não encontrada
                    self.event_bus.emit('tool_error', {
                        'tool_name': fn_name,
                        'error': f'Ferramenta "{fn_name}" não registrada'
                    })
                    
                    historico_conversas.append({
                        "role": "model",
                        "parts": [{"functionCall": {
                            "name": fn_name,
                            "args": fn_args if isinstance(fn_args, dict) else {}
                        }}]
                    })
                    
                    historico_conversas.append({
                        "role": "user",
                        "parts": [{"functionResponse": {
                            "name": fn_name,
                            "response": {
                                "error": f'Ferramenta não registrada',
                                "success": False
                            }
                        }}]
                    })
            
            except Exception as e:
                self.event_bus.emit('tool_error', {
                    'tool_name': fn_name,
                    'error': str(e)
                })
                
                historico_conversas.append({
                    "role": "model",
                    "parts": [{"functionCall": {
                        "name": fn_name,
                        "args": fn_args if isinstance(fn_args, dict) else {}
                    }}]
                })
                
                historico_conversas.append({
                    "role": "user",
                    "parts": [{"functionResponse": {
                        "name": fn_name,
                        "response": {
                            "error": str(e),
                            "success": False
                        }
                    }}]
                })
        
        # Continuar loop para processar próxima resposta do Gemini
    
    else:
        # Sem function calls, temos texto final
        texto_resposta = response.text if hasattr(response, 'text') else ""
        break

# Se saiu do loop sem texto, tenta último texto disponível
if not texto_resposta and hasattr(response, 'text'):
    texto_resposta = response.text
```

---

## 2. backend/automation.py

### Mudança 1: Adicionar Import asyncio (linha 1)

**Antes**:
```python
import pyautogui
import subprocess
import os
...
from playwright.sync_api import sync_playwright
```

**Depois** ✅:
```python
import pyautogui
import subprocess
import os
...
import asyncio  # ← NOVO
import spotipy
...
from playwright.sync_api import sync_playwright
```

---

### Mudança 2: Adicionar Métodos Async (final do arquivo, ~850-950)

**Novo Método Crítico**:
```python
async def async_tocar_youtube_invisivel(self, pesquisa: str) -> str:
    """
    Versão ASYNC do YouTube que não bloqueia o FastAPI event loop.
    Usa async_playwright em vez de sync_playwright().
    
    CRÍTICO: Esta função deve ser chamada APENAS com await em contexto async.
    """
    print(f">>> [YOUTUBE ASYNC] A preparar motor web para: '{pesquisa}'...")
    
    try:
        # ✓ Importar async_playwright (NÃO bloqueia!)
        from playwright.async_api import async_playwright
        
        # Resolver a URL do vídeo
        video_resolvido = self._resolver_video_youtube(pesquisa)
        query_url = urllib.parse.quote(pesquisa)
        
        # ✓ Inicializar async_playwright
        async with await async_playwright() as p:
            # Lançar browser
            browser = await p.chromium.launch(
                headless=False,
                channel="msedge",
                args=[
                    "--autoplay-policy=no-user-gesture-required",
                    "--window-position=-32000,-32000",
                    "--window-size=800,600",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            # Criar contexto
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            
            # Criar página
            page = await context.new_page()
            
            # Injetar script anti-bot
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Navegar para o vídeo
            if video_resolvido and video_resolvido.get("id"):
                print(f">>> [YOUTUBE ASYNC] Navegando para: {video_resolvido['id']}")
                await page.goto(f"https://www.youtube.com/watch?v={video_resolvido['id']}", timeout=30000)
            else:
                print(f">>> [YOUTUBE ASYNC] Procurando: {pesquisa}")
                await page.goto(f"https://www.youtube.com/results?search_query={query_url}", timeout=30000)
                await page.wait_for_selector("a#video-title", timeout=10000)
                await page.click("a#video-title")
            
            # Aguardar player
            print(">>> [YOUTUBE ASYNC] Aguardando player...")
            await page.wait_for_selector("video", timeout=15000)
            await asyncio.sleep(2)  # ← asyncio.sleep, NÃO time.sleep()
            
            # Injetar código de controle de volume
            codigo_magico = f"""
            (() => {{
                const DEFAULT_VOLUME = {self.youtube_default_volume};
                if (typeof window.__assistentePreferredVolume !== 'number') {{
                    window.__assistentePreferredVolume = DEFAULT_VOLUME;
                }}
                const v = document.querySelector('video');
                if(v) {{
                    v.muted = false;
                    v.volume = DEFAULT_VOLUME;
                    if(v.paused) v.play();
                }}
            }})();
            """
            
            await page.evaluate(codigo_magico)
            print(">>> [YOUTUBE ASYNC] Motor furtivo injetado!")
            
            # ✓ Cleanup (liberta recursos)
            await page.close()
            await context.close()
            await browser.close()
            
            if video_resolvido and video_resolvido.get("title"):
                return f"Sucesso! Encontrei e coloquei '{video_resolvido['title']}' a tocar."
            return f"Sucesso! Coloquei '{pesquisa}' a tocar."
    
    except Exception as e:
        return f"Erro na automação do YouTube (async): {str(e)}"
```

---

## 3. backend/tools/media_tools.py

### Mudança: Smart Detection para Async (linhas ~135-145)

**Antes (SEMPRE SYNC)**:
```python
try:
    result = await asyncio.to_thread(
        self.youtube_controller,
        pesquisa
    )
```

**Depois (SMART DETECTION)** ✅:
```python
try:
    # ✓ CRÍTICO: Se o controller tem método async, usar async (NÃO bloqueia event loop)
    if hasattr(self.youtube_controller, 'async_tocar_youtube_invisivel'):
        # Chamar versão async diretamente
        result = await self.youtube_controller.async_tocar_youtube_invisivel(pesquisa)
    else:
        # Fallback: executar em thread (bloqueia ligeiramente)
        result = await asyncio.to_thread(
            self.youtube_controller,
            pesquisa
        )
```

---

## 4. Novos Arquivos

### CORRECAO_TOOL_CALLING_E_ASYNC.md
- Documentação completa com exemplos
- Seções: Loop ReAct, problemas de async, fluxo completo
- Debugging guide

### teste_tool_calling_async.py
- 8 testes automatizados
- Validação de tool calling real
- Monitor de processos

---

## Checklist de Implementação

- [x] System prompt agressivo reforçado
- [x] Loop ReAct/tool calling implementado
- [x] Métodos async YouTube criados
- [x] Smart detection para async/sync
- [x] Documentação completa escrita
- [x] Script de testes criado
- [ ] Testes executados e validados
- [ ] Processos orfãos monitorados
- [ ] Testes de carga (100+ calls)

---

## Quick Verification

```bash
# Verificar se as mudanças estão em lugar:

# 1. System prompt contém "DOUTRINA INQUEBRÁVEL"
grep -n "DOUTRINA INQUEBRÁVEL" backend/brain_v2.py

# 2. Loop de tool calling está presente
grep -n "while iteration < max_tool_iterations" backend/brain_v2.py

# 3. async_tocar_youtube_invisivel existe
grep -n "async def async_tocar_youtube_invisivel" backend/automation.py

# 4. Smart detection em media_tools.py
grep -n "hasattr.*async_tocar_youtube_invisivel" backend/tools/media_tools.py
```

