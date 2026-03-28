"""
Ferramentas de Visão: Captura de tela com compressão e detecção de monitor.
"""

import asyncio
import os
import base64
from typing import Dict, Any, Optional, Tuple
from PIL import Image, ImageGrab
import io

from backend.core.tool_registry import Tool, ToolMetadata


class CapturarVisaoTool(Tool):
    """
    Ferramenta para capturar tela com compressão e detecção de monitor ativo.
    
    Otimizações:
    - Compressão de imagem (WebP qualidade ajustável)
    - Detecção de qual monitor é o "foco" (onde o mouse está)
    - Caching do screenshot para reutilização na mesma request
    - Base64 para transmissão
    """
    
    def __init__(self):
        super().__init__(
            metadata=ToolMetadata(
                name="capture_vision",
                description="Captura tela com compressão, detecta monitor foco, retorna Base64",
                version="2.0.0",
                tags=["vision", "screenshot", "optimization"]
            )
        )
        self.compression_quality = int(os.getenv("VISION_COMPRESSION_QUALITY", "70"))
        self.max_dimension = int(os.getenv("VISION_MAX_DIMENSION", "1280"))
        self._last_screenshot = None
        self._last_screenshot_timestamp = 0
        self._cache_ttl_seconds = 0.5  # Cache por 500ms
    
    def validate_input(self, **kwargs) -> bool:
        # Captura de visão não requer argumentos (ou pode aceitar opcionais)
        return True
    
    def _detectar_monitor_foco(self) -> Dict[str, Any]:
        """
        Detecta qual monitor está em foco (onde o mouse está).
        
        Returns:
            {
                'monitor_index': int,
                'monitor_dims': (x1, y1, x2, y2),
                'is_primary': bool
            }
        """
        try:
            import pyautogui
            
            # Posição atual do mouse
            mouse_x, mouse_y = pyautogui.position()
            
            # Em sistemas com múltiplos monitores, a biblioteca
            # pode fornecer informações, mas não de forma direta.
            # Fallback: assumir monitor primário em ~1920x1080
            # Uma solução real usaria mss ou screeninfo
            
            try:
                # Tentativa com screeninfo (se instalado)
                import screeninfo
                monitors = screeninfo.get_monitors()
                for idx, monitor in enumerate(monitors):
                    if (monitor.x <= mouse_x < monitor.x + monitor.width and
                        monitor.y <= mouse_y < monitor.y + monitor.height):
                        return {
                            'monitor_index': idx,
                            'monitor_dims': (monitor.x, monitor.y, monitor.x + monitor.width, monitor.y + monitor.height),
                            'is_primary': idx == 0,
                            'resolution': (monitor.width, monitor.height)
                        }
            except ImportError:
                pass
            
            # Fallback: usar PILImageGrab (pega monitor primário)
            screen_width, screen_height = ImageGrab.grab().size
            return {
                'monitor_index': 0,
                'monitor_dims': (0, 0, screen_width, screen_height),
                'is_primary': True,
                'resolution': (screen_width, screen_height)
            }
            
        except Exception as e:
            # Fallback final
            return {
                'monitor_index': 0,
                'monitor_dims': (0, 0, 1920, 1080),
                'is_primary': True,
                'resolution': (1920, 1080),
                'error': str(e)
            }
    
    def _comprimir_imagem(self, imagem: Image.Image, max_dim: int, quality: int) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Comprime imagem via redimensionamento e conversão para WebP.
        
        Args:
            imagem: PIL Image object
            max_dim: Dimensão máxima para redimensionar
            quality: Qualidade WebP (1-100)
            
        Returns:
            (imagem_comprimida, metadados)
        """
        largura_orig, altura_orig = imagem.size
        
        # Redimensionar se exceder max_dim
        if largura_orig > max_dim or altura_orig > max_dim:
            imagem.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        
        metadados = {
            'original_resolution': (largura_orig, altura_orig),
            'compressed_resolution': imagem.size,
            'compression_ratio': (largura_orig * altura_orig) / (imagem.size[0] * imagem.size[1])
        }
        
        return imagem, metadados
    
    async def execute(self, **kwargs) -> str:
        """
        Captura tela, comprime e retorna Base64.
        
        Args:
            use_cache (bool): Usar cache? (default True)
            compress_quality (int): Qualidade de compressão (override)
            
        Returns:
            str: Base64 da imagem ou JSON de erro
        """
        use_cache = kwargs.get('use_cache', True)
        quality_override = kwargs.get('compress_quality', None)
        quality = quality_override or self.compression_quality
        
        import time
        now = time.time()
        
        # Verificar cache
        if use_cache and self._last_screenshot and (now - self._last_screenshot_timestamp) < self._cache_ttl_seconds:
            if self._event_bus:
                self._event_bus.emit('vision_captured', {
                    'source': 'cache',
                    'timestamp': now
                })
            return self._last_screenshot
        
        try:
            # Detectar monitor
            if self._event_bus:
                self._event_bus.emit('cortex_thinking', {
                    'step': 'detecting_focus_monitor'
                })
            
            monitor_info = await asyncio.to_thread(self._detectar_monitor_foco)
            
            # Capturar tela
            if self._event_bus:
                self._event_bus.emit('cortex_thinking', {
                    'step': 'capturing_screenshot'
                })
            
            imagem = await asyncio.to_thread(ImageGrab.grab)
            
            # Comprimir
            if self._event_bus:
                self._event_bus.emit('cortex_thinking', {
                    'step': 'compressing_image',
                    'quality': quality
                })
            
            imagem_comprimida, meta_compressao = await asyncio.to_thread(
                self._comprimir_imagem,
                imagem,
                self.max_dimension,
                quality
            )
            
            # Converter para Base64
            buffer = io.BytesIO()
            imagem_comprimida.save(buffer, format='WEBP', quality=quality, method=6)
            buffer.seek(0)
            base64_str = base64.b64encode(buffer.read()).decode('utf-8')
            
            # Guardar em cache
            self._last_screenshot = base64_str
            self._last_screenshot_timestamp = now
            
            # Emitir evento
            if self._event_bus:
                self._event_bus.emit('vision_captured', {
                    'monitor_index': monitor_info['monitor_index'],
                    'monitor_dims': monitor_info['monitor_dims'],
                    'original_resolution': meta_compressao['original_resolution'],
                    'compressed_resolution': meta_compressao['compressed_resolution'],
                    'compression_ratio': meta_compressao['compression_ratio'],
                    'base64_size': len(base64_str),
                    'quality': quality,
                    'timestamp': now
                })
            
            return base64_str
            
        except Exception as e:
            error_msg = f"[ERRO Visão] {str(e)}"
            if self._event_bus:
                self._event_bus.emit('vision_captured', {
                    'error': str(e),
                    'timestamp': now
                })
            return error_msg


class AnalisarVisaoComGeminiTool(Tool):
    """
    Ferramenta para analisar screenshot com Gemini (economia de tokens).
    Envia imagem comprimida + prompt específico.
    """
    
    def __init__(self, gemini_client=None):
        super().__init__(
            metadata=ToolMetadata(
                name="analyze_vision",
                description="Analisa screenshot com Gemini, otimizado para economia de tokens",
                version="1.0.0",
                tags=["vision", "ai", "analysis"]
            )
        )
        self.gemini_client = gemini_client
        self.capture_tool = CapturarVisaoTool()
    
    def validate_input(self, **kwargs) -> bool:
        return True  # Pode ser chamado sem argumentos
    
    async def execute(self, **kwargs) -> str:
        """
        Analisa visão com Gemini.
        
        Args:
            prompt (str): Prompt customizado (opcional)
            context (str): Contexto adicional
            
        Returns:
            str: Análise de texto
        """
        if not self.gemini_client:
            return "[ERRO] Gemini não configurado"
        
        prompt_custom = kwargs.get('prompt', '')
        context = kwargs.get('context', '')
        
        # Capturar tela
        base64_image = await self.capture_tool.safe_execute(use_cache=True)
        
        if base64_image.startswith('[ERRO'):
            return base64_image
        
        # Prompt otimizado
        prompt_final = prompt_custom or f"""
        Analise esta captura de tela e descreva sucintamente ET CONTEXTO: {context}.
        Foque em: elementos visuais principais, texto legível, janelas abertas, status do sistema.
        Seja conciso (máx 200 palavras).
        """
        
        if self._event_bus:
            self._event_bus.emit('cortex_thinking', {
                'step': 'analyzing_with_gemini',
                'context': context
            })
        
        try:
            # Converter base64 para PIL Image para enviar ao Gemini
            import base64 as b64_module
            from PIL import Image
            import io
            
            image_data = b64_module.b64decode(base64_image)
            imagem = Image.open(io.BytesIO(image_data))
            
            # Usar Gemini com a imagem
            result = await asyncio.to_thread(
                self.gemini_client.vision_analyze,
                imagem,
                prompt_final
            )
            
            if self._event_bus:
                self._event_bus.emit('vision_captured', {
                    'analysis': result[:100] + '...' if len(result) > 100 else result,
                    'status': 'analyzed'
                })
            
            return result
            
        except Exception as e:
            return f"[ERRO Análise Gemini] {str(e)}"
