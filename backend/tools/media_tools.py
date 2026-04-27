"""
Ferramentas de Multimídia: Spotify, YouTube, Musica, Control
"""

import asyncio
import os
import sys
from typing import Dict, Any


import threading as _threading


def _play_media_in_background_legacy(query: str) -> None:
    """Fire-and-forget para TocarYoutubeTool (legacy Tool)."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        try:
            import os as _os
            _bd = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            if _bd not in sys.path:
                sys.path.insert(0, _bd)
            from automation import OSAutomation
        except Exception:
            return
        automation = OSAutomation()
        loop.run_until_complete(automation.tocar_youtube_invisivel_async(query))
        loop.run_until_complete(asyncio.sleep(3600))
    except Exception:
        pass
    finally:
        loop.close()

try:
    from core.tool_registry import Tool, ToolMetadata
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
        # Aceitar tanto 'pesquisa' quanto 'query', 'track_query', etc
        return ('pesquisa' in kwargs) or ('query' in kwargs) or ('track_query' in kwargs)
    
    async def execute(self, **kwargs) -> str:
        """
        Toca musica no Spotify.
        
        Args:
            pesquisa (str): "Artista - Música" ou termo de busca (alias 1)
            query (str): Termo de busca (alias 2 - do Gemini)
            track_query (str): Termo de busca (alias 3)
            raciocinio (str): Contexto/razão (opcional)
            
        Returns:
            str: Resultado
        """
        if not self.spotify_client:
            return "[ERRO] Spotify nao configurado. Verifique SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET"
        
        # Extrair pesquisa com fallback para multiplos nomes de parametro
        pesquisa = (
            kwargs.get('pesquisa', '').strip() or
            kwargs.get('query', '').strip() or
            kwargs.get('track_query', '').strip()
        )
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
    Ferramenta de midia: toca musica/video no YouTube.

    Estrategia dupla:
      1. Motor invisivel (OSAutomation.tocar_youtube_invisivel) — executa
         Playwright no host para reproducao real com audio.
      2. Evento media_playback_requested — aviso visual ao frontend para
         exibir player inline (fallback se automacao indisponivel).

    Aliases aceitos: youtube_play, youtube, tocar_youtube, controlar_midia.
    """

    _YT_URL_RE = __import__('re').compile(
        r"(?:youtube\.com/(?:watch\?v=|embed/|v/)|youtu\.be/)([A-Za-z0-9_-]{6,})"
    )

    def __init__(self, youtube_controller=None):
        super().__init__(
            metadata=ToolMetadata(
                name="youtube_play",
                description=(
                    "Toca musica ou video no YouTube via automacao invisivel no host. "
                    "Use os parametros: pesquisa, video_url ou video_id."
                ),
                version="3.0.0",
                tags=["media", "youtube", "music"]
            )
        )
        self.youtube_controller = youtube_controller

    def validate_input(self, **kwargs) -> bool:
        return (
            ('pesquisa' in kwargs) or ('video_query' in kwargs) or
            ('query' in kwargs) or ('video_url' in kwargs) or
            ('video_id' in kwargs)
        )

    @classmethod
    def _extract_video_id(cls, text: str) -> str:
        if not text:
            return ""
        match = cls._YT_URL_RE.search(text)
        return match.group(1) if match else ""

    def _get_automation(self):
        """Lazy-load do OSAutomation."""
        try:
            from automation import OSAutomation
        except ImportError:
            try:
                from backend.automation import OSAutomation
            except ImportError:
                return None
        return OSAutomation()

    async def execute(self, **kwargs) -> str:
        """
        1. Tenta tocar via motor invisivel (OSAutomation).
        2. Publica media_playback_requested no EventBus como aviso ao frontend.

        Args:
            pesquisa / video_query / query (str): termo de busca
            video_url (str): URL direta (opcional)
            video_id  (str): ID direto (opcional)
            raciocinio (str): contexto para log (opcional)
        """
        pesquisa = (
            kwargs.get("pesquisa", "").strip() or
            kwargs.get("video_query", "").strip() or
            kwargs.get("query", "").strip()
        )
        video_url = (kwargs.get("video_url") or "").strip()
        video_id  = (kwargs.get("video_id")  or "").strip()

        if not video_id and video_url:
            video_id = self._extract_video_id(video_url)
        if not video_id and pesquisa:
            maybe = self._extract_video_id(pesquisa)
            if maybe:
                video_id = maybe

        if not (pesquisa or video_id or video_url):
            return "[ERRO] Nenhum termo de busca, URL ou ID fornecido para YouTube"

        raciocinio = kwargs.get("raciocinio", "")
        if raciocinio and self._event_bus:
            self._event_bus.emit("cortex_thinking", {
                "step": "youtube_reasoning",
                "reasoning": raciocinio,
                "search_query": pesquisa,
            })

        # ── 1) Motor invisivel (daemon thread fire-and-forget) ────────
        automation_result = "reproducao iniciada em segundo plano"
        query_for_automation = pesquisa or (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else video_url
        )
        try:
            _threading.Thread(
                target=_play_media_in_background_legacy,
                args=(query_for_automation,),
                name="yt-media-play",
                daemon=True,
            ).start()
        except Exception as e:
            automation_result = f"[AVISO Motor] {type(e).__name__}: {e}"

        # ── 2) Evento visual para o frontend ──────────────────────────
        media_payload: Dict[str, Any] = {
            "provider": "youtube",
            "video_id": video_id or None,
            "video_url": video_url or (
                f"https://www.youtube.com/watch?v={video_id}" if video_id else None
            ),
            "search_query": pesquisa or None,
            "title": pesquisa or None,
            "autoplay": True,
        }
        self.publish_runtime("media_playback_requested", media_payload)
        if self._event_bus:
            self._event_bus.emit("media_playback_requested", media_payload)
            self._event_bus.emit("action_terminal", {
                "action": "youtube_play",
                "query": pesquisa,
                "video_id": video_id,
                "result": automation_result,
            })

        label = pesquisa or (f"youtube.com/watch?v={video_id}" if video_id else video_url)
        return f"Tocando: {label} ({automation_result})"


