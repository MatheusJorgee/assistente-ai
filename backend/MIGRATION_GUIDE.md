"""
PATCH MIGRATION GUIDE: Integrar Otimizações no brain.py Existente
==================================================================

Este arquivo mostra EXATAMENTE ONDE fazer mudanças no brain.py

ANTES DE COMEÇAR:
- Faça backup: copy backend\brain\quinta_feira_brain.py quinta_feira_brain.py.backup
- Use este guia passo a passo
- Teste após cada mudança com: python -m uvicorn main:app --reload
"""

# ============================================================================
# PASSO 1: Adicionar Imports no Topo do brain.py
# ============================================================================

# ANTES:
"""
from core import get_config, get_logger
from core.llm_provider import LLMProvider, Message, Response
from core.gemini_provider import GeminiAdapter
"""

# DEPOIS (adicionar estes):
"""
from core import get_config, get_logger
from core.llm_provider import LLMProvider, Message, Response
from core.gemini_provider import GeminiAdapter
from core.database import Database, get_database  # ← NOVO
from core.token_optimizer import get_token_counter, get_vision_optimizer  # ← NOVO
import hashlib  # ← NOVO (para hash de imagens)
from core.brain_optimization_guide import (  # ← NOVO
    OptimizedVisionProcessor,
    BrainContextBudget,
    ContextWindowManager,
)
"""

# ============================================================================
# PASSO 2: Copiar Classes Auxiliares
# ============================================================================

# Copiar estas 3 classes do arquivo brain_optimization_guide.py
# para o topo do brain.py (após imports, antes de QuintaFeiraBrain):

"""
class OptimizedVisionProcessor:
    ...

class BrainContextBudget:
    ...

class ContextWindowManager:
    ...
"""

# ============================================================================
# PASSO 3: Modificar __init__ do QuintaFeiraBrain
# ============================================================================

# ANTES:
"""
def __init__(
    self,
    llm_provider: Optional[LLMProvider] = None,
    tool_registry: Optional[Any] = None,
):
    self.config = get_config()
    self.logger = get_logger(__name__)
    
    # ... resto ...
    
    self.message_history = MessageHistory(max_messages=50)
    self.vision_buffer = VisionBuffer(max_images=5)
"""

# DEPOIS (adicionar):
"""
def __init__(
    self,
    llm_provider: Optional[LLMProvider] = None,
    tool_registry: Optional[Any] = None,
):
    self.config = get_config()
    self.logger = get_logger(__name__)
    
    # ... resto código existente ...
    
    self.message_history = MessageHistory(max_messages=50)
    self.vision_buffer = VisionBuffer(max_images=5)
    
    # ===== NOVO: Otimizações =====
    self.token_counter = get_token_counter()  # ← NOVO
    self.vision_processor = OptimizedVisionProcessor()  # ← NOVO
    self.database: Optional[Database] = None  # ← NOVO (será inicializado em startup)
    self.context_manager: Optional[ContextWindowManager] = None  # ← NOVO
    
    self.logger.info("[BRAIN] ✅ Modo otimizado de tokens ativado")
"""

# ============================================================================
# PASSO 4: Modificar async def startup()
# ============================================================================

# ANTES:
"""
async def startup(self) -> None:
    await self.llm_provider.initialize()
    self.logger.info("[BRAIN] ✓ Inicializado com sucesso")
"""

# DEPOIS (adicionar):
"""
async def startup(self) -> None:
    await self.llm_provider.initialize()
    
    # ===== NOVO: Carregar database para RAG =====
    try:
        self.database = await get_database()
        self.context_manager = ContextWindowManager(
            db=self.database,
            session_id="default",  # Será atualizada por sessão
            max_active_messages=20,  # Últimas 20 mensagens
            max_context_tokens=15_000,  # Budget de 15k tokens
        )
        self.logger.info("[BRAIN] ✅ Context manager inicializado")
    except Exception as e:
        self.logger.warning(f"[BRAIN] Sem database disponível: {e}")
    
    self.logger.info("[BRAIN] ✓ Inicializado com sucesso")
"""

# ============================================================================
# PASSO 5: Adicionar Método para Extrair Keywords
# ============================================================================

# Adicionar este método na classe QuintaFeiraBrain:

