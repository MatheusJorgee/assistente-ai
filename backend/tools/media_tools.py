"""
Ferramentas de MultimÃ­dia: Spotify, YouTube, Musica, Control
"""

import asyncio
import os
from typing import Dict, Any

try:
    from core.tool_registry import Tool, ToolMetadata
except ModuleNotFoundError:
    from core.tool_registry import Tool, ToolMetadata


class TocarMusicaSpotifyTool(Tool):
    """
    Ferramenta para tocar mÃºsica no Spotify via API.
    """
    
    def __init__(self, spotify_client=None):
        super().__init__(
            metadata=ToolMetadata(
                name="spotify_play",
                description="Toca mÃºsica no Spotify via API (requer Premium e auth)",
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
            pesquisa (str): "Artista - MÃºsica" ou termo de busca (alias 1)
            query (str): Termo de busca (alias 2 - do Gemini)
            track_query (str): Termo de busca (alias 3)
            raciocinio (str): Contexto/razÃ£o (opcional)
            
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
                return f"[AVISO] Nenhuma mÃºsica encontrada para: {pesquisa}"
            
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
            
            return f"â–¶ Tocando: {artist} - {track_name}"
            
        except Exception as e:
            return f"[ERRO Spotify] {str(e)}"


class TocarYoutubeTool(Tool):
    """
    Ferramenta para tocar vÃ­deo/mÃºsica no YouTube (via Playwright).
    """
    
    def __init__(self, youtube_controller=None):
        super().__init__(
            metadata=ToolMetadata(
                name="youtube_play",
                description="Toca vÃ­deo/mÃºsica no YouTube automaticamente",
                version="1.0.0",
                tags=["media", "youtube", "music"]
            )
        )
        self.youtube_controller = youtube_controller
    
    def validate_input(self, **kwargs) -> bool:
        # Aceitar tanto 'pesquisa' quanto 'video_query' (ou 'query')
        return ('pesquisa' in kwargs) or ('video_query' in kwargs) or ('query' in kwargs)
    
    async def execute(self, **kwargs) -> str:
        """
        Toca no YouTube.
        
        Args:
            pesquisa (str): Termo de busca (alias 1)
            video_query (str): Termo de busca (alias 2 - do Gemini)
            query (str): Termo de busca (alias 3)
            raciocinio (str): Contexto (opcional)
            
        Returns:
            str: Resultado
        """
        if not self.youtube_controller:
            return "[ERRO] YouTube controller nao configurado"
        
        # âœ“ CRÃTICO: Extrair pesquisa com fallback para multiplos nomes de parametro
        # Garantir que a pesquisa NÃƒO esteja vazia antes de chamar Playwright
        pesquisa = (
            kwargs.get('pesquisa', '').strip() or
            kwargs.get('video_query', '').strip() or
            kwargs.get('query', '').strip()
        )
        
        # âœ“ FIX: Validar pesquisa nÃ£o vazia ANTES de chamar controller
        if not pesquisa:
            return "[ERRO] Nenhum termo de busca fornecido para YouTube"
        
        raciocinio = kwargs.get('raciocinio', '')
        
        if raciocinio and self._event_bus:
            self._event_bus.emit('cortex_thinking', {
                'step': 'youtube_reasoning',
                'reasoning': raciocinio,
                'search_query': pesquisa
            })
        
        try:
            # âœ“ CRÃTICO: Se o controller tem mÃ©todo async, usar async (NÃƒO bloqueia event loop)
            if hasattr(self.youtube_controller, 'async_tocar_youtube_invisivel'):
                # Chamar versÃ£o async diretamente
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
    Ferramenta para controlar reproduÃ§Ã£o: play, pause, skip, volume, loop.
    Suporta YouTube (via JavaScript) e Spotify (via API Spotipy).
    """
    
    def __init__(self, media_controller=None):
        super().__init__(
            metadata=ToolMetadata(
                name="media_control",
                description="Controla reproduÃ§Ã£o: play, pause, skip, volume, loop/repeat - compatÃ­vel com YouTube e Spotify",
                version="1.1.0",
                tags=["media", "control", "youtube", "spotify"]
            )
        )
        self.media_controller = media_controller
    
    def validate_input(self, **kwargs) -> bool:
        return 'acao' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Controla reproduÃ§Ã£o de mÃ­dia (YouTube ou Spotify).
        
        Args:
            acao (str): Comandos suportados:
                       - 'play' / 'retomar' / 'comeÃ§ar': Inicia reproduÃ§Ã£o
                       - 'pause' / 'pausar' / 'parar': Pausa reproduÃ§Ã£o
                       - 'skip' / 'pular' / 'prÃ³xima': PrÃ³xima faixa
                       - 'loop' / 'repeat' / 'repetir' / 'lupi': Ativa repetiÃ§Ã£o
                       - 'volume' + valor: Ajusta volume (0-100)
            valor (int): Para volume (0-100) ou outros parÃ¢metros
            
        Returns:
            str: Resultado da aÃ§Ã£o ou mensagem de erro amigÃ¡vel
        """
        if not self.media_controller:
            return "[ERRO] Media controller nÃ£o configurado"
        
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
    
    Esta ferramenta Ã© APENAS para abrir aplicativos instalados no computador local.
    NÃƒO USE ESTA FERRAMENTA para responder a perguntas factuais, buscar informaÃ§Ãµes online,
    consultar notÃ­cias, clima, estado de servidores ou qualquer conhecimento em tempo real.
    
    Exemplos de uso CORRETO:
    - Abrir navegador, bloco de notas, calculadora
    - Iniciar Steam, Discord, VS Code
    - Abrir aplicaÃ§Ãµes locais
    
    Exemplos de uso INCORRETO (NÃƒO USE):
    - "A AWS estÃ¡ instÃ¡vel?" -> Use pesquisar_informacao_online
    - "Qual Ã© o clima hoje?" -> Use pesquisar_informacao_online
    - "NotÃ­cias sobre tecnologia" -> Use pesquisar_informacao_online
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
        # Aceitar variaÃ§Ãµes de nomes: alvo, target, url, query para o alvo
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
        
        # Usar OrÃ¡culo para desambiguaÃ§Ã£o se necessÃ¡rio
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
    FERRAMENTA MANDATÃ“RIA E PRIORITÃRIA PARA PERGUNTAS FACTUAIS EM TEMPO REAL.
    
    Esta Ã© a ferramenta EXCLUSIVA para responder a perguntas que requerem conhecimento
    atual ou informaÃ§Ãµes online em tempo real. SEMPRE use esta ferramenta quando o usuÃ¡rio
    perguntar sobre:
    
    - Estado de serviÃ§os (AWS, Google, etc.)
    - NotÃ­cias e eventos atuais
    - Clima e condiÃ§Ãµes meteorolÃ³gicas
    - PreÃ§os e cotaÃ§Ãµes
    - Status de servidores ou sistemas
    - Qualquer fato que possa mudar com o tempo
    
    NÃƒO USE para abrir navegadores ou iniciar aplicaÃ§Ãµes locais.
    Para abrir apps, use AbrirOuPesquisarTool.
    
    Exemplos:
    - "A AWS estÃ¡ instÃ¡vel?"
    - "Qual Ã© o clima em SÃ£o Paulo?"
    - "NotÃ­cias sobre IA hoje"
    """
    
    def __init__(self):
        super().__init__(
            metadata=ToolMetadata(
                name="pesquisar_informacao_online",
                description="Busca informaÃ§Ãµes factuais em tempo real na web via DuckDuckGo",
                version="1.0.0",
                tags=["web", "search", "information", "real-time"]
            )
        )
    
    def validate_input(self, **kwargs) -> bool:
        return 'pergunta' in kwargs or 'query' in kwargs
    
    async def execute(self, **kwargs) -> str:
        """
        Realiza pesquisa online para perguntas factuais usando DuckDuckGo API + Playwright.
        Extrai tÃ­tulo, descriÃ§Ã£o e URL de cada resultado de forma robusta.
        
        Args:
            pergunta (str): A pergunta factual a pesquisar
            query (str): Alias alternativo para pergunta
            
        Returns:
            str: Resultados da pesquisa formatados ou erro amigÃ¡vel
        """
        import asyncio
        
        # Extrair pergunta
        pergunta = kwargs.get('pergunta', '').strip() or kwargs.get('query', '').strip()
        
        if not pergunta:
            return "[ERRO] Pergunta nÃ£o fornecida"
        
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
                                    
                                    # Extrair descriÃ§Ã£o
                                    desc_elem = result.query_selector('[data-testid="result-snippet"]')
                                    if not desc_elem:
                                        desc_elem = result.query_selector('.result__snippet')
                                    
                                    descricao = desc_elem.text_content() if desc_elem else 'DescriÃ§Ã£o indisponÃ­vel'
                                    
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
                print(f">>> [AVISO] Playwright nÃ£o disponÃ­vel, tentando fallback...")
                return None
            except Exception as e:
                print(f">>> [ERRO Playwright] {str(e)}")
                return None
        
        def _buscar_com_ddg_api():
            """
            Fallback: Usa DuckDuckGo API JSON (sem scraping).
            Menos dados mas muito mais confiÃ¡vel.
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
                
                # Usar Abstract se disponÃ­vel
                if data.get('Heading') or data.get('Abstract'):
                    resultados.append({
                        'titulo': data.get('Heading', 'Resultado Principal'),
                        'descricao': data.get('Abstract', 'Sem descriÃ§Ã£o'),
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
            
            # Se Playwright falhar ou nÃ£o disponÃ­vel, tentar DDG API
            if not resultados:
                print(f">>> [FALLBACK] Usando DuckDuckGo API...")
                resultados = await asyncio.to_thread(_buscar_com_ddg_api)
            
            # ValidaÃ§Ã£o final
            if not resultados:
                return "AVISO: NÃ£o consegui extrair informaÃ§Ãµes neste momento. Tenta novamente ou reformula a pergunta."
            
            # Construir contexto para o LLM
            contexto_extraido = "RESULTADOS DA PESQUISA ONLINE:\n"
            for i, r in enumerate(resultados, 1):
                contexto_extraido += f"[{i}] TÃ­tulo: {r['titulo']}\nDescriÃ§Ã£o: {r['descricao']}\nURL: {r['url']}\n\n"
            
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
            return "ERRO DE REDE: NÃ£o consegui aceder aos motores de busca. Avisa o Matheus se o problema persistir."