class ControlarReproducaoTool(Tool):
    """
    Ferramenta para controlar reprodução: play, pause, skip, volume, loop.
    Suporta YouTube (via JavaScript) e Spotify (via API Spotipy).
    """
    
    def __init__(self, media_controller=None):
        super().__init__(
            metadata=ToolMetadata(
                name="media_control",
                description="Controla reprodução: play, pause, skip, volume, loop/repeat - compatível com YouTube e Spotify",
                version="1.1.0",
                tags=["media", "control", "youtube", "spotify"]
            )
        )
        self.media_controller = media_controller
    
    def validate_input(self, **kwargs) -> bool:
        return 'acao' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Controla reprodução de mídia (YouTube ou Spotify).
        
        Args:
            acao (str): Comandos suportados:
                       - 'play' / 'retomar' / 'começar': Inicia reprodução
                       - 'pause' / 'pausar' / 'parar': Pausa reprodução
                       - 'skip' / 'pular' / 'próxima': Próxima faixa
                       - 'loop' / 'repeat' / 'repetir' / 'lupi': Ativa repetição
                       - 'volume' + valor: Ajusta volume (0-100)
            valor (int): Para volume (0-100) ou outros parâmetros
            
        Returns:
            str: Resultado da ação ou mensagem de erro amigável
        """
        if not self.media_controller:
            return "[ERRO] Media controller não configurado"
        
        acao = kwargs.get('acao', '').strip().lower()
        valor = kwargs.get('valor', None)
        
        try:
            # Chamar com acao e passar valor em kwargs
            result = await asyncio.to_thread(
                lambda: self.media_controller(acao, valor=valor) if valor else self.media_controller(acao)
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
    FERRAMENTA EXCLUSIVA PARA INICIAR SOFTWARE LOCAL.
    
    Esta ferramenta é APENAS para abrir aplicativos instalados no computador local.
    NÃO USE ESTA FERRAMENTA para responder a perguntas factuais, buscar informações online,
    consultar notícias, clima, estado de servidores ou qualquer conhecimento em tempo real.
    
    Exemplos de uso CORRETO:
    - Abrir navegador, bloco de notas, calculadora
    - Iniciar Steam, Discord, VS Code
    - Abrir aplicações locais
    
    Exemplos de uso INCORRETO (NÃO USE):
    - "A AWS está instável?" -> Use pesquisar_informacao_online
    - "Qual é o clima hoje?" -> Use pesquisar_informacao_online
    - "Notícias sobre tecnologia" -> Use pesquisar_informacao_online
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
        # Aceitar variações de nomes: alvo, target, url, query para o alvo
        # acao, action, command para a acao
        tem_alvo = ('alvo' in kwargs) or ('target' in kwargs) or ('url' in kwargs) or ('query' in kwargs)
        tem_acao = ('acao' in kwargs) or ('action' in kwargs) or ('command' in kwargs)
        return tem_alvo and tem_acao
    
    async def execute(self, **kwargs) -> str:
        """
        Abre/pesquisa.
        
        Args:
            alvo (str): App/URL/termo (aliases: target, url, query)
            acao (str): 'abrir', 'pesquisar', etc (aliases: action, command)
            contexto (str): Contexto opcional (twitch, youtube, etc)
            
        Returns:
            str: Resultado
        """
        if not self.ui_controller:
            return "[ERRO] UI Controller nao configurado"
        
        # Extrair alvo com fallback para multiplos nomes
        alvo = (
            kwargs.get('alvo', '').strip() or
            kwargs.get('target', '').strip() or
            kwargs.get('url', '').strip() or
            kwargs.get('query', '').strip()
        )
        
        # Extrair acao com fallback para multiplos nomes
        acao = (
            kwargs.get('acao', '').strip() or
            kwargs.get('action', '').strip() or
            kwargs.get('command', '').strip()
        )
        
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


class PesquisarInformacaoOnlineTool(Tool):
    """
    FERRAMENTA MANDATÃ"RIA E PRIORITÃRIA PARA PERGUNTAS FACTUAIS EM TEMPO REAL.
    
    Esta é a ferramenta EXCLUSIVA para responder a perguntas que requerem conhecimento
    atual ou informações online em tempo real. SEMPRE use esta ferramenta quando o usuário
    perguntar sobre:
    
    - Estado de serviços (AWS, Google, etc.)
    - Notícias e eventos atuais
    - Clima e condições meteorológicas
    - Preços e cotações
    - Status de servidores ou sistemas
    - Qualquer fato que possa mudar com o tempo
    
    NÃO USE para abrir navegadores ou iniciar aplicações locais.
    Para abrir apps, use AbrirOuPesquisarTool.
    
    Exemplos:
    - "A AWS está instável?"
    - "Qual é o clima em São Paulo?"
    - "Notícias sobre IA hoje"
    """
    
    def __init__(self):
        super().__init__(
            metadata=ToolMetadata(
                name="pesquisar_informacao_online",
                description="Busca informações factuais em tempo real na web via DuckDuckGo",
                version="1.0.0",
                tags=["web", "search", "information", "real-time"]
            )
        )
    
    def validate_input(self, **kwargs) -> bool:
        return 'pergunta' in kwargs or 'query' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Realiza pesquisa online para perguntas factuais usando DuckDuckGo API + Playwright.
        Extrai título, descrição e URL de cada resultado de forma robusta.
        
        Args:
            pergunta (str): A pergunta factual a pesquisar
            query (str): Alias alternativo para pergunta
            
        Returns:
            str: Resultados da pesquisa formatados ou erro amigável
        """
        import asyncio
        
        # Extrair pergunta
        pergunta = kwargs.get('pergunta', '').strip() or kwargs.get('query', '').strip()
        
        if not pergunta:
            return "[ERRO] Pergunta não fornecida"
        
        print(f">>> [WEB SCALPEL] Extraindo dados da internet para: '{pergunta}'...")
        
        def _buscar_com_playwright():
            """
            Usa Playwright em headless mode para fazer web scraping robusto.
            Simula navegador real, evita bloqueios de bot.
            """
            try:
                from playwright.sync_api import sync_playwright
                import time
                
                resultados = []
                
                with sync_playwright() as p:
                    # Usar Chromium em headless mode
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    
                    # Tentar DuckDuckGo primeiro
                    url_ddg = f"https://duckduckgo.com/?q={pergunta}&t=h_&ia=web"
                    
                    try:
                        page.goto(url_ddg, wait_until="domcontentloaded", timeout=10000)
                        time.sleep(2)  # Esperar carregamento de JS
                        
                        # Extrair resultados de DuckDuckGo
                        results_html = page.query_selector_all('[data-testid="result"]')
                        
                        if not results_html:
                            # Tentar seletor alternativo
                            results_html = page.query_selector_all('.result')
                        
                        for result in results_html[:3]:
                            try:
                                # Extrair link
                                link_elem = result.query_selector('a[data-testid="result-title-a"]')
                                if not link_elem:
                                    link_elem = result.query_selector('a')
                                
                                if link_elem:
                                    titulo = link_elem.text_content()
                                    url_res = link_elem.get_attribute('href')
                                    
                                    # Extrair descrição
                                    desc_elem = result.query_selector('[data-testid="result-snippet"]')
                                    if not desc_elem:
                                        desc_elem = result.query_selector('.result__snippet')
                                    
                                    descricao = desc_elem.text_content() if desc_elem else 'Descrição indisponível'
                                    
                                    resultados.append({
                                        'titulo': titulo.strip(),
                                        'descricao': descricao.strip(),
                                        'url': url_res
                                    })
                            except:
                                continue
                        
                    finally:
                        browser.close()
                
                return resultados if resultados else None
                
            except ImportError:
                print(f">>> [AVISO] Playwright não disponível, tentando fallback...")
                return None
            except Exception as e:
                print(f">>> [ERRO Playwright] {str(e)}")
                return None
        
        def _buscar_com_ddg_api():
            """
            Fallback: Usa DuckDuckGo API JSON (sem scraping).
            Menos dados mas muito mais confiável.
            """
            try:
                import requests
                
                url = 'https://api.duckduckgo.com/'
                params = {
                    'q': pergunta,
                    'format': 'json',
                    'no_html': 1
                }
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                
                response = requests.get(url, params=params, headers=headers, timeout=8)
                response.raise_for_status()
                
                data = response.json()
                resultados = []
                
                # Usar Abstract se disponível
                if data.get('Heading') or data.get('Abstract'):
                    resultados.append({
                        'titulo': data.get('Heading', 'Resultado Principal'),
                        'descricao': data.get('Abstract', 'Sem descrição'),
                        'url': data.get('AbstractURL', '')
                    })
                
                # Usar RelatedTopics
                if 'RelatedTopics' in data and data['RelatedTopics']:
                    for topic in data['RelatedTopics'][:2]:
                        if 'Text' in topic and 'FirstURL' in topic:
                            resultados.append({
                                'titulo': topic.get('FirstURL', '').split('/')[-1],
                                'descricao': topic['Text'][:150],
                                'url': topic['FirstURL']
                            })
                
                return resultados if resultados else None
                
            except Exception as e:
                print(f">>> [ERRO DuckDuckGo API] {str(e)}")
                return None
        
        try:
            # Tentar Playwright primeiro
            resultados = await asyncio.to_thread(_buscar_com_playwright)
            
            # Se Playwright falhar ou não disponível, tentar DDG API
            if not resultados:
                print(f">>> [FALLBACK] Usando DuckDuckGo API...")
                resultados = await asyncio.to_thread(_buscar_com_ddg_api)
            
            # Validação final
            if not resultados:
                return "AVISO: Não consegui extrair informações neste momento. Tenta novamente ou reformula a pergunta."
            
            # Construir contexto para o LLM
            contexto_extraido = "RESULTADOS DA PESQUISA ONLINE:\n"
            for i, r in enumerate(resultados, 1):
                contexto_extraido += f"[{i}] Título: {r['titulo']}\nDescrição: {r['descricao']}\nURL: {r['url']}\n\n"
            
            # Emitir evento
            if self._event_bus:
                self._event_bus.emit('action_terminal', {
                    'action': 'web_search',
                    'query': pergunta,
                    'results_count': len(resultados),
                    'result': 'SUCESSO'
                })
            
            return contexto_extraido
            
        except Exception as e:
            print(f">>> [ERRO WEB SCALPEL] {str(e)}")
            return "ERRO DE REDE: Não consegui aceder aos motores de busca. Avisa o Matheus se o problema persistir."