"""
def _extract_keywords(self, text: str, max_keywords: int = 5) -> list:
    \"\"\"
    Extrai palavras-chave da mensagem para RAG.
    
    Exemplos:
    - "como abre Excel?" → ["abre", "excel"]
    - "toca música de rock" → ["toca", "música", "rock"]
    \"\"\"
    # Stopwords comuns em português
    stopwords = {
        "o", "a", "de", "da", "do", "eu", "você", "ele", "ela",
        "que", "é", "e", "um", "uma", "os", "as", "dos", "das",
        "por", "para", "com", "sem", "em", "este", "esse", "aquele"
    }
    
    words = text.lower().split()
    
    # Filtrar: apenas palavras > 3 chars e não stopwords
    keywords = [
        w for w in words 
        if len(w) > 3 and w not in stopwords and w.isalpha()
    ]
    
    return list(set(keywords))[:max_keywords]
"""

# ============================================================================
# PASSO 6: Modificar Processamento de Imagem no ask()
# ============================================================================

# ANTES (em ask()):
"""
if image_data:
    self.vision_buffer.add_image(image_data)
    self.logger.info(f"[BRAIN] Imagem adicionada ao buffer...")
"""

# DEPOIS (adicionar otimização):
"""
if image_data:
    # ===== NOVO: Verificar se deve processar =====
    should_process = self.vision_processor.should_process_image(
        image_data,
        reason="default"  # ou "user_explicit" se usuário pediu
    )
    
    if should_process:
        # Otimizar imagem
        optimized = self.vision_processor.optimize_vision_request(image_data)
        
        # Usar imagem otimizada
        self.vision_buffer.add_image(
            optimized["data"],
            format=optimized["format"]
        )
        
        self.logger.info(
            f"[BRAIN] 🎨 Imagem otimizada: "
            f"{optimized['original_size']} → {optimized['optimized_size']} bytes "
            f"({optimized.get('compression_ratio', 0):.1f}% redução)"
        )
    else:
        self.logger.info("[BRAIN] 📦 Imagem em cache, pulando envio")
"""

# ============================================================================
# PASSO 7: Implementar RAG para Sistema Prompt
# ============================================================================

# ANTES (em ask(), construção do system_prompt):
"""
system_prompt = self.system_prompt
if hidden_context:
    system_prompt = (
        f"{system_prompt}\n\n"
        "[HIDDEN_LONG_TERM_MEMORY_CONTEXT]\n"
        f"{hidden_context}\n"
        "[/HIDDEN_LONG_TERM_MEMORY_CONTEXT]"
    )
"""

# DEPOIS (adicionar RAG):
"""
system_prompt = self.system_prompt

# ===== NOVO: RAG - Buscar contexto relevante =====
if self.database and self.context_manager:
    try:
        # Extrair keywords da mensagem do usuário
        keywords = self._extract_keywords(message)
        
        if keywords:
            # Buscar mensagens relevantes
            relevant_messages = await self.database.search_messages_by_keywords(
                session_id="default",  # TODO: usar session_id real
                keywords=keywords,
                limit=10,  # Máximo 10 mensagens relevantes
            )
            
            if relevant_messages:
                # Formatar contexto relevante
                relevant_context = "\n".join([
                    f"[{m.role.upper()}] {m.content[:200]}"
                    for m in relevant_messages
                ])
                
                system_prompt += (
                    f"\n\n[RELEVANT_CONTEXT_FROM_RAG]\n"
                    f"{relevant_context}\n"
                    f"[/RELEVANT_CONTEXT_FROM_RAG]"
                )
                
                self.logger.info(
                    f"[BRAIN] 🔍 RAG: Encontrados {len(relevant_messages)} msgs relevantes"
                )
    
    except Exception as e:
        self.logger.warning(f"[BRAIN] Erro em RAG: {e}")

# Contexto resumido se necessário
if self.context_manager:
    if await self.context_manager.should_summarize():
        summary = await self.context_manager.get_context_summary_injection()
        if summary:
            system_prompt += f"\n\n{summary}"
            self.logger.info("[BRAIN] ✓ Contexto resumido injetado")

# Hidden context (se fornecido)
if hidden_context:
    system_prompt += (
        f"\n\n[HIDDEN_LONG_TERM_MEMORY_CONTEXT]\n"
        f"{hidden_context}\n"
        f"[/HIDDEN_LONG_TERM_MEMORY_CONTEXT]"
    )
"""

