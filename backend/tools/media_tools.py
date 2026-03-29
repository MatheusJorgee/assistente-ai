"""
Ferramentas de Multimídia: Spotify, YouTube, Musica, Control
"""

import asyncio
import os
from typing import Dict, Any

try:
    from backend.core.tool_registry import Tool, ToolMetadata
except ModuleNotFoundError:
    from core.tool_registry import Tool, ToolMetadata


class TocarMusicaSpotifyTool(Tool):
    """
    Ferramenta para tocar música no Spotify via API.
    """
    
    def __init__(self, spotify_client=None):
        super().__init__(
            metadata=ToolMetadata(
                name="spotify_play",
                description="Toca música no Spotify via API (requer Premium e auth)",
                version="1.0.0",
                tags=["media", "spotify", "music"]
            )
        )
        self.spotify_client = spotify_client
    
    def validate_input(self, **kwargs) -> bool:
        return 'pesquisa' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Toca musica no Spotify.
        
        Args:
            pesquisa (str): "Artista - Música" ou termo de busca
            raciocinio (str): Contexto/razão (opcional)
            
        Returns:
            str: Resultado
        """
        if not self.spotify_client:
            return "[ERRO] Spotify não configurado. Verifique SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET"
        
        pesquisa = kwargs.get('pesquisa', '').strip()
        raciocinio = kwargs.get('raciocinio', '')
        
        if raciocinio and self._event_bus:
            self._event_bus.emit('cortex_thinking', {
                'step': 'spotify_reasoning',
                'reasoning': raciocinio,
                'search_query': pesquisa
            })
        
        try:
            # Buscar no Spotify
            resultados = await asyncio.to_thread(
                lambda: self.spotify_client.search(pesquisa, type='track', limit=1)
            )
            
            tracks = resultados.get('tracks', {}).get('items', [])
            if not tracks:
                return f"[AVISO] Nenhuma música encontrada para: {pesquisa}"
            
            track = tracks[0]
            track_uri = track['uri']
            track_name = track['name']
            artist = track['artists'][0]['name'] if track['artists'] else "Desconhecido"
            
            # Play
            await asyncio.to_thread(
                self.spotify_client.start_playback,
                uris=[track_uri]
            )
            
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'action': 'spotify_play',
                    'track': track_name,
                    'artist': artist,
                    'result': 'SUCESSO'
                })
            
            return f"▶ Tocando: {artist} - {track_name}"
            
        except Exception as e:
            return f"[ERRO Spotify] {str(e)}"


class TocarYoutubeTool(Tool):
    """
    Ferramenta para tocar vídeo/música no YouTube (via Playwright).
    """
    
    def __init__(self, youtube_controller=None):
        super().__init__(
            metadata=ToolMetadata(
                name="youtube_play",
                description="Toca vídeo/música no YouTube automaticamente",
                version="1.0.0",
                tags=["media", "youtube", "music"]
            )
        )
        self.youtube_controller = youtube_controller
    
    def validate_input(self, **kwargs) -> bool:
        return 'pesquisa' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Toca no YouTube.
        
        Args:
            pesquisa (str): Termo de busca
            raciocinio (str): Contexto (opcional)
            
        Returns:
            str: Resultado
        """
        if not self.youtube_controller:
            return "[ERRO] YouTube controller não configurado"
        
        pesquisa = kwargs.get('pesquisa', '').strip()
        raciocinio = kwargs.get('raciocinio', '')
        
        if raciocinio and self._event_bus:
            self._event_bus.emit('cortex_thinking', {
                'step': 'youtube_reasoning',
                'reasoning': raciocinio,
                'search_query': pesquisa
            })
        
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
            
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'action': 'youtube_play',
                    'query': pesquisa,
                    'result': 'SUCESSO'
                })
            
            return result
            
        except Exception as e:
            return f"[ERRO YouTube] {str(e)}"


class ControlarReproducaoTool(Tool):
    """
    Ferramenta para controlar reprodução: play, pause, skip, volume.
    """
    
    def __init__(self, media_controller=None):
        super().__init__(
            metadata=ToolMetadata(
                name="media_control",
                description="Controla reprodução: play, pause, skip, volume",
                version="1.0.0",
                tags=["media", "control"]
            )
        )
        self.media_controller = media_controller
    
    def validate_input(self, **kwargs) -> bool:
        return 'acao' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Controla reprodução.
        
        Args:
            acao (str): 'play', 'pause', 'skip', 'volume'
            valor (int): Para volume (0-100)
            
        Returns:
            str: Resultado
        """
        if not self.media_controller:
            return "[ERRO] Media controller não configurado"
        
        acao = kwargs.get('acao', '').strip().lower()
        valor = kwargs.get('valor', None)
        
        try:
            result = await asyncio.to_thread(
                self.media_controller,
                acao,
                valor
            )
            
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'action': 'media_control',
                    'control': acao,
                    'value': valor,
                    'result': 'SUCESSO'
                })
            
            return result
            
        except Exception as e:
            return f"[ERRO Media] {str(e)}"


class AbrirOuPesquisarTool(Tool):
    """
    Ferramenta para abrir aplicativos, URLs ou fazer pesquisas.
    """
    
    def __init__(self, ui_controller=None, oraculo_engine=None, database=None):
        super().__init__(
            metadata=ToolMetadata(
                name="open_search",
                description="Abre aplicativos, URLs ou faz pesquisas personalizadas",
                version="2.0.0",
                tags=["ui", "web", "navigation"]
            )
        )
        self.ui_controller = ui_controller
        self.oraculo = oraculo_engine
        self.db = database
    
    def validate_input(self, **kwargs) -> bool:
        return 'alvo' in kwargs and 'acao' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Abre/pesquisa.
        
        Args:
            alvo (str): App/URL/termo
            acao (str): 'abrir', 'pesquisar', etc
            contexto (str): Contexto opcional (twitch, youtube, etc)
            
        Returns:
            str: Resultado
        """
        if not self.ui_controller:
            return "[ERRO] UI Controller não configurado"
        
        alvo = kwargs.get('alvo', '').strip()
        acao = kwargs.get('acao', '').strip()
        contexto = kwargs.get('contexto', 'web').strip().lower()
        
        # Usar Oráculo para desambiguação se necessário
        if self.oraculo and self.db and contexto != 'web':
            if self._event_bus:
                self._event_bus.emit('cortex_thinking', {
                    'step': 'resolving_target',
                    'target': alvo,
                    'context': contexto
                })
            
            try:
                resolucao = await asyncio.to_thread(
                    lambda: self.oraculo.consultar_alvo_canonico(alvo, contexto)
                )
                alvo = resolucao.get('alvo_canonico', alvo)
            except:
                pass  # Fallback para alvo original
        
        try:
            result = await asyncio.to_thread(
                self.ui_controller,
                alvo,
                acao,
                contexto
            )
            
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'action': 'open_search',
                    'target': alvo,
                    'command': acao,
                    'context': contexto,
                    'result': 'SUCESSO'
                })
            
            return result
            
        except Exception as e:
            return f"[ERRO Open/Search] {str(e)}"
