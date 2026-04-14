"""
Ferramentas de MemÃ³ria e Aprendizado.
"""

import asyncio
from typing import Dict, Any

try:
    from core.tool_registry import Tool, ToolMetadata
except ModuleNotFoundError:
    from core.tool_registry import Tool, ToolMetadata


class GuardarMemoriaTool(Tool):
    """
    Ferramenta para guardar informaÃ§Ãµes na memÃ³ria longa de forma estruturada.
    """
    
    def __init__(self, database=None):
        super().__init__(
            metadata=ToolMetadata(
                name="save_memory",
                description="Guarda informaÃ§Ãµes na memÃ³ria de longo prazo com categorizaÃ§Ã£o",
                version="1.0.0",
                tags=["memory", "learning", "persistence"]
            )
        )
        self.db = database
    
    def validate_input(self, **kwargs) -> bool:
        return 'informacao' in kwargs and 'categoria' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Guarda informaÃ§Ã£o na memÃ³ria.
        
        Args:
            informacao (str): O que guardar
            categoria (str): Categoria (ex: "resolucao_contextual", "skill", "fato")
            
        Returns:
            str: ConfirmaÃ§Ã£o
        """
        if not self.db:
            return "[AVISO] Database nÃ£o configurado - memÃ³ria temporÃ¡ria apenas"
        
        informacao = kwargs.get('informacao', '').strip()
        categoria = kwargs.get('categoria', 'general').strip()
        
        try:
            resultado = await asyncio.to_thread(
                self.db.guardar_memoria,
                informacao,
                categoria
            )
            
            if self._event_bus:
                self._event_bus.emit('cortex_thinking', {
                    'step': 'memory_saved',
                    'category': categoria,
                    'info_length': len(informacao)
                })
            
            return resultado
            
        except Exception as e:
            return f"[ERRO MemÃ³ria] {str(e)}"


class BuscarMemoriaTool(Tool):
    """
    Ferramenta para buscar informaÃ§Ãµes na memÃ³ria.
    """
    
    def __init__(self, database=None):
        super().__init__(
            metadata=ToolMetadata(
                name="search_memory",
                description="Busca informaÃ§Ãµes na memÃ³ria de longo prazo",
                version="1.0.0",
                tags=["memory", "search"]
            )
        )
        self.db = database
    
    def validate_input(self, **kwargs) -> bool:
        return 'categoria' in kwargs or 'termos' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Busca na memÃ³ria.
        
        Args:
            categoria (str): Filtrar por categoria (opcional)
            termos (str): Termos de busca (opcional)
            
        Returns:
            str: Resultados encontrados
        """
        if not self.db:
            return "[AVISO] Database nÃ£o configurado"
        
        categoria = kwargs.get('categoria', '').strip()
        termos = kwargs.get('termos', '').strip()
        
        try:
            # Dependendo da implementaÃ§Ã£o do DB
            if categoria:
                resultados = await asyncio.to_thread(
                    self.db.buscar_memoria_por_categoria,
                    categoria
                )
            else:
                resultados = await asyncio.to_thread(
                    self.db.buscar_memoria,
                    termos
                )
            
            if self._event_bus:
                self._event_bus.emit('cortex_thinking', {
                    'step': 'memory_searched',
                    'category': categoria,
                    'results_count': len(resultados) if isinstance(resultados, list) else 1
                })
            
            return str(resultados)
            
        except Exception as e:
            return f"[ERRO Busca MemÃ³ria] {str(e)}"


class ResolverAlvoComAprendizadoTool(Tool):
    """
    Ferramenta inteligente para resolver termos ambÃ­guos usando OrÃ¡culo + cache.
    """
    
    def __init__(self, oraculo_engine=None, database=None):
        super().__init__(
            metadata=ToolMetadata(
                name="resolve_target",
                description="Resolve termos ambÃ­guos com OrÃ¡culo e cache de aprendizado",
                version="2.0.0",
                tags=["resolving", "learning", "disambiguation"]
            )
        )
        self.oraculo = oraculo_engine
        self.db = database
    
    def validate_input(self, **kwargs) -> bool:
        return 'termo' in kwargs and 'contexto' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Resolve termo com OrÃ¡culo + cache.
        
        Args:
            termo (str): Termo ambÃ­guo
            contexto (str): Contexto (twitch, youtube, web, etc)
            
        Returns:
            str: Resultado JSON com alvo canonico, confianÃ§a, etc
        """
        termo = kwargs.get('termo', '').strip()
        contexto = kwargs.get('contexto', 'web').strip().lower()
        
        if not termo:
            return '{"erro": "Termo vazio"}'
        
        # Tentar buscar no cache primeiro
        if self.db:
            try:
                cache = await asyncio.to_thread(
                    self.db.buscar_resolucao,
                    contexto,
                    termo
                )
                if cache:
                    if self._event_bus:
                        self._event_bus.emit('cortex_thinking', {
                            'step': 'target_resolved_from_cache',
                            'term': termo,
                            'context': contexto
                        })
                    return str(cache)
            except:
                pass
        
        # Consultar OrÃ¡culo
        if not self.oraculo:
            return f'{{"erro": "OrÃ¡culo nÃ£o disponÃ­vel"}}'
        
        if self._event_bus:
            self._event_bus.emit('cortex_thinking', {
                'step': 'consulting_oracle_for_disambiguation',
                'term': termo,
                'context': contexto
            })
        
        try:
            resultado = await asyncio.to_thread(
                self.oraculo.consultar_alvo_canonico,
                termo,
                contexto
            )
            
            # Guardar no cache
            if self.db:
                try:
                    await asyncio.to_thread(
                        self.db.salvar_resolucao,
                        contexto,
                        termo,
                        resultado.get('alvo_canonico', ''),
                        resultado.get('confianca', 'MEDIA'),
                        'oraculo'
                    )
                except:
                    pass
            
            if self._event_bus:
                self._event_bus.emit('cortex_thinking', {
                    'step': 'target_resolved_from_oracle',
                    'confidence': resultado.get('confianca')
                })
            
            return str(resultado)
            
        except Exception as e:
            return f'{{"erro": "{str(e)}"}}'