# ============================================================================
# PASSO 8: Adicionar Token Counting
# ============================================================================

# ANTES (após receber resposta de LLM):
"""
response = await self._process_with_tool_calls(
    messages=llm_messages,
    tools=tools,
    temperature=self.config.LLM_TEMPERATURE
)
"""

# DEPOIS (adicionar contagem):
"""
response = await self._process_with_tool_calls(
    messages=llm_messages,
    tools=tools,
    temperature=self.config.LLM_TEMPERATURE
)

# ===== NOVO: Log de tokens =====
try:
    # Estimar tokens se resposta não tiver usage info
    if hasattr(response, 'usage') and response.usage:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
    else:
        # Fallback: estimar
        input_text = "\n".join([m.content or "" for m in llm_messages])
        output_text = response.text or ""
        input_tokens = self.token_counter.estimate_tokens(input_text)
        output_tokens = self.token_counter.estimate_tokens(output_text)
    
    # Log
    self.token_counter.log_request(
        messages=llm_messages,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        operation="chat",
        model=self.llm_provider.name(),
    )
    
    # Relatório rápido
    summary = self.token_counter.get_summary()
    self.logger.info(
        f"[TOKENS_SUMMARY] "
        f"Total: {summary['total_tokens']} | "
        f"In: {summary['input_tokens']} | "
        f"Out: {summary['output_tokens']} | "
        f"Avg: {summary['avg_tokens_per_call']:.0f} tokens/call | "
        f"Cost: ${summary['estimated_cost_usd']:.4f}"
    )
    
except Exception as e:
    self.logger.debug(f"[TOKENS] Erro ao logar: {e}")
"""

# ============================================================================
# PASSO 9: Atualizar Contexto Manager
# ============================================================================

# Na função ask(), após adicionar mensagem ao histórico:

"""
# ===== NOVO: Atualizar context budget =====
if self.context_manager:
    try:
        await self.context_manager.update_context_from_message(
            user_message=message,
            assistant_messages=[response.text],
        )
        
        budget = self.context_manager.get_budget_report()
        self.logger.debug(
            f"[CONTEXT] {budget['messages_count']} msgs | "
            f"{budget['current_tokens']} tokens | "
            f"{budget['utilization_percent']:.1f}% util"
        )
    except Exception as e:
        self.logger.warning(f"[CONTEXT] Erro ao atualizar: {e}")
"""

# ============================================================================
# PASSO 10: TESTE
# ============================================================================

"""
Depois de fazer todas as mudanças:

1. Salve o arquivo brain.py

2. No PowerShell:
   cd c:\Users\mathe\Documents\assistente-ai
   python -m py_compile backend\brain\quinta_feira_brain.py
   
   Se sem erro, ✅ sintaxe OK

3. Teste a API:
   python -m uvicorn main:app --reload
   
   Envie uma requisição:
   curl -X POST http://localhost:8000/api/chat \\
     -H "Content-Type: application/json" \\
     -d '{"command": "ola"}'
   
   Procure nos logs por:
   - "[BRAIN] 🔍 RAG: Encontrados X msgs"
   - "[TOKENS] op=chat | in=..."
   - "[CONTEXT] Y msgs | Z tokens"

4. Valide a visualização de custos:
   O terminal deve mostrar tokens a CADA requisição

5. Você deve ver redução imediata em custos!
"""

# ============================================================================
# RESUMO DE MUDANÇAS
# ============================================================================

"""
Arquivos criados:
✅ backend/core/token_optimizer.py (335 linhas)
✅ backend/core/brain_optimization_guide.py (280 linhas)
✅ backend/core/CONTEXT_WINDOW_MANAGEMENT.md (documentação)

Arquivos modificados:
✅ backend/core/database.py (+80 linhas, métodos RAG)

Arquivos a modificar:
⏳ backend/brain/quinta_feira_brain.py (10 pontos de mudança)

Tempo estimado: 30-60 minutos
Risco: Baixo (mudanças isoladas, sem breaking changes)
Rollback: Basta restaurar backup

RESULTADO ESPERADO:
Antes:  R$ 10,00/dia
Depois: R$ 1,50-2,50/dia
Economia: R$ 7,50-8,50/dia = R$ 225-255/mês
"""
