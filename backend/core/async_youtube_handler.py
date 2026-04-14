"""
ASYNC YOUTUBE HANDLER - FunÃ§Ãµes assÃ­ncronas para YouTube

Encapsula toda a lÃ³gica de Playwright em funÃ§Ãµes que nÃ£o bloqueiam o event loop.
Usa PlaywrightManager singleton internally.
"""

import asyncio
import urllib.parse
import time
from youtubesearchpython import VideosSearch


class AsyncYouTubeHandler:
    """Handler assÃ­ncrono para YouTube + Playwright."""
    
    def __init__(self, default_volume: float = 0.05):
        """Inicializa handler."""
        self.default_volume = default_volume
        self.playwright_manager = None
    
    async def initialize_manager(self):
        """Inicializa PlaywrightManager."""
        try:
            from core.playwright_manager import PlaywrightManager
        except ImportError:
            from core.playwright_manager import PlaywrightManager
        self.playwright_manager = await PlaywrightManager.get_instance()
        await self.playwright_manager.initialize()
    
    def _resolver_video_youtube(self, pesquisa: str):
        """Resolve vÃ­deo no YouTube (sÃ­ncrono - rÃ¡pido)."""
        query = pesquisa.strip()
        if not query:
            return None
        
        tentativas = [query]
        if "letra" not in query.lower() and "lyrics" not in query.lower():
            tentativas.append(f"{query} official audio")
        
        for tentativa in tentativas:
            try:
                resultados = VideosSearch(tentativa, limit=3).result()
                videos = resultados.get("result", [])
                if videos:
                    return {
                        "id": videos[0].get("id", ""),
                        "title": videos[0].get("title", ""),
                        "query": tentativa,
                    }
            except:
                continue
        
        return None
    
    async def tocar_youtube_invisivel(self, pesquisa: str) -> str:
        """
        Toca vÃ­deo YouTube de forma assÃ­ncrona (sem bloquear event loop).
        
        Usa PlaywrightManager singleton + async/await.
        """
        # Inicializar se preciso
        if self.playwright_manager is None:
            await self.initialize_manager()
        
        print(f"[YT] ðŸŽµ Tocando: {pesquisa}...")
        
        query_url = urllib.parse.quote(pesquisa)
        video_resolvido = self._resolver_video_youtube(pesquisa)
        
        try:
            # Obter pÃ¡gina do manager (fecha anterior se existir, cria nova)
            page = await self.playwright_manager.get_page()
            
            # Navegar atÃ© YouTube
            print(f"[YT] ðŸŒ Navegando atÃ© YouTube...")
            if video_resolvido and video_resolvido.get("id"):
                await page.goto(
                    f"https://www.youtube.com/watch?v={video_resolvido['id']}",
                    timeout=30000
                )
            else:
                await page.goto(
                    f"https://www.youtube.com/results?search_query={query_url}",
                    timeout=30000
                )
                await page.wait_for_selector("a#video-title", timeout=10000)
                await page.click("a#video-title")
            
            # Aguardar player de vÃ­deo
            print(f"[YT] â³ Aguardando player...")
            await page.wait_for_selector("video", timeout=15000)
            
            # Pequena pausa para garantir que vÃ­deo iniciou
            await asyncio.sleep(2)
            
            # Injetar cÃ³digo mÃ¡gico para controlar anÃºncios e volume
            codigo_magico = f"""
            () => {{
                const DEFAULT_VOLUME = {self.default_volume};
                window.__assistentePreferredVolume = DEFAULT_VOLUME;
                
                let lastVideoSrc = null;
                let hookedVideo = null;
                
                const aplicarVolume = (video) => {{
                    if (!video) return;
                    video.muted = false;
                    video.volume = DEFAULT_VOLUME;
                }};
                
                setInterval(() => {{
                    try {{
                        const video = document.querySelector('video');
                        if (!video) return;
                        
                        // Detectar anÃºncio
                        const isAd = document.querySelector('.ytp-ad-player-overlay, .ad-showing');
                        
                        if (isAd) {{
                            // Ã‰ anÃºncio: muta e pula
                            video.muted = true;
                            video.volume = 0;
                            video.playbackRate = 16.0;
                            document.querySelectorAll('.ytp-ad-skip-button, .ytp-skip-ad-button').forEach(b => b.click());
                            if (video.duration > 0 && video.currentTime < video.duration - 1) {{
                                video.currentTime = video.duration - 0.5;
                            }}
                        }} else {{
                            // NÃ£o Ã© anÃºncio: restaura
                            aplicarVolume(video);
                            video.playbackRate = 1.0;
                        }}
                        
                        // Fechar banners
                        document.querySelectorAll('.ytp-ad-overlay-close-button').forEach(b => b.click());
                    }} catch (err) {{}}
                }}, 150);
            }}
            """
            
            await page.evaluate(codigo_magico)
            print(f"[YT] âœ“ Motor furtivo injetado!")
            
            if video_resolvido and video_resolvido.get("title"):
                return f"â–¶ Tocando: {video_resolvido['title']}"
            return f"â–¶ Tocando: {pesquisa}"
        
        except asyncio.TimeoutError:
            return f"[ERRO] Timeout ao carregar YouTube para '{pesquisa}'"
        except Exception as e:
            print(f"[YT] âŒ Erro: {e}")
            return f"[ERRO] Falha na automaÃ§Ã£o do YouTube: {str(e)}"
    
    async def controlar_reproducao(self, acao: str) -> str:
        """Controla reproduÃ§Ã£o (pausar/retomar)."""
        if self.playwright_manager is None or not self.playwright_manager.page:
            return "Erro: YouTube nÃ£o estÃ¡ aberto"
        
        try:
            page = self.playwright_manager.page
            
            if "pausar" in acao.lower() or "parar" in acao.lower():
                await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.pause(); }")
                return "â¸ MÃºsica pausada com sucesso"
            elif "retomar" in acao.lower() or "voltar" in acao.lower() or "play" in acao.lower():
                await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.play(); }")
                return "â–¶ MÃºsica retomada"
            
            return "AÃ§Ã£o nÃ£o reconhecida"
        except Exception as e:
            return f"Erro ao controlar reproduÃ§Ã£o: {str(e)}"
    
    async def pular_musica(self) -> str:
        """Pula para prÃ³xima mÃºsica."""
        if self.playwright_manager is None or not self.playwright_manager.page:
            return "Erro: YouTube nÃ£o estÃ¡ aberto"
        
        try:
            page = self.playwright_manager.page
            await page.evaluate("() => { const btn = document.querySelector('.ytp-next-button'); if(btn) btn.click(); }")
            return "â­ Pulada para prÃ³xima"
        except Exception as e:
            return f"Erro ao pular: {str(e)}"
    
    async def cleanup(self) -> None:
        """Limpeza completa."""
        if self.playwright_manager:
            await self.playwright_manager.cleanup()


# InstÃ¢ncia global (lazy-loaded)
_async_yt_handler = None

async def get_async_yt_handler() -> AsyncYouTubeHandler:
    """ObtÃ©m instÃ¢ncia do handler assÃ­ncrono."""
    global _async_yt_handler
    if _async_yt_handler is None:
        _async_yt_handler = AsyncYouTubeHandler()
        await _async_yt_handler.initialize_manager()
    return _async_yt_handler

