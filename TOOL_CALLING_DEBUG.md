# 🔧 Tool Calling Debug - Auditoria Completa

## 🎯 Objetivo
Garantir que o Gemini CHAMA ferramentas em vez de responder com "Como sou uma IA...".

---

## 📍 Pontos Críticos de Injeção (brain_v2.py)

### 1️⃣ **Conversão de Ferramentas (Linhas 268-344)**
```python
def _converter_ferramentas_para_gemini(self) -> list:
```
**O que faz**: Transforma ToolRegistry em `types.Tool` com schemas explícitos
**Output esperado**:
```
✓ [TOOLS] spotify_play → schema detalhado injetado
✓ [TOOLS] youtube_play → schema detalhado injetado
✓ [GENAI] 8 ferramentas com schemas EXPLÍCITOS para Gemini
✓ [GENAI] ToolConfig mode=AUTO garantido (tool calling OBRIGATÓRIO)
```

---

### 2️⃣ **Injeção Inicial (Linhas 246-264)**
```python
# ✓ CONSTRUIR CONFIG WITH TOOLS (não adicionar depois)
config_dict = {
    "system_instruction": self.instrucao_sistema,
    "temperature": 0.55,
    "tool_config": types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(
            mode=types.FunctionCallingConfig.Mode.AUTO  # ← FORÇA tool calling
        )
    )
}

# Passar ferramentas DENTRO do config (não adicionar depois)
if ferramentas_gemini:
    config_dict["tools"] = ferramentas_gemini  # ← TOOLS AQUI

config_chat = types.GenerateContentConfig(**config_dict)
self.config_com_tools = config_chat  # ← GUARDAR para reutilizar

# Criar sessão com config completo
self.chat_session = self.client.chats.create(
    model="gemini-2.5-flash",
    config=config_chat  # ← Sessão TEM tools
)
```

**Linha exata**: **253 - `config_dict["tools"] = ferramentas_gemini`**

**Linha exata**: **258 - `self.config_com_tools = config_chat`**

---

### 3️⃣ **Reutilização no Loop ReAct (Linhas 618-640)**
```python
# ✓ USAR CONFIG COM TOOLS (não criar nova sem tools!)
config_com_temp = types.GenerateContentConfig(
    system_instruction=self.config_com_tools.system_instruction,
    temperature=temperatura,
    tool_config=self.config_com_tools.tool_config,  # ← PRESERVAR
    tools=getattr(self.config_com_tools, 'tools', None)  # ← PRESERVAR
)

response = await asyncio.to_thread(
    self.chat_session.send_message,
    envio_atual,
    config_com_temp  # ← COM TOOLS
)
```

**Linha exata**: **624 - `tools=getattr(self.config_com_tools, 'tools', None)`**

---

## 🚨 O Que Mudou (Fix P0)

| Item | Antes | Depois |
|------|-------|--------|
| Config no send_message | Apenas temperatura ❌ | C/ tools + tool_config ✅ |
| Armazenamento config | Não reutilizava ❌ | `self.config_com_tools` ✅ |
| System prompt | Genérico ❌ | Suprema + proibições ✅ |
| Debug logs | Nenhum ❌ | Detecta function_calls ✅ |

---

## 🔍 Como Debugar

### Teste 1: Verificar Injeção
```bash
# Execute backend
cd backend
python start_hub.py

# Procure por:
✓ [GENAI] 8 ferramentas com schemas EXPLÍCITOS para Gemini
✓ [GENAI] ToolConfig mode=AUTO garantido (tool calling OBRIGATÓRIO)
```

### Teste 2: Verificar Tool Calling
```bash
# No frontend, diga:
> "Toca The Weeknd"

# No backend, procure por:
[GENAI] Iteração 1 - Texto: ...
[TOOL_CALLING] ✓ Detectadas 1 function calls!
[AÇÃO] Tool iniciada: spotify_play
```

### Teste 3: Verificar Sem Tool Calling
```bash
# Se aparecer:
[GENAI] Iteração 1 - Texto: Como sou uma inteligência artificial...

# SIGNIFICA: Tool calling NÃO foi acionado.
# Verificar:
1. Ferramentas foram listadas?
2. Schema está correto?
3. System prompt está sendo respeitado?
```

---

## 📊 Fluxo Completo

```
1. InitSetup (brain_v2.py:145-265)
   ├─ _converter_ferramentas_para_gemini() → types.Tool[]
   ├─ config_dict["tools"] = ferramentas_gemini
   ├─ config_chat = GenerateContentConfig(**config_dict)
   ├─ self.config_com_tools = config_chat  ← GUARDAR
   └─ chat_session.create(..., config=config_chat)
   
2. Ask Loop (brain_v2.py:600-640)
   ├─ iteration=1
   ├─ config_com_temp = GenerateContentConfig(...)
   ├─ config_com_temp.tools = self.config_com_tools.tools  ← REUTILIZAR
   ├─ send_message(..., config_com_temp)  ← COM TOOLS
   ├─ response.function_calls?
   │  ├─ SIM → Processar e executar
   │  └─ NÃO → Próxima iteração com historico
   └─ Sair do loop quando resposta.text
   
3. Tool Execution (brain_v2.py:641-720)
   ├─ fn_call.name → spotify_play, youtube_play, etc
   ├─ fn_call.args → {"pesquisa": "The Weeknd"}
   ├─ tool.execute(**fn_args)
   └─ Enviar resultado para send_message novamente
```

---

## ✅ Verificação Pré-Teste

- [ ] `config_com_tools` armazenado na linha 258
- [ ] `tool_config` reutilizado no send_message (linha 621)
- [ ] `tools` reutilizado no send_message (linha 624)
- [ ] System prompt tem "FORCE ABSOLUTA" + proibições
- [ ] Logs de debug `[TOOL_CALLING]` aparecem no stdout

---

## 🎯 Resultado Esperado

> **Usuário**: "_Toca uma música_"

### ❌ FALHA (Antes)
```
[GENAI] Como sou uma IA, não consigo tocar músicas...
```

### ✅ SUCESSO (Depois)
```
[GENAI] Iteração 1 - Texto: ...
[TOOL_CALLING] ✓ Detectadas 1 function calls!
[AÇÃO] Tool iniciada: spotify_play
[ACTION] Tocando: The Weeknd - Blinding Lights
```

---

## 📞 Suporte

Se ainda não funcionar:
1. Verificar se `ferramentas_gemini` tem conteúdo (não vazio)
2. Verificar logs de schema (`✓ [TOOLS] spotify_play...`)
3. Verificar se `system_instruction` tem a diretiva suprema
4. Verificar se `tool_config.mode = AUTO`

**Próximo passo**: Se ainda assim não chamar, significa que a SDK do Google GenAI tem limitação: usar `models.generate_content()` com ferramentas sem sessions.
